# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-21 (M11.1 Gemini Batch API + /analyzing dashboard 완료)
**마지막 완료 작업**: **M11.1 완료** — feat/m11-1-gemini-batch-api 브랜치 (PR 대기). Gemini Batch API hybrid 정책 (50% 비용, 24h SLO) + `/analyzing` dashboard + M11 알려진 한계(`mark_asset_backends` write hook) 동시 해결. 회귀 **1252 → 1426 (+174) + 옵트인 13 → 16**. 신규 의존성 0.
**M11.1 결과**: `core/batch/` 패키지 (types/manager/poller) + DB `batch_jobs` table + `assets.batch_job_id/batch_state` + Store 13 신규 메서드 + GeminiBackend batch_chat/embed/get/cancel/download + BatchManager(try_submit/cancel) + BatchPoller(daemon, 30분 주기) + AnalysisQueue hook + BatchConfig + /settings batch 카드 + /analyzing dashboard + Qt tray toggle + i18n 18 msgid. spec: [`docs/superpowers/specs/2026-05-20-gemini-batch-api-design.md`](docs/superpowers/specs/2026-05-20-gemini-batch-api-design.md), verification: [`milestones/M11_1_verification.md`](milestones/M11_1_verification.md)
**현재 브랜치**: `feat/m11-1-gemini-batch-api` (PR 대기 — main `f68ef88` 기준)
**다음 세션 작업**: **PR 생성 + main 머지 + v0.2.1 tag → PyPI publish** (Trusted Publishing OIDC, ~30초). 그 후 M12 (C4 측정/학습/벤치마크) 또는 M13 (Mac/Linux 검증) 사용자 결정.

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가"를 한 번에 파악하도록 작성된 스냅샷이다.

## 1. 한 줄 요약

**M11.1 완료** (feat/m11-1-gemini-batch-api 브랜치, PR 대기). Gemini Batch API hybrid 정책 (50% 비용, 24h SLO) + `/analyzing` dashboard + M11 한계 (`mark_asset_backends`) 해결. 회귀 **1426 passed + 1 skipped + 56 deselected** (M11 v0.2.0 1252 + 174 신규 + 3 옵트인 추가). 신규 의존성 0. MCP 20 도구 그대로. 다음 세션: **PR 생성 + v0.2.1 PyPI publish** (Trusted Publishing OIDC, ~30초).

## 2. 검증된 사실 (M10 완료 시점)

자동 — `pytest -q` 결과 **1103 passed + 1 skipped + 40 deselected** (M10 +57, baseline 1046)

