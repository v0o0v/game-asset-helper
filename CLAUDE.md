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
| **M5 — 웹 GUI 전환 + 라이브러리 리디자인 + Claude pick 인터랙션** (~5.5주) | **🔄 진행 중** (Phase 0~4 완료, **약 73%**, `feat/m5-web-gui` 브랜치 main 위 59+ commit) | **완료**: Phase 0~2 (인프라/페이지/검색/결과/카드/상세 모달/사운드 — `506 passed` baseline) + **Phase 3 (B/C/D 사이드 패널 18 task — ⚙ 토글 + 슬라이드 transition + 리사이즈 핸들 (240~640) + B 탭 (매칭 모드 AND/OR/NOT + 라벨 검색 + 종류 탭 + axis 칩 FlowLayout + 다축 필터 4 드롭다운 + selectedLabels → SearchRequest 매핑) + C 탭 (그리드/리스트/카드 크기/정렬 양방향 + 카드 메타 4 토글) + D 탭 (프리셋 3 + 슬라이더 6 + Config 즉시 갱신 + 저장된 검색 CRUD + 통일성 요약 + 모달) + 768px 반응형). Store 헬퍼 2 + endpoint 7 신규. populated_deps fixture 6 파일 → conftest 통합.** + **Phase 4 (Claude `request_user_pick` MCP 17번째 도구 + SSE push + 브라우저 보라색 pick 카드 + htmx-json-enc vendoring + TrayBridge QObject 시그널 브리지 + 자동 `record_asset_use(source="claude_pick")`) — 백엔드: `/internal/user-pick` long-poll + `/api/user-pick/{rid}` + `/sse/notifications`. MCP: `tool_request_user_pick` + httpx loopback. 프론트: `_pick_card.html` + Alpine pickQueue store + app.js + 헤더 배지. 트레이: `TrayBridge(QObject)` uvicorn→Qt 시그널.** **746 passed + 8 skipped**. **다음**: Phase 5 (Qt 폐기 + Pack/라벨 관리 웹 이식). spec: [`docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md`](./docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md), plan: [`milestones/M5_plan.md`](./milestones/M5_plan.md) |
| M6 — 시트 분석 + 애니메이션 (1주) | 대기 | 격자 분할·Aseprite/TexturePacker JSON·`suggest_animation_frames` |
| M7 — Unity Asset Store 임포트 (1주) | 대기 | `.unitypackage` 파서·캐시 스캐너 |
| M8 — 패키징 + i18n (1주) | 대기 | PyInstaller/Tauri 빌드, gettext / Jinja i18n |

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

