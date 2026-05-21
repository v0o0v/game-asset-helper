# CLAUDE.md

이 파일은 Claude Code(혹은 다른 Claude 도구)가 이 저장소에서 작업할 때 항상 먼저 읽어야 하는 프로젝트 가이드다. **새 세션을 시작하면 가장 먼저 이 파일을 읽고**, 그 다음 [`DESIGN.md`](./DESIGN.md), [`HANDOFF.md`](./HANDOFF.md), [`milestones/`](./milestones/) 를 본다.

## 1. 프로젝트 한 줄 소개

**AssetCacheMCP (`assetcache-mcp`)** — Unity 게임 개발 중 Claude Code가 보유 에셋(2D 스프라이트, 스프라이트 시트, 사운드)을 자연어로 요청하면 가장 적합한 후보를 돌려주는 **MCP 서버 + 윈도우즈 트레이 상주 앱**.

핵심 아이디어
- 사용자가 `library/<pack>/...` 형태로 에셋 팩을 드롭하면 자동 인덱싱.
- Ollama로 도는 Gemma 4(`gemma4:e4b`)가 이미지·오디오를 직접 보고 의미 라벨을 만든다.
- 한 프로젝트에서 한 번 채택한 팩을 이후 검색에서 우선시해 통일성을 유지.
- Unity Asset Store 로컬 캐시(`.unitypackage`)도 자동 임포트.
- **PyPI 1차 배포** — `pipx install assetcache-mcp` / `uv tool install assetcache-mcp` (Windows + Mac + Linux 동시 지원). 단일 `.exe` 는 2차 옵션.

자세한 아키텍처는 [`DESIGN.md`](./DESIGN.md).

## 2. 진행 현황 (요약)

