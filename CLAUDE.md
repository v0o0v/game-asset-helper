# CLAUDE.md

이 파일은 Claude Code(혹은 다른 Claude 도구)가 이 저장소에서 작업할 때 항상 먼저 읽어야 하는 프로젝트 가이드다. **새 세션을 시작하면 가장 먼저 이 파일을 읽고**, 그 다음 [`DESIGN.md`](./DESIGN.md), [`HANDOFF.md`](./HANDOFF.md), [`milestones/`](./milestones/) 를 본다.

## 1. 프로젝트 한 줄 소개

**Game Asset Helper (GAH)** — Unity 게임 개발 중 Claude Code가 보유 에셋(2D 스프라이트, 스프라이트 시트, 사운드)을 자연어로 요청하면 가장 적합한 후보를 돌려주는 **MCP 서버 + 윈도우즈 트레이 상주 앱**.

핵심 아이디어
- 사용자가 `library/<pack>/...` 형태로 에셋 팩을 드롭하면 자동 인덱싱.
- Ollama로 도는 Gemma 4(`gemma4:e4b`)가 이미지·오디오를 직접 보고 의미 라벨을 만든다.
- 한 프로젝트에서 한 번 채택한 팩을 이후 검색에서 우선시해 통일성을 유지.
- Unity Asset Store 로컬 캐시(`.unitypackage`)도 자동 임포트.

자세한 아키텍처는 [`DESIGN.md`](./DESIGN.md).

## 2. 진행 현황 (요약)

| 마일스톤 | 상태 | 산출물 |
|---|---|---|
| M0 — 뼈대 | ✅ 완료 | 패키지 스캐폴딩, config/logging/single-instance, 트레이 셸, CLI |
| M1 — 워처 + Pack Manager + DB | ✅ 완료 | watchdog 래퍼+디바운서, 매니페스트/벤더 휴리스틱, SQLite 4테이블, 부팅 풀스캔, GUI 팩/라이브러리 탭 |
| M2 — 분석 파이프라인 + CLIP | ✅ 완료 | Pillow·numpy 기술 특성·librosa+soundfile·Ollama 클라이언트·`nomic-embed-text`·CLIP zero-shot·24축 ≈ 316 라벨 시드+`LabelRegistry`+라벨 관리 다이얼로그·분석 큐+ETA 상태바 |
| M2.1 — 분석 큐 병렬화 패치 | ✅ 완료 | 동시성 1→3, Ollama semaphore(parallel=2), CLIP threading.Lock, SQLite write_lock+busy_timeout, GUI 250ms 디바운스 |
| M3 — 검색 백엔드 + 통일성 + MCP | ✅ 완료 | HybridSearcher 가중합 0.40/0.15/0.20/0.20/0.05, ConsistencyScorer §4.6 표, UsageTracker, MCP stdio 12 도구 (mcp 1.27), GUI 검색 박스, `docs/MCP_USAGE_GUIDE.md` 본격화 |
| M4 — 검색 UX 풍부화 (1.5주) | 다음 | 자연어 라벨 부울 파서·다축 필터 칩·가중치 슬라이더·저장된 검색·suggest_packs samples 풍부화 |
| M5 — 시트 분석 + 애니메이션 (1주) | 대기 | 격자 분할·`suggest_animation_frames` |
| M6 — Unity Asset Store 임포트 (1주) | 대기 | `.unitypackage` 파서·캐시 스캐너 |
| M7 — GUI 마감 + 패키징 (1주) | 대기 | 상세/설정/프로젝트 탭·Qt i18n·PyInstaller |

각 마일스톤의 상세 계획·체크리스트·검증 결과는 `milestones/M{N}_plan.md`, `M{N}_todo.md`, `M{N}_verification.md`.

현재까지의 한 줄 인계 상태는 [`HANDOFF.md`](./HANDOFF.md).

## 3. 사용자 환경

