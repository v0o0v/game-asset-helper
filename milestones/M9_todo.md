# M9 — TODO 체크리스트

> 본 todo 는 [`docs/superpowers/plans/2026-05-19-m9-code-signing-and-auto-update.md`](../docs/superpowers/plans/2026-05-19-m9-code-signing-and-auto-update.md) 의 phase 진행 상황을 마일스톤 사이클 형식으로 추적.

## Phase 0 — SignPath 신청 + 빌드 가이드

- [ ] Task 1 — SignPath Foundation 신청 + `docs/RELEASE_BUILD_GUIDE.md` 7단계 절차

## Phase 1 — Updater 백엔드: Checker + Version

- [ ] Task 2 — Config `[update]` 섹션 (release_repo / check_interval_hours / enabled) + 6 tests
- [ ] Task 3 — `core/updater/version.py` semver-lite parse + compare + 9 tests
- [ ] Task 4 — `core/updater/checker.py` UpdateChecker.check_once (GitHub API 단발) + 9 tests
- [ ] Task 5 — `core/updater/checker.py` PollingLoop + app.py 통합 (부팅 시 thread 시작) + 3 tests

## Phase 2 — Updater 백엔드: Downloader + Installer

- [ ] Task 6 — `core/updater/downloader.py` UpdateDownloader (httpx stream + SHA256) + 8 tests
- [ ] Task 7 — `core/updater/installer.py` UpdateInstaller STEP 1 (rename/move + 롤백) + 4 tests
- [ ] Task 8 — UpdateInstaller STEP 2 (`--complete-update` detached spawn) + 3 tests
- [ ] Task 9 — UpdateInstaller STEP 3 (wait_for_pid + cleanup + tray restart) + 5 tests
- [ ] Task 10 — `__main__.py --complete-update --old-pid` routing + 2 tests

## Phase 3 — Web UI 통합

- [ ] Task 11 — `/api/updates/{check,start,status}` 라우터 + SSE + 8 tests
- [ ] Task 12 — `_update_banner.html` partial + base.html + `/api/updates/install` + 2 tests
- [ ] Task 13 — i18n msgid 9건 + ko/en .po 번역 + .mo 컴파일

## Phase 4 — 트레이 통합

- [ ] Task 14 — `tray.py` 동적 메뉴 (Qt signal/slot, "업데이트 확인" + "vX.X.X 업데이트 가능") + 4 tests

## Phase 5 — 검증 + 문서 + 첫 서명 release

- [ ] Task 15 — `milestones/M9_verification.md` 수동 검증 시나리오 6건
- [ ] Task 16 — `README.md` §배포 SignPath 서명 + 자동 업데이트 흐름 추가
- [ ] Task 17 — v0.0.2 dogfood release (version bump + release notes + SignPath 서명 + tag + GH release + 시나리오 1 dogfood 실행)
