# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-20 (M10 완전 종료 + workflow Node.js 24 fix)
**마지막 완료 작업**: **M10 — v2 PyPI 1차 배포 + AssetCacheMCP rename** (Phase 0~5 모두 main 머지 완료)
**M10 결과**: [PyPI v0.1.0 Latest](https://pypi.org/project/assetcache-mcp/0.1.0/) + [GitHub release v0.1.0 Latest](https://github.com/v0o0v/assetcache-mcp/releases/tag/v0.1.0) + repo rename `v0o0v/assetcache-mcp`
**현재 브랜치**: `main` (HEAD = `7ba6551` workflow fix → `d9a3862` M10 PR #11 merge)
**다음 세션 작업**: 사용자 결정 — Mac/Linux 검증 / v0.1.1 patch / 사용자 피드백 대응 / Claude Desktop config 자동 마이그레이션

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가"를 한 번에 파악하도록 작성된 스냅샷이다.

## 1. 한 줄 요약

M10 (v2 — PyPI 1차 배포 + AssetCacheMCP rename + 마이그레이션) **완전 종료**. main `d9a3862` PR #11 + `7ba6551` PR #12 (workflow Node.js 24). **1103 passed + 1 skipped + 40 deselected**, MCP 20 도구. PyPI v0.1.0 publish 완료, Trusted Publishing (OIDC) 셋업 → 향후 tag push 한 줄로 자동 publish. GitHub repo rename `v0o0v/game-asset-helper` → `v0o0v/assetcache-mcp`. 사용자 데이터 폴더 `%APPDATA%\GameAssetHelper\` → `%APPDATA%\AssetCacheMCP\` 자동 마이그레이션 helper 제공 (배너 + CLI).

## 2. 검증된 사실 (M10 완료 시점)

자동 — `pytest -q` 결과 **1103 passed + 1 skipped + 40 deselected** (M10 +57, baseline 1046)

| Phase | 핵심 산출물 | 신규 테스트 |
|---|---|---:|
| 0 — rename mechanical | `src/gah/` → `src/assetcache/` + 모든 import / config / babel.cfg / spec / docs / `.po` 경로 | 0 (회귀만) |
| 1 — 마이그레이션 helper | `core/migration.py` (detect + MigrationRunner async copy/move + rollback + 디스크 검사) + `web/routers/migration.py` + SSE + `_migration_banner.html` + CLI `--migrate=copy\|move` + i18n msgid 10건 | +21 |
| 2 — PyPI 알림 (M9 cherry-pick) | `core/updater/version.py` (semver + classmethod + ordering) + `checker.py` (PyPI JSON API + ETag 캐시 + 24h PollingLoop) + `pip_command.py` (pipx/uv/pip 분기) + `web/routers/updates.py` 단순화 + `_pypi_update_banner.html` + `tray.TrayController` + `_TrayBridge` Qt Signal cross-thread + i18n msgid 4건 | +17 |
| 3 — docs + i18n catalog + verification | README/CLAUDE/HANDOFF/DESIGN 표기 일괄 갱신 + `tests/test_locale_assetcache_msgid.py` (5 msgid × 2 lang = 10 instance) + `milestones/M10_verification.md` (수동 시나리오 7건) | +10 |
| 4 — PyPI 패키지 + 빌드 + 배포 | `pyproject.toml` name=`assetcache-mcp` + version=0.1.0 + scripts + classifiers + package-data + `main_mcp()` entry + `python -m build` + TestPyPI + 정식 PyPI + Trusted Publishing (OIDC) + GitHub Actions workflow | 0 (배포 검증) |
| 5 — 마일스톤 wrap-up | PR #11 머지 + v0.1.0 GitHub release publish + repo rename + token revoke + cleanup PR | 0 |
| 후속 fix | workflow Node.js 24 호환 (`actions/checkout@v6` + `actions/setup-python@v6`, PR #12) | 0 |
| **M10 전체** | **MCP 20 도구 그대로, 신규 의존성 0 (run-time), dev `build` + `twine` 추가** | **+57** |

수동 — 시나리오 1~7 의 자동 가능 부분 (rename 회귀 / wheel local smoke / TestPyPI / 정식 PyPI install / Trusted Publishing workflow) 검증 통과. 시나리오 1~5 의 사용자 직접 부분 (트레이 + 배너 + 마이그레이션 GUI) 은 [`milestones/M10_verification.md`](./milestones/M10_verification.md) §2 참고.

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
| 마이그레이션 소스 | `%APPDATA%\GameAssetHelper\` (v0.0.1 사용자 잔존, `.migrated_from_v001` 마커로 idempotent) |
| **MCP 도구 수** | 20 도구 (M10 신규 0) |
| PyPI 패키지 | `assetcache-mcp` 0.1.0 (https://pypi.org/project/assetcache-mcp/0.1.0/) |
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

→ `1103 passed, 1 skipped, 40 deselected` 확인 후 다음 작업 진입.

## 5. 다음 세션 진입 절차 (M10 완료 후 — 다음 작업 후보)

### 5.1 후보 옵션 (사용자 결정)

| 후보 | 내용 | 우선 |
|---|---|---|
| Mac / Linux 검증 | PyPI 패키지의 cross-platform 호환 정식 검증 (M11 후보) | 사용자 수요에 따라 |
| v0.1.1 patch | 발견된 bug fix 누적 + Trusted Publishing 첫 자동 publish 검증 | 자연스럽게 |
| 사용자 피드백 수집 | [PyPI download 통계](https://pypistats.org/packages/assetcache-mcp) + [GitHub Issues](https://github.com/v0o0v/assetcache-mcp/issues) 모니터링 | 1주 후 |
| Claude Desktop config 자동 마이그레이션 | v0.0.1 사용자가 `mcpServers` 의 `python -m gah --mcp` → `assetcache-mcp` 자동 갱신 helper | 사용자 보고 시 |

### 5.2 worktree 정리 (선택)

main 머지 후 `claude/brave-tesla-80fb0e` worktree 는 사용 끝남. 정리:

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
git worktree remove .claude/worktrees/brave-tesla-80fb0e
```

⚠️ worktree branch `claude/brave-tesla-80fb0e` 에 main 보다 ahead 인 `0009a10` (Task 5.2/5.3 todo 마크) 가 있었지만 본 cleanup PR 에서 동일 내용이 main 으로 반영됨. branch 정리 안전.

### 5.3 다음 세션이 자동 로드하는 메모리

자동 — `MEMORY.md` 의 `project_m10_complete` 가 최신 스냅샷. [[m10-phase4-partial]] / [[m10-pr-pending]] / [[m10-inflight-phase2-task21]] / [[m10-phase2-complete]] 는 STALE 표시.

## 6. 마일스톤 정렬

| # | 이름 | 상태 |
|---:|---|---|
| M0~M8 | v1 (뼈대 ~ 패키징 + i18n) | ✅ 완료 (main 머지) |
| M9 | 코드 서명 + 자동 업데이트 (GitHub releases) | ⚠️ implementation 완료 / **머지 보류** (PyPI 채택으로 path pivot, version/checker/banner/tray 일부 모듈은 M10 Phase 2 cherry-pick) |
| M10 | **PyPI 배포 + AssetCacheMCP rename + 마이그레이션** | ✅ 완료 ([PR #11](https://github.com/v0o0v/assetcache-mcp/pull/11) + [PR #12](https://github.com/v0o0v/assetcache-mcp/pull/12) main 머지) |
| M11+ | Mac/Linux 검증 + v0.1.1 patch + 사용자 피드백 대응 | 📋 미정 |

## 7. M10 후속 정리거리 (해결됨/잔존)

- ✅ M9 의 SignPath 신청 docs (`docs/SIGNPATH_APPLICATION.md` + `docs/CODE_SIGNING_POLICY.md`) — `feat/m9` 브랜치 보존, 향후 SignPath 채택 시 복귀 가능
- ✅ TestPyPI / 정식 PyPI entire-account scope token 2개 revoke 완료 (2026-05-20, 보안 정리)
- ✅ GitHub Actions Node.js 20 deprecation 경고 → v6 로 갱신 (PR #12)
- 📋 (선택) Mac / Linux 정식 검증 — PyPI 흐름에서 가능하지만 별도 마일스톤
- 📋 (선택) Claude Desktop config 의 `mcpServers` 자동 마이그레이션 helper
- 📋 (선택) v0.1.1 patch — 사용자 피드백 누적 시 자동 publish (Trusted Publishing) 첫 검증

자세한 plan / spec / verification:

- [`milestones/M10_plan.md`](./milestones/M10_plan.md) — 5 Phase 상세
- [`milestones/M10_todo.md`](./milestones/M10_todo.md) — task 체크리스트 (모두 마크 완료)
- [`milestones/M10_verification.md`](./milestones/M10_verification.md) — 자동 + 수동 검증 시나리오 7건
- [`docs/superpowers/plans/2026-05-19-m10-pypi-and-rename.md`](./docs/superpowers/plans/2026-05-19-m10-pypi-and-rename.md) — implementation plan
- [`docs/superpowers/specs/2026-05-19-m10-pypi-and-rename.md`](./docs/superpowers/specs/2026-05-19-m10-pypi-and-rename.md) — design spec