`pytest -q`가 **746 passed + 8 skipped + 4 deselected** 로 떨어지면 준비 완료 (M0~M4 의 452 baseline + M5 Phase 0~4 의 +294 신규 - 폐기 예정 m4 Qt UI 7 파일 ~50 skip = 746). `pytest -m mcp_integration` 으로 옵트인 2 케이스 (실 `python -m gah --mcp` subprocess + JSON-RPC, **17 도구** 응답) 추가 검증 가능. M4 시점 검증 결과는 [`milestones/M4_verification.md`](./milestones/M4_verification.md). **M4 + M5 spec 은 [PR #5](https://github.com/v0o0v/game-asset-helper/pull/5) 로 main 머지됨**. **M5 작업 브랜치는 `feat/m5-web-gui`** (main 위 59+ commit, Phase 0~4 완료, Phase 5~6 진행 예정).

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

## 8. 다음 작업 (M5 Phase 5)

**M5 — 웹 GUI 전환 + 라이브러리 리디자인 + Claude pick 인터랙션** 이 **🔄 진행 중** (Phase 0~4 완료, 약 73%). 다음 phase 는 **Phase 5 (Qt 위젯 폐기 + Pack/라벨 관리 웹 이식)** — [`milestones/M5_plan.md`](./milestones/M5_plan.md) §4.5, ~0.5주.

### 8.1 현재 상태 (Phase 0~4 완료)

- 브랜치 `feat/m5-web-gui` — main 위 **59 commit** (미머지).
- 746 passed + 8 skipped + 4 deselected. 회귀 0.
- 완료된 인프라:
  - **Phase 0~2** — FastAPI/uvicorn/Jinja2/sse-starlette 의존성 + Config 7 신규 필드 + UsageSource enum + HTMX/Alpine vendoring + WebServer 별 스레드 + 포트 폴백 + SSE bus + 트레이 → 브라우저 + 라이브러리 페이지 + 검색/결과/카드/모달/사운드 (`506 passed`)
  - **Phase 3A** — 사이드 패널 ⚙ 토글 200ms 슬라이드 transition + `resizeHandle()` Alpine 컴포넌트 (240~640 클램프) + B/C/D 탭 헤더 + 3 partial 스캐폴딩 + sticky 정정
  - **Phase 3B** — B 탭 매칭 모드 (AND/OR/NOT 라디오 + form hidden input) + 라벨 검색 input + `.chip.matched` (box-shadow 단독) + 종류 탭 (sprite/sheet/sound) + `/api/filters/labels` (axis prefix 분류) + axis 칩 `chip-flow` FlowLayout + `toggleLabel()` + 다축 필터 4 `<details>` (팩 다중/벤더/라이선스/상태) + `/api/filters/packs` (vendors/licenses distinct + asset_count) + `_do_search` 가 labels list[int] → `Store.list_labels_raw` 룩업 → LabelFilter + match_mode → `labels_all/any/none` 분배 + `pack_ids` Python 후처리 필터 + form-data JSON parse + library.html hidden input 3개 (`match_mode`, `labels`, `pack_ids` JSON.stringify)
  - **Phase 3C** — C 탭 표시 옵션 (그리드/리스트, S/M/L, sort — 양방향 `$store.search.*` + 결과 툴바와 자동 동기) + 카드 메타 4 체크박스 (라벨/팩/점수/크기 — 즉시 카드 `x-show` 반영, 와이드 카드만 지원)
  - **Phase 3D** — 프리셋 3 (균형/통일성/참신성 — `PRESETS` dict + `POST /api/preset/{name}` + `_apply_weights_to_config` + Config mutate + activePreset 표시) + 슬라이더 6 (`<details>` 펼침 + `<input type="range" min="0" max="100">` + `WeightsBody` Pydantic + `POST /api/weights` + `syncWeights()` 자동 정규화) + 저장된 검색 CRUD (`saved_searches` 라우터 4 endpoint + `savedSearches()` Alpine + 복원 7 필드) + 통일성/페널티 요약 (`Store.project_usage_summary` 활용 + `/api/usage/summary` + `/ui/usage/detail` + `_modal_usage.html`) + 768px 반응형 (`position: fixed` + `transform: translateX` + resize 리스너 자동 닫힘)
  - **Phase 3 cleanup** — `Store.get_pack_by_id` + `Store.get_saved_search_by_id` 헬퍼 + endpoint 3 곳 raw SQL → 헬퍼 교체 + dead resize-init 블록 제거 + `_do_search` docstring (pack_ids 한계) + `populated_deps`/`populated_client` fixture 6 파일 → `tests/conftest.py` 통합
  - **Phase 4A** — `/internal/user-pick` long-poll + `/api/user-pick/{rid}` (수락/거부) + `/sse/notifications` (sse-starlette) — 4 commit
  - **Phase 4B** — `_pick_card.html` partial + `GET /ui/pick-card/{rid}` + htmx-sse SSE 클라이언트 + Alpine `pickQueue` store + `app.js` SSE 핸들러 + 헤더 배지 CSS (보라) + `htmx-json-enc.js` vendoring (채택 버튼 422 회피) — 5 commit
  - **Phase 4C** — `RequestUserPickRequest`/`Result` Pydantic 모델 + `tool_request_user_pick` (httpx loopback + 자동 `record_asset_use(source="claude_pick")`) + 17 도구 등록 + `mcp_integration` 17 도구 카운트 갱신 + cleanup (httpx.TransportError 통합 + source=manual pin 테스트 + 408 메시지 동적) — 5 commit
  - **Phase 4D** — `TrayBridge(QObject)` Qt 시그널 브리지 (uvicorn worker thread → Qt main thread → 트레이 툴팁/속성 갱신) + `MCP_USAGE_GUIDE` 17번째 도구 + Claude 의사결정 흐름 갱신 — 2 commit
- M4 Qt UI 7 파일은 module-level `pytest.skip("M5 Phase 5 가 폐기 예정")` 적용 (Phase 5 가 실 삭제).

### 8.2 다음 세션 진입 시 첫 작업

1. **환경 복원**:
   ```powershell
   & "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
   ```
   ```powershell
   cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
   ```
   ```powershell
   git status
   ```
   → `On branch feat/m5-web-gui` + 59+ commits ahead of main + clean.

2. **회귀 검증**:
   ```powershell
   pytest -q
   ```
   → `746 passed, 8 skipped, 4 deselected`.

3. **선택 — 시각 검증**: `python -m gah --tray` 후 브라우저에서 사이드 패널 ⚙ + B/C/D 탭 + 리사이즈 + 다축 필터 + 저장된 검색 + 다크 모드 동작 확인. 수동 검증 항목 상세 = [`HANDOFF.md`](./HANDOFF.md) §9.6.

4. **Phase 5 시작** — plan §4.5 의 task 진행. 핵심: Qt UI 7 파일 실 삭제 + Pack 페이지 (`/packs`) + 라벨 관리 페이지 (`/labels/admin`) 백엔드 + 프론트엔드 이식.

5. **Phase 5 시작 전 follow-up (옵션)**:
   - `_card_list.html` 에 `cardMeta` `x-show` 바인딩 추가 (현재 와이드 카드만 지원)
   - 자산 상세 모달 [채택]/[거부] 버튼이 호출하는 `POST /api/record-use` + `POST /api/feedback` endpoint — Phase 4 의 자동 `record_asset_use` 인프라 활용
   - 모달 ESC 키 dismiss + 카드 keyboard accessibility — Phase 6 마감 흡수

상세 진행 상태 + 알려진 한계는 [`HANDOFF.md`](./HANDOFF.md) §5 + §9.

### 8.3 진행 패턴 (M5 동안 유지)

본 마일스톤은 `superpowers:subagent-driven-development` 스킬 패턴으로 진행 중:
- **implementer subagent (sonnet)** — phase 의 logical sub-unit 단위로 task 묶음 dispatch
- **spec compliance reviewer (sonnet or haiku)** — 구현이 spec 과 일치하는지 코드 직접 읽고 검증
- **code quality reviewer (sonnet or haiku)** — 깨끗한 코드 + 테스트 품질 평가
- review 가 NEEDS_FIXES 면 fix subagent (sonnet) 로 재처리 후 재검토

각 sub-phase 끝마다 회귀 (`pytest -q`) + 한국어 commit. 한 phase 가 끝나면 HANDOFF + CLAUDE.md 갱신 후 사용자 인계.

### 8.4 신규 의존성 (Phase 0 에서 추가 완료)

`fastapi>=0.110`, `uvicorn[standard]>=0.27`, `jinja2>=3.1`, `python-multipart>=0.0.9`, `sse-starlette>=2`. 정적 JS (HTMX 1.9.12 + Alpine 3.13.10) 는 `src/gah/web/static/vendor/` 에 vendoring.

(spec §7 의 `websockets>=12` 는 SSE 결정 [plan §3.2] 후 `sse-starlette>=2` 로 대체. uvicorn[standard] 가 websockets 를 transitive 로 가져오므로 별도 추가 불필요.)

### 8.5 마일스톤 재정렬 (변경 없음)

| 신규 # | 이름 | 일정 | 상태 |
|---:|---|---:|---|
| M5 | 웹 GUI 전환 + 리디자인 + Claude pick | 5.5주 | 🔄 진행 중 (~73%) |
| M6 | 시트 분석 + 애니메이션 | 1주 | 대기 |
| M7 | Unity Asset Store 임포트 | 1주 | 대기 |
| M8 | 패키징 + i18n | 1주 | 대기 |

참고 DESIGN: §3 (아키텍처 — M5 가 §4.8 갱신 예정), §4.5 (MCP — Phase 4C 에서 17 도구 완료), §11 (로드맵).

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
