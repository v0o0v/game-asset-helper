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
| M4 — 검색 UX 풍부화 | ✅ 완료 (main 머지됨, [PR #5](https://github.com/v0o0v/game-asset-helper/pull/5)) | label_query 파서 AND/OR/NOT + axis:label + bare 자동매칭, HybridSearcher 6채널 0.35/0.10/0.20/0.20/0.05/0.10 feedback, diversity none/mmr/round_robin, saved_searches 4 신규 MCP 도구 (12→16), feedback_records signed weight 페널티 학습, suggest_packs samples 풍부화. Qt UI 위젯 4개는 M5 가 폐기 예정 |
| **M5 — 웹 GUI 전환 + 라이브러리 리디자인 + Claude pick 인터랙션** (~5.5주) | **✅ 완료** (`feat/m5-web-gui` 브랜치, main 머지 대기) | 웹 GUI 전환 완료 + 라이브러리/팩/라벨 리디자인 + Claude pick + 17 MCP 도구 + Qt UI 폐기. Phase 0~6 완료 — **796 passed + 1 skipped**. spec: [`docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md`](./docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md), plan: [`milestones/M5_plan.md`](./milestones/M5_plan.md) |
| M6 — 시트 분석 + 애니메이션 | ✅ 완료 ([PR #7](https://github.com/v0o0v/game-asset-helper/pull/7) main 머지) + 후속 patch 8건 | sheet 4 모듈 + SpritesheetAnalyzer + `suggest_animation_frames` MCP 18번째 + 와이드/리스트 카드 🎞 배지 + Ollama cold-start retry. 신규 의존성 0. **91 신규 테스트** (M6 spec +84, 후속 patch +7, 총 887). spec: [`docs/superpowers/specs/2026-05-18-m6-sheet-and-animation-design.md`](./docs/superpowers/specs/2026-05-18-m6-sheet-and-animation-design.md) |
| **M7 — Unity Asset Store 임포트 (1주)** | **✅ 완료** (feat/m7-unity-asset-store-import 브랜치, PR 대기) | `.unitypackage` 파서·캐시 스캐너·임포터 + 활성 프로젝트 + 프로젝트 페이지 + 자산별 선호도 + 20 MCP 도구. 신규 의존성 0. **+124 신규 테스트** (총 1011). spec: [`docs/superpowers/specs/2026-05-18-m7-unity-asset-store-import.md`](./docs/superpowers/specs/2026-05-18-m7-unity-asset-store-import.md), plan: [`milestones/M7_plan.md`](./milestones/M7_plan.md) |
| **M8 — 패키징 + i18n (1주)** | **대기 (다음)** | PyInstaller/Tauri 빌드, gettext / Jinja i18n |

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
│       ├── web/              # M5 FastAPI 웹 서버 (app/server/routers/templates/static)
│       └── ui/               # M5 Phase 5C 에서 완전 삭제됨 (src/gah/ui/ 디렉터리 없음)
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

`pytest -q`가 **1011 passed + 1 skipped + 40 deselected** 로 떨어지면 준비 완료 (M0~M4 의 452 baseline + M5 Phase 0~6 의 +344 + M6 Phase 0~5 spec +84 + M6 후속 patch +7 + M7 +124). `pytest -m mcp_integration` 으로 옵트인 2 케이스 (실 `python -m gah --mcp` subprocess + JSON-RPC, **20 도구** 응답) 추가 검증 가능. M5 최종 검증 결과는 [`milestones/M5_verification.md`](./milestones/M5_verification.md). M6 최종 검증 결과는 [`milestones/M6_verification.md`](./milestones/M6_verification.md). M7 최종 검증 결과는 [`milestones/M7_verification.md`](./milestones/M7_verification.md). **M4 + M5 + M6 모두 main 머지 완료** ([PR #5](https://github.com/v0o0v/game-asset-helper/pull/5), [PR #6](https://github.com/v0o0v/game-asset-helper/pull/6), [PR #7](https://github.com/v0o0v/game-asset-helper/pull/7)). **M7 PR 대기** (`feat/m7-unity-asset-store-import` 브랜치). **현재 브랜치 = `feat/m7-unity-asset-store-import`**.

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

## 8. 다음 작업 (M8 — 패키징 + i18n)

M7 이 **✅ 완료**됐다 (Phase 0~7 완료, `feat/m7-unity-asset-store-import` 브랜치, 1011 passed). 다음 마일스톤은 **M8 — 패키징 + i18n** (~1주).

### 8.1 현재 상태 (M7 완료)

- 브랜치 `feat/m7-unity-asset-store-import` (PR 대기).
- **1011 passed + 1 skipped + 40 deselected**. 회귀 0.
- M7 완료된 인프라 요약:
  - **Phase 0** — 7 frozen dataclass + `.unitypackage` fixture + asset_factory (+7 테스트)
  - **Phase 1A~1D** — cache_paths 4단계 + unitypackage 파서 + scanner + importer + remote_optin (+39 테스트)
  - **Phase 2A~2B** — Store unity_imports/projects/preferences + Config 5 필드 + 트레이 + 자동 스캔 (+29 테스트)
  - **Phase 3A~3B** — MCP 4 Pydantic + 2 도구 (scan/list) + INSTRUCTIONS + 20 도구 통합 (+10 테스트)
  - **Phase 4A~4B** — Unity 라우터 6 endpoint + HTML/CSS 페이지 (+8 테스트)
  - **Phase 5** — 활성 프로젝트 + SSE + 글로벌 헤더 + 채택 버튼 (+13 테스트)
  - **Phase 6A~6C** — /projects 목록 + /projects/\<id\> 사용/분포 + 선호도 패널 (+13 테스트)
  - **Phase 7** — I-1~I-5 격리 invariant 회귀 + 문서 + verification (+5 테스트)
- MCP **20 도구** (18 → +2: `scan_unity_asset_store_cache`, `list_unity_packages`).

### 8.2 다음 세션 진입 시 첫 작업

1. **M7 PR 머지 확인**:
   ```powershell
   git status
   ```
   → `feat/m7-unity-asset-store-import` 브랜치, PR 상태 확인.

2. **환경 복원**:
   ```powershell
   & "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
   ```
   ```powershell
   cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
   ```

3. **회귀 검증**:
   ```powershell
   pytest -q
   ```
   → `1011 passed, 1 skipped, 40 deselected`.

4. **M8 시작**: `superpowers:brainstorming` 으로 옵션 비교 → `superpowers:writing-plans` 로 `milestones/M8_plan.md` 작성.

M8 핵심 (DESIGN.md §11 Milestone 8):
- 웹 UI i18n — Jinja2 + `babel`, `Config.ui_language` (`"ko"`/`"en"`/`"auto"`)
- Pack/프로젝트 탭 풍부 UX (메타 수정, manual_override, 프로젝트 pin/block, 사용 분포 차트)
- 다크/라이트 모드 토글 UI
- PyInstaller 단일 exe (CLIP 모델 가중치 포함 또는 첫 실행 시 다운로드), 자동 시작 토글

상세 진행 상태 + 알려진 한계는 [`HANDOFF.md`](./HANDOFF.md).

### 8.3 마일스톤 재정렬 (M7 완료)

| # | 이름 | 일정 | 상태 |
|---:|---|---:|---|
| M5 | 웹 GUI 전환 + 리디자인 + Claude pick | 5.5주 | ✅ 완료 |
| M6 | 시트 분석 + 애니메이션 | 1주 | ✅ 완료 |
| M7 | Unity Asset Store 임포트 | 1주 | ✅ 완료 |
| **M8** | **패키징 + i18n** | **1주** | **대기** |

참고 DESIGN: §3 (아키텍처), §4.9 (Unity Asset Store Importer — M7), §4.10 (활성 프로젝트/프로젝트 페이지 — M7), §4.5 (MCP — 20 도구), §4.8 (트레이 + 웹 UI), §11 (로드맵).

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