- **OS**: Windows 10
- **Python**: python.org 정식 Python 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\`). **Microsoft Store Python 금지** — `%APPDATA%` 가상화로 경로가 불일치한다(M0 검증 중 확인).
- **venv 위치**: `%USERPROFILE%\.venvs\gah\`. Cowork 작업 폴더(`D:\ClaudeCowork\...`) 내부에 venv를 만들면 권한 충돌이 난다.
- **PowerShell**: 기본 5.1 가정. PowerShell 7+은 사용자가 별도 설치한 경우만.

## 4. 작업 규칙 (반드시 지킬 것)

### 4.1 문서·코드 언어
- **모든 문서는 한글로 작성**.
- **모든 폴더·파일 이름은 영어로**.

### 4.2 마일스톤 사이클 (TDD)
각 마일스톤은 다음 5단계를 반드시 순서대로 거친다.

1. `milestones/M{N}_plan.md` — 목표·산출물·작업 단위·테스트 전략·검증 기준. M0 문서를 표준 템플릿으로 참고.
2. `milestones/M{N}_todo.md` — TDD 순서 체크리스트.
3. **테스트 먼저 작성** (red phase). `tests/` 아래에 실패하는 테스트들을 작성하고, 한 번 돌려서 모두 실패하는지 확인.
4. 구현 (green phase). 테스트가 통과하도록 모듈 작성.
5. `milestones/M{N}_verification.md` — 자동 검증 결과(`pytest -v` 출력) + 사용자 수동 검증 항목 + 알려진 한계.

이 사이클을 건너뛰지 않는다. 코드 먼저 쓰고 테스트를 나중에 끼워 맞추지 않는다.

### 4.3 명령 제시 방식 (사용자에게 안내할 때)
- 사용자가 실행할 셸/PowerShell 명령은 **한 줄에 하나씩** 분리.
- `&&`로 묶지 않는다(PowerShell 5.1 미지원).
- `cd` 도 별도 줄.

### 4.4 모르는 정보는 웹으로
- 최신 모델·제품·버전·API 등 컷오프 이후 가능성이 있으면 추측 금지.
- WebSearch/WebFetch로 1차 출처 확인 후 답한다.
- 설계 문서/코드에 모델명·버전 같은 고정값을 박기 전에 반드시 검증.

### 4.5 작업 폴더와 분리
- 코드/문서 변경: `D:\ClaudeCowork\game-asset-helper\game-asset-helper\` (이 저장소 안)
- venv·런타임 데이터: 저장소 바깥. venv는 `%USERPROFILE%\.venvs\gah\`, GAH 런타임 데이터는 `%APPDATA%\GameAssetHelper\`.

## 5. 디렉터리 구조

```
game-asset-helper/
├── CLAUDE.md                 # 이 파일
├── HANDOFF.md                # 현재 인계 스냅샷
├── DESIGN.md                 # 전체 아키텍처 / MCP 도구 명세 / 데이터 스키마
├── README.md                 # 일반 사용자용 안내
├── pyproject.toml
├── milestones/
│   ├── README.md             # 마일스톤 디렉터리 안내
│   ├── M0_plan.md / M0_todo.md / M0_verification.md
│   ├── M1_plan.md / M1_todo.md / M1_verification.md
│   └── M{N}_*.md             # 각 마일스톤별 3종 세트
├── src/
│   └── gah/
│       ├── __init__.py
│       ├── __main__.py       # CLI 엔트리(--tray / --mcp / --version / --data-dir)
│       ├── config.py         # AppPaths / Config / load_config / save_config
│       ├── logging_setup.py  # 회전 파일 + stderr 핸들러
│       ├── platform/
│       │   └── single_instance.py
│       ├── app.py            # QApplication 부트 (지연 import) + 워처/스토어 연결
│       ├── tray.py           # 트레이 아이콘 + "메인 창 열기" 액션
│       ├── core/             # M1 도메인 로직
│       │   ├── asset_kind.py     # 확장자→sprite/sound
│       │   ├── manifest.py       # pack.json/pack.toml + 벤더 휴리스틱
│       │   ├── store.py          # SQLite + packs/assets/tags/asset_tags
│       │   ├── pack_manager.py   # 팩 디렉터리 인테이크
│       │   ├── scanner.py        # 부팅 풀스캔 화해
│       │   └── watcher.py        # watchdog 어댑터 + PackDebouncer
│       └── ui/               # M1 GUI
│           ├── main_window.py    # QMainWindow + 탭 컨테이너 + packChanged 시그널
│           ├── pack_view.py      # 팩 리스트 테이블
│           └── library_view.py   # 에셋 리스트 테이블
└── tests/
    ├── conftest.py
    ├── test_config.py / test_logging.py / test_single_instance.py / test_entrypoint.py / test_imports.py  # M0
    ├── test_asset_kind.py / test_manifest.py / test_store.py                                              # M1
    ├── test_pack_manager.py / test_scanner.py / test_watcher.py / test_ui_smoke.py                        # M1