| Phase | 핵심 산출물 | 신규 테스트 |
|---|---|---:|
| 0 — rename mechanical | `src/gah/` → `src/assetcache/` + 모든 import / config / babel.cfg / spec / docs / `.po` 경로 | 0 (회귀만) |
| 1 — 마이그레이션 helper | `core/migration.py` (detect + MigrationRunner async copy/move + rollback + 디스크 검사) + `web/routers/migration.py` + SSE + `_migration_banner.html` + CLI `--migrate=copy\|move` + i18n msgid 10건 (**v0.1.1 yagni-clean 됨**) | +21 |
| 2 — PyPI 알림 (M9 cherry-pick) | `core/updater/version.py` (semver + classmethod + ordering) + `checker.py` (PyPI JSON API + ETag 캐시 + 24h PollingLoop) + `pip_command.py` (pipx/uv/pip 분기) + `web/routers/updates.py` 단순화 + `_pypi_update_banner.html` + `tray.TrayController` + `_TrayBridge` Qt Signal cross-thread + i18n msgid 4건 | +17 |
| 3 — docs + i18n catalog + verification | README/CLAUDE/HANDOFF/DESIGN 표기 일괄 갱신 + `tests/test_locale_assetcache_msgid.py` (5 msgid × 2 lang = 10 instance) + `milestones/M10_verification.md` (수동 시나리오 7건) | +10 |
| 4 — PyPI 패키지 + 빌드 + 배포 | `pyproject.toml` name=`assetcache-mcp` + version=0.1.0 + scripts + classifiers + package-data + `main_mcp()` entry + `python -m build` + TestPyPI + 정식 PyPI + Trusted Publishing (OIDC) + GitHub Actions workflow | 0 (배포 검증) |
| 5 — 마일스톤 wrap-up | PR #11 머지 + v0.1.0 GitHub release publish + repo rename + token revoke + cleanup PR | 0 |
| 후속 fix | workflow Node.js 24 호환 (`actions/checkout@v6` + `actions/setup-python@v6`, PR #12) | 0 |
| **M10 전체** | **MCP 20 도구 그대로, 신규 의존성 0 (run-time), dev `build` + `twine` 추가** | **+57** |

수동 — 시나리오 1~7 의 자동 가능 부분 (rename 회귀 / wheel local smoke / TestPyPI / 정식 PyPI install / Trusted Publishing workflow) 검증 통과. 시나리오 1~5 의 사용자 직접 부분 (트레이 + 배너) 은 [`milestones/M10_verification.md`](./milestones/M10_verification.md) §2 참고.

## 3. 환경 (재현용)

| 항목 | 값 |
|---|---|
| OS | Windows 10 (Mac/Linux 정식 검증은 M11 또는 별도 마일스톤) |
| Python | python.org 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\python.exe`) |
| venv | `C:\Users\v0o0v\.venvs\gah\` (이름은 그대로 유지 — 새 이름 `.venvs\assetcache` 로 마이그레이션은 향후 옵션) |
| 작업 폴더 | `D:\ClaudeCowork\game-asset-helper\game-asset-helper\` (main 저장소) |
| 사용자 런타임 데이터 | `C:\Users\v0o0v\AppData\Roaming\AssetCacheMCP\` (M10 rename 후) |
| 라이브러리 루트 | `%APPDATA%\AssetCacheMCP\library\` |
| 메타 DB | `%APPDATA%\AssetCacheMCP\metadata.db` (WAL, M7 `unity_imports` / `projects` / `asset_usage` 확장 유지) |
| **MCP 도구 수** | 20 도구 (M10 신규 0) |
| PyPI 패키지 | `assetcache-mcp` 0.1.2 (https://pypi.org/project/assetcache-mcp/0.1.2/) |
| CLI 콘솔 스크립트 | `assetcache` (트레이/MCP 통합) + `assetcache-mcp` (MCP stdio 전용, `main_mcp` entry) |

**금기**: Microsoft Store Python, Cowork 작업 폴더 내부 venv.

M10 신규 의존성: 0 (run-time). dev 만 +2 (`build`, `twine`).

## 4. 새 세션에서 바로 이어가는 방법

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
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

→ main 기준: `1252 passed, 1 skipped, 53 deselected` (M11 v0.2.0 baseline).

feat/m11-1-gemini-batch-api 브랜치에서 PR 머지 후: `1426 passed, 1 skipped, 56 deselected` 예상.

**현재 브랜치 = `feat/m11-1-gemini-batch-api`** (PR 대기, main `f68ef88` 기준). PR 머지 후 v0.2.1 tag push → Trusted Publishing 자동 publish.

## 5. 다음 세션 진입 절차 (M11.1 완료 — v0.2.1 publish 후 M12/M13)

### 5.1 로드맵 (2026-05-20 brainstorm 확정)

상세 spec: [`docs/superpowers/specs/2026-05-20-roadmap-design.md`](docs/superpowers/specs/2026-05-20-roadmap-design.md) (main `b3f8fe8`).

| Tier | M# | 마일스톤 | 의존 |
|---|---|---|---|
| **0** (1차 implement 대상) | **M11** | Multi-backend LLM Architecture — 6 backend (Ollama/Gemini/Claude/OpenAI/OpenRouter/HF), modality 별 chain + 자동 fallback, /settings UI. design 3/3 확정 | — |
| **1** (M11 직속) | M12 | C4 측정 / 학습 / 벤치마크 (6 backend 정확도 비교) | M11 |
| 1 | M13 | Mac/Linux 검증 + M11 cross-platform | M11 |
| **2** (큰 새 기능) | M14 | MCP 원격 통신 (HTTP/SSE + 인증, server↔client 다른 머신) | 독립 |
| 2 | M15 | Unity Editor 통합 (drag-drop / 자동 import) | 독립 |
| **3** (검색 확장 / 성능 / 분산) | M16 | C2 이미지/사운드 유사 검색 | M11 (embedding) |
| 3 | M17 | 성능 (대량 라이브러리 처리량 + 메모리/시작 시간) | 독립 |
| 3 | M18 | 분산 분석 (여러 PC 라이브러리 공유 + 분석 분담) | **M14 필수** |

권장 다음: **PR 생성 + main 머지 + v0.2.1 tag push** → Trusted Publishing OIDC 자동 publish (패턴 검증 4회째). 그 후 M12 (C4 측정/학습) 또는 M13 (Mac/Linux 검증) 사용자 결정.

### 5.2 Reactive backlog (별도 트리거 시)

| 항목 | 트리거 |
|---|---|
| 사용자 피드백 수집 | [PyPI download 통계](https://pypistats.org/packages/assetcache-mcp) + [GitHub Issues](https://github.com/v0o0v/assetcache-mcp/issues) (1주 후 모니터링) |
| v0.1.3+ patch 누적 | bug fix 발견 시 — tag push 한 줄로 자동 publish (Trusted Publishing 검증된 30초 패턴) |
| 코드 서명 + 자동 업데이트 (M9 복귀) | SignPath 채택 결정 시 — spec/plan 보존됨 (`docs/superpowers/{plans,specs}/2026-05-19-m9-*.md`), feat/m9 브랜치는 deleted, reflog 30일 또는 spec 기반 redo |

### 5.3 worktree 상태

✅ `git worktree list` → main 만 출력. v0.1.1 yagni-clean 부터는 worktree 사용 X — memory feedback `feedback_no_worktrees` 적용 ("워크트리 사용 금지, 메인 저장소에서 직접 branch checkout").

### 5.4 다음 세션이 자동 로드하는 메모리

자동 — `MEMORY.md` 의 `project_m10_complete` 가 최신 스냅샷 (v0.1.2 publish + 8 마일스톤 로드맵 표 + 브랜치 cleanup 까지 포함). `project_trusted_publishing_pattern` 는 v0.1.1+v0.1.2 양쪽 검증 후 패턴 안정성 confirmed. `project_m9_pivot_state` 는 historical (feat/m9 deleted). [[m10-phase4-partial]] / [[m10-pr-pending]] / [[m10-inflight-phase2-task21]] / [[m10-phase2-complete]] 는 STALE 표시.

## 6. 마일스톤 정렬

| # | 이름 | 상태 |
|---:|---|---|
| M0~M8 | v1 (뼈대 ~ 패키징 + i18n) | ✅ 완료 (main 머지) |
| M9 | 코드 서명 + 자동 업데이트 (GitHub releases) | ⚠️ implementation 완료 / **path pivot** (PyPI 채택, version/checker/banner/tray 일부 모듈 M10 Phase 2 cherry-pick), feat/m9 브랜치 deleted (2026-05-20), spec/plan 만 보존 |
| M10 | **PyPI 배포 + AssetCacheMCP rename** | ✅ 완료 ([PR #11](https://github.com/v0o0v/assetcache-mcp/pull/11) + [PR #12](https://github.com/v0o0v/assetcache-mcp/pull/12) main 머지); Phase 1 마이그레이션 helper 는 v0.1.1 yagni-clean |
| v0.1.1 | v0.0.1 마이그레이션 helper 제거 + 첫 Trusted Publishing OIDC 자동 publish | ✅ 완료 ([PR #14](https://github.com/v0o0v/assetcache-mcp/pull/14) + 32초 publish) |
| v0.1.2 | PyPI 페이지 정직성 patch (README/DESIGN/docs/CLAUDE stale 일괄 정리, classifiers 보강) + Trusted Publishing 2회째 자동 publish | ✅ 완료 ([PR #15](https://github.com/v0o0v/assetcache-mcp/pull/15) + 29초 publish) |
| **로드맵 brainstorm** | M11~M18 8 마일스톤 design + Reactive backlog ([roadmap-design.md](docs/superpowers/specs/2026-05-20-roadmap-design.md)) | ✅ 완료 (main `b3f8fe8`) |
| **M11** | Multi-backend LLM Architecture (Ollama+Gemini+Claude+OpenAI+OpenRouter+HF) | ✅ v0.2.0 publish 완료 ([PR #16](https://github.com/v0o0v/assetcache-mcp/pull/16) main 머지 `f68ef88`, [PyPI v0.2.0 Latest](https://pypi.org/project/assetcache-mcp/0.2.0/), [GitHub release v0.2.0](https://github.com/v0o0v/assetcache-mcp/releases/tag/v0.2.0)). 회귀 1079 → 1252 (+173 + 13 옵트인). 신규 의존성 4. Trusted Publishing 3회째 자동 (~30초). [verification](milestones/M11_verification.md) |
| **M11.1** | Gemini Batch API (50% 비용, 24h SLO) + /analyzing dashboard + M11 한계 해결 | ✅ 구현 완료 (feat/m11-1-gemini-batch-api 브랜치, **PR + v0.2.1 publish 대기**). 회귀 1252 → 1426 (+174 + 3 옵트인). 신규 의존성 0. [verification](milestones/M11_1_verification.md) |
| M12~M18 | 측정/Mac-Linux/원격 통신/Unity Editor/유사 검색/성능/분산 | 📋 미정 (사용자 결정) |

## 7. M10 후속 정리거리 (해결됨/잔존)

- ✅ M9 의 SignPath 신청 docs (`docs/SIGNPATH_APPLICATION.md` + `docs/CODE_SIGNING_POLICY.md`) — feat/m9 브랜치 2026-05-20 deleted (브랜치 cleanup), 향후 SignPath 채택 시 spec/plan (`docs/superpowers/{plans,specs}/2026-05-19-m9-*.md`) 기반 redo
- ✅ TestPyPI / 정식 PyPI entire-account scope token 2개 revoke 완료 (2026-05-20, 보안 정리)
- ✅ GitHub Actions Node.js 20 deprecation 경고 → v6 로 갱신 (PR #12)
- ✅ v0.0.1 마이그레이션 helper (Phase 1) yagni-clean — [PR #14](https://github.com/v0o0v/assetcache-mcp/pull/14) main 머지 (회귀 1103 → 1079, -24; version 0.1.0 → 0.1.1)
- ✅ v0.1.1 PyPI publish — Trusted Publishing (OIDC) 첫 자동 publish 검증 ✅ 32초 성공 ([run 26139260454](https://github.com/v0o0v/assetcache-mcp/actions/runs/26139260454)) + [GitHub release v0.1.1](https://github.com/v0o0v/assetcache-mcp/releases/tag/v0.1.1) 생성
- ✅ v0.1.2 PyPI publish — Trusted Publishing 자동 publish 2회째 ✅ 29초 성공 ([run 26141958223](https://github.com/v0o0v/assetcache-mcp/actions/runs/26141958223)) + [GitHub release v0.1.2](https://github.com/v0o0v/assetcache-mcp/releases/tag/v0.1.2) 생성. [PR #15](https://github.com/v0o0v/assetcache-mcp/pull/15) — README PyInstaller exe 섹션 제거 (release artifact 0건 거짓 안내), DESIGN/docs stale 명령어 (`python -m gah` / `game-asset-helper` → `assetcache`) 갱신, classifiers 보강 (Games/Entertainment + Sound/Audio), CLAUDE.md M10 worktree 안내 제거. 회귀 1079 그대로 (코드 변경 0)
- ✅ feat/m10-pypi-and-rename + feat/m9-code-signing-and-auto-update 브랜치 cleanup (2026-05-20) — 둘 다 deleted. M10 평행 implementation 의 핵심 기능 (`handle_pypi_update` slot) 은 main `_on_update_clicked` 로 동등 구현 검증 후. M9 는 spec/plan 만 보존 (`docs/superpowers/{plans,specs}/2026-05-19-m9-*.md`). 복구는 reflog 30일 이내
- ✅ M11~M18 로드맵 brainstorm + spec 작성 (2026-05-20, main `b3f8fe8`) — 8 마일스톤 정렬 + Reactive backlog. M11 (Multi-backend LLM Architecture) design 3/3 확정 (web research image+audio 6 backend 비교 포함). spec: [`docs/superpowers/specs/2026-05-20-roadmap-design.md`](./docs/superpowers/specs/2026-05-20-roadmap-design.md)
- 📋 M11 implementation 시작 자연 — detail design spec 작성 → writing-plans → `milestones/M11_plan.md` → TDD cycle

자세한 plan / spec / verification:

- [`milestones/M10_plan.md`](./milestones/M10_plan.md) — 5 Phase 상세
- [`milestones/M10_todo.md`](./milestones/M10_todo.md) — task 체크리스트 (모두 마크 완료)
- [`milestones/M10_verification.md`](./milestones/M10_verification.md) — 자동 + 수동 검증 시나리오 7건
- [`docs/superpowers/plans/2026-05-19-m10-pypi-and-rename.md`](./docs/superpowers/plans/2026-05-19-m10-pypi-and-rename.md) — implementation plan
- [`docs/superpowers/specs/2026-05-19-m10-pypi-and-rename.md`](./docs/superpowers/specs/2026-05-19-m10-pypi-and-rename.md) — design spec
