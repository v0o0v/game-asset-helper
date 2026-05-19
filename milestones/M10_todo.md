# M10 — TODO 체크리스트

> 본 todo 는 [`docs/superpowers/plans/2026-05-19-m10-pypi-and-rename.md`](../docs/superpowers/plans/2026-05-19-m10-pypi-and-rename.md) 의 phase 진행 상황을 마일스톤 사이클 형식으로 추적.

## Phase 0 — rename mechanical (~1.5일)

- [ ] Task 0.1 — `git mv src/gah src/assetcache` + import 전수 교체 (~150 파일) + `gah.spec` → `assetcache.spec` + pyproject 패키지 경로 갱신 + 회귀 1047 passed
- [ ] Task 0.2 — `config.APP_NAME = "AssetCacheMCP"` + `tray.py` 브랜딩 + `base.html` title/h1 + tests/ fixture 어설션 갱신
- [ ] Task 0.3 — ko/en `.po` "Game Asset Helper" → "AssetCacheMCP" + `.mo` 재컴파일
- [ ] Task 0.4 — 전수 grep `from gah\|import gah` = 0 hits 검증 + pytest 1047 passed + MCP integration 통과 + 트레이 부팅 스모크 (수동)

## Phase 1 — 데이터 폴더 마이그레이션 helper (~1일, +21 tests)

- [x] Task 1.1 — `core/migration.py` `detect_v001_candidate` + `is_already_migrated` + `MigrationCandidate` dataclass + `AppPaths.legacy_data_dir` 필드 + 5 tests
- [x] Task 1.2 — `MigrationRunner` async copy/move + 디스크 공간 검사 + rollback + 마커 파일 + 5 tests
- [x] Task 1.3 — `rewrite_paths_after_migration` (config.toml 만; metadata.db 는 assets.path 가 library_root 기준 상대경로라 무수정) + 3 tests
- [x] Task 1.4 — `web/routers/migration.py` `/api/migration/{status,run,progress,dismiss}` + 3 tests
- [x] Task 1.5 — `_migration_banner.html` Alpine + SSE + base.html 통합 + CSS
- [x] Task 1.6 — CLI `--migrate=copy|move` 헤드리스 + 2 tests
- [x] Task 1.7 — 마이그레이션 배너 i18n msgid 10건 ko/en + `.mo` 재컴파일

### Phase 1 reviewer / robustness 후속 fix (history 에 누적)

- [x] Task 1.4 reviewer Critical — asyncio.Task GC + SSE JSON safety (a217f0d)
- [x] Task 1.3 reviewer Important — LIKE escape + OSError catch + docstring (8814f42)
- [x] 검토 — Task 1.3 db rewrite 제거 (assets.path 상대경로 인지, a51a399)
- [x] worktree editable install 정합성 — pyproject pytest pythonpath=src (1ce0322)
- [x] Task 1.2 fix — ensure_dirs 가 만든 빈 target 과 충돌하던 copytree/move (b949632)
- [x] Task 1.1 fix — detect 가 ensure_dirs scaffolding 을 데이터로 오인하던 결함 (52bb928)

## Phase 2 — M9 cherry-pick (~1.5일, +24 tests 실제 = +15 plan + 2 Version 확장 + 4 tray + 미스 3 보정)

- [x] Task 2.1 — feat/m9 에서 `core/updater/__init__.py` + `version.py` + `test_updater_version.py` cherry-pick + import path 갱신 + 9 tests pass (`2702ce3`, 1067 → 1076)
- [x] Task 2.2 — `core/updater/checker.py` PyPI JSON API + ETag 캐시 + PollingLoop + 6 tests (`dd2eeee` + 사전 `0b39460` Version.parse classmethod + ordering dunders + 2 tests, 1076 → 1084)
- [x] Task 2.3 — `core/updater/pip_command.py` 환경 분기 (pipx/uv/pip) + 3 tests (`09f9c61`, 1084 → 1087)
- [x] Task 2.4 — `web/routers/updates.py` 단순화 (/api/updates/check 만) + 2 tests + Version.__str__ 4 라인 (`15f9cd8`, 1087 → 1089)
- [x] Task 2.5 — `_pypi_update_banner.html` (영어 msgid) + base.html include + main.css (`bc4b3fd`, 1089 유지)
- [x] Task 2.6 — `tray.py` 동적 메뉴 + Qt Signal cross-thread (`_TrayBridge`) + 4 tests (`c7359f6`, 1089 → 1093)
- [x] Task 2.7 — PyPI 알림 i18n msgid 4건 (`"available"` / `"Release notes"` / `"v{version} update available →"` / `"Upgrade command copied to clipboard"`) ko/en + `.mo` 재컴파일 (`d694bdf`, 1093 유지)

### Phase 2 후속 fix (history 누적)

- [x] babel.cfg path 갱신 — `src/gah/` → `src/assetcache/` (Phase 0 rename 누락, `b5d24b0`)

## Phase 3 — 문서 + verification (+10 tests, ~1일)

- [x] Task 3.1 — README + CLAUDE + HANDOFF + DESIGN AssetCacheMCP 표기 일괄 갱신 (`5eef1a8`)
- [x] Task 3.2 — `tests/test_locale_assetcache_msgid.py` parametrize (5 msgid × ko/en) + 10 instance (`ced16fb`, 1093 → 1103)
- [x] Task 3.3 — `milestones/M10_verification.md` 수동 검증 시나리오 7건 (`6569034`)

## Phase 4 — PyPI 배포 (~1일, 0 자동 신규 테스트)

- [x] Task 4.1 — `pyproject.toml` name="assetcache-mcp" + version=0.1.0 + scripts + classifiers + urls + package-data + editable install + 회귀 (`8f8af41`)
- [x] Task 4.2 — `main_mcp()` entry point 추가 (`assetcache-mcp` console script — `072f712`)
- [x] Task 4.3 — `python -m build` + 별도 venv 로컬 wheel smoke (`assetcache --version` = `assetcache-mcp 0.1.0`) + `__version__` 0.1.0 sync (`28a257e`, dist 298KB)
- [x] Task 4.4 — `.github/workflows/publish.yml` tag v\* trigger + PYPI_API_TOKEN secret + README dev 안내 (`d2a8079`)
- [x] Task 4.5 — TestPyPI 업로드 + `pip install --no-deps --index-url ...` 검증 (`cd03b3d`, 사용자 token + Claude .pypirc + twine upload + 별도 venv install + module import + `__version__=0.1.0` + `pip show` 메타데이터 정상)
- [x] Task 4.6 — 정식 PyPI 업로드 + GitHub repo rename + v0.1.0 release draft (`fda1a08` + `74bc84d` + `e6fa00b`, 정식 PyPI publish + assetcache.exe --version 정상 + Trusted Publishing 셋업 + workflow 29초 success + GitHub release draft 생성)

### Phase 4 후속 fix / 전환 (history 누적)

- [x] Trusted Publishing (OIDC) 전환 — `.github/workflows/publish.yml` 의 `password:` 라인 삭제 + `skip-existing: true` 옵션 + README §배포 갱신 (`74bc84d`)

## Phase 5 — 마일스톤 wrap-up

- [x] Task 5.1 — `milestones/M10_plan.md` + `M10_todo.md` 정합성 검증 (이 commit 으로 일괄 마크)
- [ ] **Task 5.2 — `claude/brave-tesla-80fb0e` → `main` PR 생성 + 사용자 review + main 머지 (사용자 수동)**
- [ ] **Task 5.3 — v0.1.0 GitHub release draft → publish (사용자 수동, release notes 검토 후)**