```

후속 마일스톤에서 추가될 모듈은 `DESIGN.md §7` 참고.

## 6. 개발 환경 셋업 (새 PC에서)

```powershell
python -m venv $env:USERPROFILE\.venvs\gah
```

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
pip install -e D:\ClaudeCowork\game-asset-helper\game-asset-helper[dev]
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

`pytest -q`가 333 passed (+ 4 deselected) 로 떨어지면 준비 완료 (M0~M2.1 합 221 + M3 110). `pytest -m mcp_integration` 으로 옵트인 2 케이스 (실 `python -m gah --mcp` subprocess + JSON-RPC) 추가 검증 가능. M3 시점 검증 결과는 [`milestones/M3_verification.md`](./milestones/M3_verification.md).

## 7. 자주 쓰는 명령

테스트 전체:

```powershell
pytest -q
```

테스트 한 파일만:

```powershell
pytest tests/test_config.py -v
```

트레이 모드 실행:

```powershell
python -m gah --tray
```

버전 확인:

```powershell
python -m gah --version
```

## 8. 다음 작업 (M4)

M4 — **검색 UX 풍부화** (예상 1.5주 분량, 메모리 `project_search_ux_milestone.md`).

핵심 산출물 (자세한 건 M3 사이클을 본떠 `milestones/M4_plan.md`부터 작성):

- `src/gah/core/label_query.py` — 자연어 라벨 부울 파서 (`"pixel art AND dark"` → `LabelFilter[]` 변환). M3 의 `SearchRequest.labels_*` 구조화 입력 위에 얹힌다.
- GUI 라이브러리 탭 풍부 UX — 사이드 패널 라벨 칩 다중 선택, 5 채널 가중치 슬라이더, 결과 행에 `matched_labels` 칩 + 점수 시각화, "저장된 검색" 사이드바.
- `suggest_packs` 응답의 `samples` 필드 풍부화 — 썸네일 경로 + `preview_blurb` + 사운드 미리듣기 메타.
- 결과 다양성 부스터 — `find_asset` 에 `cross_pack_filter` 옵션 (MMR / round-robin / softmax 중 결정).
- `report_feedback` 페널티 학습 — `search_queries` + `asset_usage` 의 negative 신호를 다음 검색 가중치에 반영.

**M4 시작 방법**

1. `milestones/M4_plan.md` 작성 (M3 plan 을 템플릿 삼아)
2. `milestones/M4_todo.md` 작성
3. `tests/test_label_query.py`, `tests/test_library_search_ui_rich.py`, `tests/test_search_diversity.py`, `tests/test_feedback_penalty.py` 등 실패 테스트부터 작성
4. 구현 → 통과 → `milestones/M4_verification.md`

참고할 DESIGN 섹션: §4.8 (GUI 탭 구성), §6.5 (suggest_packs samples), §11 (마일스톤 로드맵). M3 의 `SearchRequest` 구조화 입력 + `HybridSearcher.hybrid()` 가 그대로 백엔드 — M4 는 그 위 UI/UX + 자연어 파서 + 다양성/페널티 알고리즘만 추가.

## 9. 알려진 이슈·주의사항

- **Cowork 작업 폴더에 venv 만들기 금지** — Cowork이 파일을 감시 중이라 `.exe` 생성이 차단됨. venv는 `%USERPROFILE%\.venvs\gah`.
- **Microsoft Store Python 금지** — `%APPDATA%` 가상화로 호출별 경로가 달라진다.
- **Cowork의 `mcp__workspace__bash`가 가끔 부팅 실패** — 호스트(사용자 PC) 측 컨테이너 이슈. Claude Desktop 재시작이 1차 해결.

## 10. 참고: 핵심 외부 문서

- [Gemma 4 model overview](https://ai.google.dev/gemma/docs/core)
- [Audio understanding | Gemma](https://ai.google.dev/gemma/docs/capabilities/audio)
- [Unity Manual — Asset Store cache location](https://docs.unity3d.com/Manual/upm-config-cache-as.html)
- [Ollama `gemma4:e4b`](https://ollama.com/library/gemma4:e4b)

`DESIGN.md §14`에 더 자세한 출처 정리.
