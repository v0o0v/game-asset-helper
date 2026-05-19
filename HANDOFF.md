# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-19 (M8 완료 + 수동 검증 통과 + 후속 patch 3건 main 누적)
**마지막 완료 마일스톤**: **M8 — 패키징 + i18n** — ✅ 완료 (수동 검증 통과)
**현재 브랜치**: `main` (origin/main 과 sync, working tree clean, 마지막 commit `4971232`)
**다음 작업**: **v1 release** (GitHub release + `GameAssetHelper.exe` 업로드) 또는 **v2 brainstorming**

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가"를 한 번에 파악하도록 작성된 스냅샷이다.

## 1. 한 줄 요약

M8 (패키징 + i18n) ✅ 완료 + 사용자 수동 검증 통과. PR #9 main 머지 + 후속 fix 3건 (PR #10 + main fast-forward 2 commit). 빌드된 `dist/GameAssetHelper.exe` (308 MB, --onefile + --noconsole) 실 부팅 검증 — port 9874 + HTTP 200 76ms + 한국어 i18n 정상 렌더. pytest **1046 passed + 1 skipped + 40 deselected**. MCP **20 도구**. 신규 의존성 2 (Babel>=2.14, pyinstaller>=6 dev). 다음 = **v1 release 또는 v2 brainstorming**.

수동 검증 시나리오는 [`milestones/M8_verification.md`](./milestones/M8_verification.md) 참고.

## 2. 검증된 사실 (M8 완료)

자동 — `pytest -q` 결과 **1046 passed + 1 skipped + 40 deselected**

| Phase | 핵심 산출물 | 신규 테스트 |
|---|---|---:|
| 0 — 스캐폴딩 | 의존성 + Config 신규 필드 (ui_language/ui_theme) + autostart 스켈레톤 | +5 |
| 1 — i18n 인프라 | `_t()` gettext + LocaleMiddleware 5단계 + app.py 통합 | +14 |
| 2 — 문자열 추출 + 번역 | babel.cfg + 159건 msgid + ko.po + en.po + .mo 컴파일 | +2 |
| 3 — 설정 페이지 + 다크모드 | /settings GET+POST + 헤더 테마 토글 + CSS data-theme | +9 |
| 4 — autostart | winreg HKCU\\...\\Run + 트레이 메뉴 + /api/autostart | +9~10 |
| 5 — 빌드 | generate_tray_ico.py + tray.ico + gah.spec + smoke + README | +4 |
| 6 — 검증 + DRY | SUPPORTED 통합 (locale_middleware→i18n) + 문서 마감 | 0 |
| **M8 전체** | **MCP 20 도구 그대로, 신규 의존성 2** | **+44** |

`pytest -m mcp_integration -v` — 2/2 (**20 도구** 확인).

## 3. 환경 (재현용)

| 항목 | 값 |
|---|---|
| OS | Windows 10 |
| Python | python.org 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\python.exe`) |
| venv | `C:\Users\v0o0v\.venvs\gah\` |
| 작업 폴더 | `D:\ClaudeCowork\game-asset-helper\game-asset-helper\` |
| 런타임 데이터 | `C:\Users\v0o0v\AppData\Roaming\GameAssetHelper\` |
| 라이브러리 루트 | `%APPDATA%\GameAssetHelper\library\` |
| 메타 DB | `%APPDATA%\GameAssetHelper\metadata.db` (WAL, `unity_imports` + `projects` + `asset_usage` M7 에서 확장) |
| **M7: unity_import 패키지** | `src/gah/core/unity_import/` (types/cache_paths/unitypackage/scanner/importer/remote_optin) |
| **M8: i18n 카탈로그** | `src/gah/web/locale/ko/LC_MESSAGES/messages.mo` + `en/` (Babel gettext) |
| **M8: 빌드 스펙** | `gah.spec` (PyInstaller --onefile) + `scripts/generate_tray_ico.py` |
| **MCP 도구 수** | 20 도구 (M7 이후 그대로) |

**금기**: Microsoft Store Python, Cowork 작업 폴더 내부 venv.

M8 신규 의존성: `Babel>=2.14` (런타임), `pyinstaller>=6` (dev).

```powershell
pip install -e D:\ClaudeCowork\game-asset-helper\game-asset-helper[dev]
```

## 4. 새 세션에서 바로 이어가는 방법

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
git status
```