| 구간 | 상태 | 위치 |
|---|---|---|
| M0 ~ M11.7 | ✅ 완료 (모두 main 머지) | 상세 PR/회귀/산출물 → [`milestones/HISTORY.md`](./milestones/HISTORY.md) |
| **현재 main** | M11.7 (PR #27 `04c205e` squash, v0.2.3~v0.2.6 publish 누적 보류) | mood OPTIONAL + category 별 mood 차단 (A1 + A2). LIVE: crown mood 2→0 토큰 (A2 완벽), 시트 mood 10→5 토큰 (58% 감소). 회귀 **1601 passed + 1 skipped + 63 deselected**. 옵트인 6/6 PASSED. MCP 20 도구 |
| **다음 후보** | M11.8 (📋 spec/plan 작성됨) | mood 시드 `neutral`/`minimalist` `is_enabled=0` 마이그 (v0.2.7 candidate). M11.7 LIVE 의 catch-all 'neutral' 시트 4/5 잔존 해소. ⚠️ `palette.neutral` 은 절대 유지 (M11.6 tone group 핵심). spec: [m11-8](./docs/superpowers/specs/2026-05-22-m11-8-mood-seed-disable.md), plan: [M11_8_plan.md](./milestones/M11_8_plan.md) |

전체 마일스톤 정렬 + future 후보 (M12~M18) 는 [`milestones/ROADMAP.md`](./milestones/ROADMAP.md).  
한 줄 인계 스냅샷은 [`HANDOFF.md`](./HANDOFF.md).

## 3. 사용자 환경

- **OS**: Windows 10
- **Python**: python.org 정식 Python 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\`). **Microsoft Store Python 금지** — `%APPDATA%` 가상화로 경로가 불일치한다.
- **venv 위치**: `%USERPROFILE%\.venvs\gah\`. Cowork 작업 폴더(`D:\ClaudeCowork\...`) 내부에 venv를 만들면 권한 충돌이 난다.
- **PowerShell**: 기본 5.1 가정. PowerShell 7+은 사용자가 별도 설치한 경우만.

## 4. 작업 규칙 (반드시 지킬 것)

### 4.1 문서·코드 언어
- **모든 문서는 한글로 작성**.
- **모든 폴더·파일 이름은 영어로**.

### 4.2 마일스톤 사이클 (TDD)
각 마일스톤은 다음 5단계를 반드시 순서대로 거친다.

1. `milestones/M{N}_plan.md` — 목표·산출물·작업 단위·테스트 전략·검증 기준.
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
- 코드/문서 변경: 이 저장소 안에서. 워크트리는 사용하지 않는다 (메인 저장소에서 직접 branch checkout).
- venv·런타임 데이터: 저장소 바깥. venv는 `%USERPROFILE%\.venvs\gah\` (이름은 그대로 유지), AssetCacheMCP 런타임 데이터는 `%APPDATA%\AssetCacheMCP\`.

## 5. 디렉터리 구조

```
assetcache-mcp/               # M10 에서 game-asset-helper → assetcache-mcp 로 GitHub repo rename
├── CLAUDE.md                 # 이 파일
├── HANDOFF.md                # 현재 인계 스냅샷
├── DESIGN.md                 # 전체 아키텍처 / MCP 도구 명세 / 데이터 스키마
├── README.md                 # 일반 사용자용 안내
├── pyproject.toml
├── milestones/
│   ├── HISTORY.md            # M0~M11.3 완료분 아카이브
│   ├── ROADMAP.md            # 전체 마일스톤 정렬 + future
│   ├── README.md             # 마일스톤 디렉터리 안내
│   └── M{N}_*.md             # 각 마일스톤별 plan/todo/verification 3종 세트
├── docs/
│   ├── SETUP.md              # 개발 환경 셋업 + 자주 쓰는 명령
│   ├── MCP_USAGE_GUIDE.md    # MCP 20 도구 사용 가이드
│   ├── WEB_UI_GUIDE.md       # 웹 GUI 가이드
│   └── superpowers/          # spec/plan 아카이브
├── src/
│   └── assetcache/           # M10 에서 src/gah/ → src/assetcache/ rename
│       ├── __main__.py       # CLI 엔트리(--tray / --mcp / --version / --data-dir)
│       ├── config.py / logging_setup.py / app.py / tray.py
│       ├── platform/         # single_instance
│       ├── updater/          # PyPI 알림 (M10 Phase 2)
│       ├── core/             # 도메인 로직 (M1~M11.7)
│       │   ├── store.py / pack_manager.py / scanner.py / watcher.py
│       │   ├── analyzer/     # payload_parser / tech_meta / spritesheet_meta / messages
│       │   ├── batch/        # manager / poller / sheet_classifier
│       │   ├── llm/backends/ # ollama / gemini / claude / openai / openrouter / huggingface
│       │   └── sheet/        # detect / grid_detect
│       └── web/              # FastAPI 웹 서버
└── tests/                    # pytest 1601 passed (M11.7 baseline) + 옵트인 6 (llm_integration)
```

후속 마일스톤에서 추가될 모듈은 `DESIGN.md §7` 참고.

## 6. 개발 환경 셋업 + 자주 쓰는 명령

[`docs/SETUP.md`](./docs/SETUP.md) — 새 PC 셋업 절차, `pytest -q` baseline, 자주 쓰는 명령 (tray/mcp/version), 옵트인 마커 (`mcp_integration` / `llm_integration`).

## 7. 다음 작업

**M11.8 mood 시드 `neutral`/`minimalist` 비활성화** (v0.2.7 candidate).  M11.7 main `04c205e` squash 머지 완료 ([PR #27](https://github.com/v0o0v/assetcache-mcp/pull/27), 회귀 1601 + 옵트인 6 PASSED).  M11.4~M11.7 의 v0.2.3~v0.2.6 publish 모두 보류 누적 (M11.8 머지 후 0.2.2 → 0.2.7 직접 bump 권장).

1. 환경 복원 + 회귀 baseline:

   ```powershell
   & "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
   ```
   ```powershell
   git checkout main
   ```
   ```powershell
   git pull
   ```
   ```powershell
   pytest -q
   ```
   → `1601 passed, 1 skipped, 63 deselected` 확인.

2. **M11.8 implement** — 새 브랜치 + 시드 마이그 TDD red→green 부터:

   ```powershell
   git checkout -b feat/m11-8-mood-seed-disable
   ```

   spec/plan:
   - [`docs/superpowers/specs/2026-05-22-m11-8-mood-seed-disable.md`](./docs/superpowers/specs/2026-05-22-m11-8-mood-seed-disable.md)
   - [`milestones/M11_8_plan.md`](./milestones/M11_8_plan.md) — Phase 1 시드+migration TDD → Phase 2 prompt 동기화 → Phase 3 LIVE 검증 → Phase 4 PR

   ⚠️ **핵심 주의**: `palette.neutral` 은 절대 비활성화 X (M11.6 tone group enum 핵심 토큰).  `mood.neutral` + `mood.minimalist` 만 대상.

3. (선택, M11.8 머지 후) v0.2.7 publish — `pyproject.toml` + `src/assetcache/__init__.py` 0.2.2 → 0.2.7 bump + tag:

   ```powershell
   git tag v0.2.7
   ```
   ```powershell
   git push origin main v0.2.7
   ```
   → Trusted Publishing OIDC 6회째 자동 (M11.3 v0.2.2 publish 이후 5 마일스톤 누적 deliver).

## 8. 알려진 이슈·주의사항

- **Cowork 작업 폴더에 venv 만들기 금지** — Cowork이 파일을 감시 중이라 `.exe` 생성이 차단됨. venv는 `%USERPROFILE%\.venvs\gah`.
- **Microsoft Store Python 금지** — `%APPDATA%` 가상화로 호출별 경로가 달라진다.
- **Cowork의 `mcp__workspace__bash`가 가끔 부팅 실패** — 호스트(사용자 PC) 측 컨테이너 이슈. Claude Desktop 재시작이 1차 해결.

## 9. 참고: 핵심 외부 문서

- [Gemma 4 model overview](https://ai.google.dev/gemma/docs/core)
- [Audio understanding | Gemma](https://ai.google.dev/gemma/docs/capabilities/audio)
- [Unity Manual — Asset Store cache location](https://docs.unity3d.com/Manual/upm-config-cache-as.html)
- [Ollama `gemma4:e4b`](https://ollama.com/library/gemma4:e4b)

`DESIGN.md §14`에 더 자세한 출처 정리.
