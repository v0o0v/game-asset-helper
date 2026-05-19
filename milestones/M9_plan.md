# M9 — 코드 서명 + 자동 업데이트 (마일스톤 plan)

> 본 문서는 [`docs/superpowers/plans/2026-05-19-m9-code-signing-and-auto-update.md`](../docs/superpowers/plans/2026-05-19-m9-code-signing-and-auto-update.md) 의 마일스톤 사이클 표지다. 실제 구현 task 는 superpowers plan 참조.
>
> spec: [`docs/superpowers/specs/2026-05-19-m9-code-signing-and-auto-update-design.md`](../docs/superpowers/specs/2026-05-19-m9-code-signing-and-auto-update-design.md)

## 목표

- **SignPath Foundation OSS 무료 코드 서명** 으로 SmartScreen 경고 영구 해결
- **자체 구현 in-app updater** — GitHub Releases API 24h 폴링 + 트레이/웹 UI 양방 알림
- **알림만 정책** — 사용자 동의 후 다운로드 + SHA256 검증 + swap + 재시작
- **Self `--complete-update` mode** — 외부 stub 파일 없이 단일 exe 안에 swap 로직

## 산출물

| Phase | Task | 산출물 | 신규 테스트 |
|---|---|---|---:|
| 0 | 1 | SignPath 신청 + `docs/RELEASE_BUILD_GUIDE.md` | 0 |
| 1 | 2~5 | Config `[update]` 섹션, semver-lite, UpdateChecker, PollingLoop + app.py 통합 | +24 |
| 2 | 6~10 | UpdateDownloader, UpdateInstaller (STEP 1~3), ctypes wait_for_pid, `--complete-update` arg | +19 |
| 3 | 11~13 | `/api/updates/{check,start,status,install}` + `_update_banner.html` + ko/en i18n | +10 |
| 4 | 14 | tray.py 동적 메뉴 (`signal/slot`) | +4 |
| 5 | 15~17 | M9_verification.md + README §배포 + v0.0.2 dogfood release | 0 |
| **합계** | | **MCP 20 도구 그대로, 신규 의존성 0** | **+57 (over-spec +7, OK)** |

## 완료 조건

- [ ] `pytest -q` 1109 passed (1046 + 63), 회귀 0
  - 주: 실제 합계는 over-spec +7 가능. spec 의 +50 추정과 +63 실제 사이 차이는 Config 테스트 (+6) + SSE/banner 통합 테스트 (+2) + Swap 보강 (+5) 누적.
- [ ] SignPath Foundation 자격 심사 통과
- [ ] `dist/GameAssetHelper.exe` SignPath 서명 + 다운로드 시 SmartScreen 경고 없음 (수동 검증)
- [ ] v0.0.2 release 가 GH 에 publish + asset 2개 (exe + sha256) 첨부
- [ ] M9_verification.md 시나리오 6건 모두 통과 — 특히 시나리오 1 의 v0.0.1 → v0.0.2 실 swap

## 일정 추정

- ~3주 (Phase 1~5 구현 + 검증)
- + SignPath 심사 대기 (수일~수주, 병행 가능)

## 의존성

신규 0건. 기존: `httpx`, `FastAPI`, `PySide6`, `ctypes` (stdlib), Babel (M8), PyInstaller (M8).

## 브랜치

`feat/m9-code-signing-and-auto-update` (사용자가 plan 실행 직전 생성). spec commit `8dfb316` 은 main 에 이미 있음 (이 brancg 의 부모).