→ `On branch main`, `up to date with 'origin/main'`, working tree clean. 마지막 commit `4971232`.

```powershell
pytest -q
```

→ `1046 passed, 1 skipped, 40 deselected`.

## 5. 다음 세션 진입 절차 (v1 release 또는 v2)

### 5.1 환경 복원 + 회귀

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
git status
```

→ `On branch main`, working tree clean.

```powershell
pytest -q
```

→ `1046 passed, 1 skipped, 40 deselected`.

### 5.2 다음 결정 (사용자)

1. **v1 release** — `pyinstaller gah.spec` → `dist/GameAssetHelper.exe` (308 MB, 검증 완료) 를 GitHub release 페이지에 업로드. SmartScreen 안내 포함.
2. **v2 brainstorming** — v2 미룸 항목 (Pack/프로젝트 풍부 UX, E2E, 추가 언어, 인스톨러, 코드 서명 등) + `superpowers:brainstorming` 으로 설계.

### 5.3 PyInstaller 빌드 (이미 검증됨)

수동 검증 통과 — `dist/GameAssetHelper.exe --tray` 가 트레이 + WebServer (port 9874) + 한국어 i18n + 다크모드 + autostart 모두 정상 동작 확인.

빌드 절차 (release 산출 시):

```powershell
pybabel compile -d src/gah/web/locale
```

```powershell
python scripts/generate_tray_ico.py
```

```powershell
pyinstaller gah.spec
```

산출: `dist/GameAssetHelper.exe` (~308 MB, --onefile + --noconsole).

### 5.4 다음 세션이 자동 로드하는 메모리

- `project_m8_complete.md` — M8 완료 스냅샷 + 수동 검증 통과 + 후속 fix 3건 + v1 release/v2 결정 사항
- `project_m8_starting_state.md` — STALE (M8 완료, project_m8_complete 참조)
- `feedback_manual_verification_fixes.md` — 수동 검증 중 발견 fix 는 별도 브랜치 누적 + 사용자가 push/PR/머지 (이번 세션에 정립)

## 6. 마일스톤 정렬 (v1 완료)

| # | 이름 | 일정 | 상태 |
|---:|---|---:|---|
| M5 | 웹 GUI 전환 + 리디자인 + Claude pick | 5.5주 | ✅ 완료 |
| M6 | 시트 분석 + 애니메이션 | 1주 | ✅ 완료 |
| M7 | Unity Asset Store 임포트 | 1주 | ✅ 완료 |
| **M8** | **패키징 + i18n** | **1주** | **✅ 완료** |

v1 전체 완료. 총 일정 ≈ 18.5주.

## 7. 알려진 한계 / v2 보류 항목

- SmartScreen 경고 (코드 서명 없음 — v2)
- exe 크기 308 MB (실측, CLIP 가중치는 첫 실행 시 다운로드라 빌드에 미포함)
- 빌드된 exe 첫 부팅 시 Ollama cold-start + CLIP 모델 init 으로 1~2분 소요 (M2.1 알려진 트레이드오프)
- publisher 패널 실제 HTTP 구현 (v2 — 현재 skeleton 만)
- 자동 동기화 스케줄러 (v2)
- 캐시에서 사라진 .unitypackage 자동 제거 (v2)
- 다중 캐시 경로 (v2)
- UPM .tgz 임포트 (v2)
- get_active_project / set_active_project / get_project_preferences MCP 도구 (v2)
- PSD/TGA 확장자 임포트 (v2)
- 임포트 완료 후 unity_imports 자동 되돌림 (v2)
- 라이브러리 카드 직접 피드백 입력 UI (v2)
- Pack/프로젝트 풍부 UX (v2)
- Playwright E2E 테스트 (v2)
- 추가 언어 ja/zh (v2)
- MSI/NSIS 인스톨러 (v2)
- 자동 업데이트 (v2)
- 트레이 알림 (v2)
