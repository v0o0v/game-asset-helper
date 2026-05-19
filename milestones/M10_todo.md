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

## Phase 2 — M9 cherry-pick (~1.5일, +15 tests)

- [ ] Task 2.1 — feat/m9 에서 `core/updater/__init__.py` + `version.py` + `test_updater_version.py` cherry-pick + import path 갱신 + 9 tests pass
- [ ] Task 2.2 — `core/updater/checker.py` PyPI JSON API + ETag 캐시 + PollingLoop + 6 tests
- [ ] Task 2.3 — `core/updater/pip_command.py` 환경 분기 (pipx/uv/pip) + 3 tests
- [ ] Task 2.4 — `web/routers/updates.py` 단순화 (/api/updates/check 만) + 2 tests
- [ ] Task 2.5 — `_pypi_update_banner.html` 단순화 + base.html + CSS
- [ ] Task 2.6 — `tray.py` 동적 메뉴 + Qt Signal cross-thread + 4 tests
- [ ] Task 2.7 — PyPI 알림 i18n msgid 4건 ko/en + `.mo` 재컴파일

## Phase 3 — 문서 + verification (~1일, +5 tests)

- [ ] Task 3.1 — README + CLAUDE + HANDOFF + DESIGN AssetCacheMCP 표기 일괄 갱신
- [ ] Task 3.2 — `tests/test_locale_assetcache_msgid.py` parametrize (5 msgid × ko/en) + 5~10 tests pass
- [ ] Task 3.3 — `milestones/M10_verification.md` 수동 검증 시나리오 7건 (Phase 0 회귀 / 마이그레이션 / PyPI 알림 / CLI / wheel / TestPyPI / PyPI 정식)

## Phase 4 — PyPI 배포 (~1일)

- [ ] Task 4.1 — `pyproject.toml` name="assetcache-mcp" + version=0.1.0 + scripts + classifiers + urls + package-data + editable install + 회귀
- [ ] Task 4.2 — `main_mcp()` entry point 추가 (assetcache-mcp console script)
- [ ] Task 4.3 — `python -m build` + 별도 venv 로컬 wheel smoke (`assetcache --version`)
- [ ] Task 4.4 — `.github/workflows/publish.yml` tag v\* trigger + PYPI_API_TOKEN secret
- [ ] Task 4.5 — TestPyPI 업로드 + `pipx install --index-url ...` 검증 (사용자 수동)
- [ ] Task 4.6 — PyPI 정식 업로드 + GitHub repo `v0o0v/assetcache-mcp` 린네임 + v0.1.0 tag/release publish (사용자 수동)

## Phase 5 — 마일스톤 wrap-up

- [ ] Task 5.1 — `milestones/M10_plan.md` + `M10_todo.md` 정합성 검증 (모든 task 완료 표시)
- [ ] Task 5.2 — `feat/m10` → `main` PR 작성 + 사용자 review + main 머지
