# M8 — 패키징 + i18n (설계 spec)

> 본 문서는 [M5 spec](./2026-05-17-m5-web-gui-and-library-redesign.md) / [M6 spec](./2026-05-18-m6-sheet-and-animation-design.md) / [M7 spec](./2026-05-18-m7-unity-asset-store-import-design.md) 과 같은 형식이며, [`CLAUDE.md`](../../../CLAUDE.md) §2 / [`DESIGN.md`](../../../DESIGN.md) §11 Milestone 8 의 한 줄 항목을 작업 단위까지 풀어 적은 1차 결정 문서다. 본 spec 의 결정을 [`milestones/M8_plan.md`](../../../milestones/M8_plan.md) 가 phase / task 로 옮기고, 실제 구현은 plan 의 체크박스를 따라간다.
>
> **작성일**: 2026-05-19
> **타깃 마일스톤**: M8 (M7 완료 후, v1 최종 마일스톤)
> **예상 소요**: ~1주 (~6일)
> **누적 자동 테스트 baseline**: M7 종료 시 1011 passed + 1 skipped + 40 deselected. M8 종료 시 **~1050 passed** 목표.

---

## 1. 한 줄 요약

(1) **PyInstaller 단일 `.exe` 빌드** — 일반 사용자가 더블클릭만으로 GAH 를 실행할 수 있는 배포 산출물. `--onefile` + torch GPU/CPU 통합 wheel + CLIP 가중치는 첫 실행 시 다운로드. (2) **웹 UI i18n (ko/en)** — M5 의 `_t()` passthrough 를 Babel `gettext` 백엔드로 본격화, Jinja2 템플릿의 한글 hardcode 를 `{{ _("...") }}` 로 추출, locale 결정 5단계 미들웨어 도입. (3) **다크/라이트 모드 수동 토글** — M5 의 `prefers-color-scheme` 자동에 추가로 사용자가 헤더 토글로 강제 가능, `localStorage` 영속화. (4) **Windows 자동 시작 토글** — `HKCU\...\Run` 레지스트리에 등록/해제, `Config.autostart` (이미 존재) 캐시 + 새 `/settings` 페이지 + 트레이 메뉴 통합. **신규 의존성 2** (`Babel>=2.14` 런타임, `pyinstaller>=6` dev).

## 2. 배경 / 발견 사항 (코드베이스 실측)

- **`src/gah/web/i18n.py` 가 M5 부터 존재** — `_t(text) -> text` passthrough + `setup_jinja_i18n(env)` 가 `env.globals["_"]` 에 등록. 본 M8 가 `_t()` 를 `gettext.translation(...).gettext` 로 위임하도록 본격화한다.
- **`Config.autostart: bool = False` 가 M0 부터 존재** ([`src/gah/config.py:101`](../../../src/gah/config.py)). 본 M8 는 이 필드를 **활용**하고, 실제 레지스트리 동기화 로직 (`platform/autostart.py`) 만 신규 추가한다.
- **`Config.description_language: str = "ko"` 는 이미 존재** ([`src/gah/config.py:118`](../../../src/gah/config.py))이지만 이건 **분석 출력 (Gemma description) 언어**다. UI 언어와 별개이므로 본 M8 는 **신규 `ui_language` 필드**를 도입한다.
- **현재 모든 Jinja2 템플릿은 한글 hardcode** — `src/gah/web/templates/**/*.html` (M5 ~50 파일, M7 +6 파일). 이 중 사용자 노출 문자열을 `{{ _("...") }}` 로 추출한다. 동적 데이터 (라벨 이름, 팩 이름) 는 그대로 둔다.
- **`gah --tray` 가 단일 엔트리포인트** — `python -m gah --tray` 가 SingleInstance lock 후 트레이 + uvicorn + 브라우저 자동 열기. PyInstaller spec 도 같은 엔트리를 호출.
- **`src/gah/web/static/css/` 에 다크모드 CSS 가 이미 `@media (prefers-color-scheme: dark)` 기반으로 존재** (M5). 본 M8 는 `<html data-theme="dark">` 강제 모드를 추가하고 기존 미디어쿼리는 `data-theme="auto"` 또는 미설정일 때만 동작하도록 조정한다.
- **`_global_header.html` 이 M7 부터 존재** ([`src/gah/web/templates/_global_header.html`](../../../src/gah/web/templates/_global_header.html)) — 활성 프로젝트 드롭다운, 사이드바 토글 버튼 위치. 본 M8 의 테마 토글 + 언어 셀렉터는 여기에 추가.
- **MCP 도구 20개** ([`src/gah/mcp/server.py`](../../../src/gah/mcp/server.py)). 본 M8 는 MCP 도구 추가/변경 없음 — 패키징/UI 마감 마일스톤.
- **사이드바 메뉴**는 M5 의 4 페이지 (library/packs/labels/search) + M7 의 unity-asset-store + projects + `/settings` (M0 부터 placeholder). 본 M8 는 `/settings` 페이지를 실제로 채운다.
- **트레이 메뉴** = "메인 창 열기" + "종료" 만. 본 M8 는 "자동 시작" 체크박스를 추가.
- **신규 의존성**: `Babel>=2.14` (런타임 `gettext.translation` + 빌드 도구 `pybabel`), `pyinstaller>=6` (dev only, exe 빌드).

## 3. 시나리오 (M8 종료 시 동작)

### 3.1 일반 사용자가 `.exe` 더블클릭

1. 사용자가 GitHub release 페이지에서 `GameAssetHelper.exe` (~1.5-2 GB) 다운로드.
2. 더블클릭 → Windows SmartScreen 경고(서명 없는 빌드라 "추가 정보" → "실행") → 백그라운드에서 압축 해제 ~15-30s.
3. 트레이 아이콘 표시 + 기본 브라우저에서 `http://127.0.0.1:9874` 자동 열림.
4. 라이브러리 비어 있음 (`%APPDATA%\GameAssetHelper\library\`). 첫 검색 시 CLIP 가중치 다운로드 (~600 MB, 약 5분, `%APPDATA%\GameAssetHelper\cache\clip\`).
5. 이후 모든 동작은 M0~M7 와 동일.

### 3.2 영어 사용자 진입

1. 브라우저 `Accept-Language: en-US,en;q=0.9` 헤더로 진입.
2. `LocaleMiddleware` 가 결정: URL `?lang=` 없음 → 쿠키 `gah_locale` 없음 → `Config.ui_language == "auto"` (default) → `Accept-Language` 의 첫 매치 `en` → `request.state.locale = "en"`.
3. 모든 Jinja2 템플릿이 `{{ _("라이브러리") }}` → "Library", `{{ _("검색") }}` → "Search" 등으로 렌더.
4. 헤더 우상단 언어 셀렉터에 "EN ▾" 표시. 사용자가 클릭해 "한국어" 선택 → `PUT /api/settings {ui_language: "ko"}` → 쿠키 `gah_locale=ko` + Config 저장 → 전체 페이지 reload → 한국어 표시.

### 3.3 다크 모드 토글

1. Windows 가 라이트 모드 → 페이지가 라이트로 렌더 (`prefers-color-scheme: light`).
2. 사용자가 헤더 ☀️/🌙 버튼 클릭 → Alpine `theme = "dark"` → `<html data-theme="dark">` 속성 set → CSS `[data-theme="dark"]` 셀렉터가 활성 → 즉시 다크로 전환. `localStorage.gah_theme = "dark"` 영속화.
3. 페이지 reload → Alpine `x-data` 초기 함수가 `localStorage` 읽어 `data-theme` 복원. 새로고침해도 다크 유지.
4. 사용자가 토글 한 번 더 → `theme = "auto"` → `data-theme` 제거 → `prefers-color-scheme` 미디어쿼리 다시 활성 (시스템 따라감). 사이클: `auto` → `light` → `dark` → `auto` ...

### 3.4 자동 시작 토글

1. 사용자가 `/settings` 진입 → 토글 "Windows 시작 시 자동 실행" off 상태 (Config default).
2. 사용자가 토글 → `POST /api/settings {autostart: true}` → 서버가 `autostart.set_autostart(True)` 호출 → `winreg.HKCU\Software\Microsoft\Windows\CurrentVersion\Run\GameAssetHelper = "<exe path> --tray"` 등록 + `Config.autostart=True` 저장.
3. 다음 Windows 부팅 → `GameAssetHelper.exe --tray` 자동 실행 → 트레이 등장.
4. 사용자가 트레이 메뉴 우클릭 → "자동 시작 ✓" 체크박스 → 클릭으로 해제 → 같은 코드로 `set_autostart(False)` → 레지스트리 키 삭제.

### 3.5 설정 페이지 통합

`/settings` 1 페이지에서 모두 관리:
- 언어 라디오: `한국어 (ko)` / `English (en)` / `자동 감지 (auto)`
- 테마 라디오: `자동 (시스템 따라)` / `라이트` / `다크`
- 토글: `Windows 시작 시 자동 실행`

저장 버튼 누르면 `POST /api/settings` → Config 저장 + 쿠키 `gah_locale` set + 레지스트리 동기화 + 전체 페이지 reload.

### 3.6 개발자가 `pyinstaller gah.spec` 빌드

1. `pip install -e .[dev]` (이미 셋업) + `pip install pyinstaller` (dev extras 에 추가).
2. `pybabel compile -d src/gah/web/locale/` — `.po` → `.mo` 컴파일.
3. `pyinstaller gah.spec` — 단일 `dist/GameAssetHelper.exe` (~1.5 GB) 생성.
4. `dist/GameAssetHelper.exe --version` 으로 smoke test.
5. 사용자 PC 에 복사해 실행 → 시나리오 3.1 흐름.

## 4. 결정 사항 (D1~D8)

각 결정은 plan/구현/테스트에서 그대로 인용된다. 결정 번호는 plan 의 task ID 에 매핑된다.

### D1 — PyInstaller `--onefile` + spec 파일

- 빌드 형식: `--onefile`. 단일 `.exe` 가 일반 사용자에게 가장 친화적 (메모리 `project_distribution_torch_strategy.md` 결정 일관).
- `gah.spec` 파일을 저장소 루트에 커밋 (`pyinstaller gah.spec` 으로 재현 가능).
- 엔트리: `python -m gah --tray` 와 동등한 `src/gah/__main__.py:main` (CLI 인자 그대로).
- 번들 데이터 (`datas=`): `src/gah/web/templates/`, `src/gah/web/static/`, `src/gah/web/locale/{ko,en}/LC_MESSAGES/*.mo`.
- 제외 모듈 (`excludes=`): `pytest`, `pytest_asyncio`, `playwright`, `respx`, `pytest_playwright`, `pytest_mock`.
- 옵션: `--noconsole` (트레이 앱, 콘솔 창 없음). `.exe` 윈도우 아이콘용 ICO 가 필요한데 [`src/gah/tray.py`](../../../src/gah/tray.py) `_build_app_icon()` 이 런타임 QPixmap 으로 동적 생성하는 구조라 정적 ICO 파일이 없다. Phase 5 에서 신규 헬퍼 `scripts/generate_tray_ico.py` 를 추가 — `_build_app_icon()` 결과 QPixmap 을 여러 크기로 합쳐 `assets/tray.ico` 로 export. 빌드 사전 절차 (`python scripts/generate_tray_ico.py` 1회) 로 ICO 생성 후 `spec` 의 `Analysis.icon=` 또는 `EXE(icon=...)` 에 참조. ICO 도 git 에 커밋 (재현성).
- torch wheel: PyPI 기본 (CUDA 12.x 통합) 그대로 번들. 분기 없음.
- CLIP 모델 가중치는 번들 **하지 않음** — 첫 실행 시 `~/.cache/clip/` 또는 `%APPDATA%/GameAssetHelper/cache/clip/` 로 다운로드 (open_clip 의 기본 동작). 사용자에게 첫 검색 직전 모달로 알림.
- 빌드 산출물: `dist/GameAssetHelper.exe`. `build/`, `__pycache__/`, `dist/` 는 `.gitignore` 에 이미 있음 (확인 후 없으면 추가).
- smoke 테스트: `tests/test_pyinstaller_spec.py` — `gah.spec` 을 `compile()` 로 파싱해 `Analysis()` 인자 검증, 번들 데이터 경로 실재 확인. 실 빌드는 수동 검증 (`milestones/M8_verification.md`).

### D2 — Babel `gettext` 백엔드 + locale 디렉터리 구조

- 신규 디렉터리: `src/gah/web/locale/`
  - `messages.pot` (소스 카탈로그, `pybabel extract` 산출)
  - `ko/LC_MESSAGES/messages.po` (한국어 — msgid 영어, msgstr 한국어)
  - `ko/LC_MESSAGES/messages.mo` (compiled — git 에는 .po 만 커밋, .mo 는 빌드 시 생성)
  - `en/LC_MESSAGES/messages.po` (영어 — msgid == msgstr)
  - `en/LC_MESSAGES/messages.mo`
- 신규 파일: `babel.cfg` (저장소 루트)
  ```ini
  [python: src/**.py]
  [jinja2: src/gah/web/templates/**.html]
  extensions=jinja2.ext.i18n
  ```
- **`.mo` 파일도 git 에 커밋한다** — `pybabel compile` 을 매 빌드 시 강제하면 신규 contributor 가 빠뜨릴 위험 + CI 셋업이 복잡해진다. PyInstaller 가 그대로 번들. plan 의 verification task 에 "`.po` 수정 시 `pybabel compile` 후 커밋" 명시.
- msgid 정책: **영어 자연 문장**으로 통일 (예: `_("Library")`, `_("Search assets")`). 한국어를 msgid 로 두면 GitHub 검색/외부 도구 호환성이 떨어진다.
- 현재 한글 hardcode → 영어 msgid 변환 + ko.po 에 원래 한국어 매핑. **이 변환 작업이 M8 의 가장 큰 단일 task** (Phase 2, ~1.5일).
- 폴백: msgid 가 카탈로그에 없으면 msgid 그대로 반환 (gettext 표준 동작).

### D3 — `_t()` 본격화 + Jinja2 통합

```python
# src/gah/web/i18n.py (M8 개정)
import gettext
from pathlib import Path

_translations: dict[str, gettext.GNUTranslations] = {}

def _load_translations(locale_dir: Path) -> None:
    """Boot 시 1회 호출 — 모든 locale 의 .mo 를 메모리에 로드."""
    for lang in ("ko", "en"):
        mo_path = locale_dir / lang / "LC_MESSAGES" / "messages.mo"
        if mo_path.exists():
            with mo_path.open("rb") as fh:
                _translations[lang] = gettext.GNUTranslations(fh)

def _t(text: str, locale: str = "ko") -> str:
    """Translate `text` (msgid) to `locale`. Fallback chain:
    1. locale 카탈로그에 msgid → 번역 반환
    2. locale 카탈로그 미존재 또는 "auto" 등 비정상 값 → "ko" 카탈로그 재시도
    3. 그 후에도 없으면 msgid 그대로 반환
    """
    trans = _translations.get(locale) or _translations.get("ko")
    return trans.gettext(text) if trans else text

def setup_jinja_i18n(env, get_current_locale):
    """`{{ _("...") }}` 가 request 별 locale 로 자동 동작."""
    env.add_extension("jinja2.ext.i18n")
    env.install_gettext_callables(
        gettext=lambda msg: _t(msg, get_current_locale()),
        ngettext=lambda s, p, n: _t(s if n == 1 else p, get_current_locale()),
        newstyle=True,
    )
```

- `get_current_locale` 은 `ContextVar` 기반 — `LocaleMiddleware` 가 request 시작 시 set, 종료 시 reset.
- 기존 `setup_jinja_i18n(env)` 시그니처 변경 → 호출처 ([`src/gah/web/app.py`](../../../src/gah/web/app.py) 또는 [`src/gah/web/server.py`](../../../src/gah/web/server.py)) 도 함께 갱신.

### D4 — Locale 결정 미들웨어 (5단계 우선순위)

신규 파일 `src/gah/web/locale_middleware.py`:

```python
class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        locale = self._resolve(request)
        token = _current_locale.set(locale)
        request.state.locale = locale
        try:
            response = await call_next(request)
        finally:
            _current_locale.reset(token)
        return response

    def _resolve(self, request) -> str:
        # 1. URL ?lang=
        q = request.query_params.get("lang")
        if q in ("ko", "en"):
            return q
        # 2. 쿠키
        c = request.cookies.get("gah_locale")
        if c in ("ko", "en"):
            return c
        # 3. Config.ui_language
        cfg = request.app.state.config
        if cfg.ui_language in ("ko", "en"):
            return cfg.ui_language
        # 4. Accept-Language
        accept = request.headers.get("accept-language", "")
        if accept:
            for raw in accept.split(","):
                tag = raw.split(";")[0].strip().lower()
                if tag.startswith("en"):
                    return "en"
                if tag.startswith("ko"):
                    return "ko"
        # 5. 폴백
        return "ko"
```

- `_current_locale: ContextVar[str]` 는 모듈 변수.
- `cookies["gah_locale"]` 는 `Max-Age=31536000` (1년), `SameSite=Lax`, `HttpOnly=False` (JS 에서 읽을 수 있어야 헤더 셀렉터 표시).
- URL `?lang=` 으로 진입한 경우 응답에 `Set-Cookie: gah_locale=...` 도 set (다음 요청부터 쿠키 우선).

### D5 — `Config.ui_language` + `Config.ui_theme` 신규, `autostart` 활용

```python
# src/gah/config.py (M8 추가)
ui_language: Literal["ko", "en", "auto"] = "auto"
ui_theme: Literal["auto", "light", "dark"] = "auto"
# autostart 는 이미 line 101 에 존재 — 그대로 활용
```

- `from_mapping` 의 유효성 검사 화이트리스트에 두 필드 추가 (잘못된 값은 default 폴백).
- `_VALID_UI_LANGUAGES = ("ko", "en", "auto")`, `_VALID_UI_THEMES = ("auto", "light", "dark")` 모듈 상수.

### D6 — 다크모드 수동 토글 (Alpine + localStorage + data-theme)

- `_global_header.html` 에 토글 버튼:
  ```html
  <button type="button"
          x-data="themeToggle()"
          x-init="init()"
          @click="cycle()"
          x-text="icon"
          :title="`현재: ${label}, 클릭 시 다음 모드`"
          class="theme-toggle-btn">
  </button>
  ```
- 신규 정적 파일 `src/gah/web/static/js/theme.js`:
  ```js
  function themeToggle() {
      return {
          mode: 'auto',
          init() {
              this.mode = localStorage.getItem('gah_theme') || 'auto';
              this.apply();
          },
          cycle() {
              this.mode = this.mode === 'auto' ? 'light' : this.mode === 'light' ? 'dark' : 'auto';
              localStorage.setItem('gah_theme', this.mode);
              this.apply();
          },
          apply() {
              if (this.mode === 'auto') document.documentElement.removeAttribute('data-theme');
              else document.documentElement.setAttribute('data-theme', this.mode);
          },
          get icon() { return this.mode === 'dark' ? '🌙' : this.mode === 'light' ? '☀️' : '🌗'; },
          get label() { return this.mode === 'dark' ? '다크' : this.mode === 'light' ? '라이트' : '자동'; },
      };
  }
  ```
- CSS 조정 (`src/gah/web/static/css/main.css` 또는 동등 파일):
  - 기존 `@media (prefers-color-scheme: dark)` 블록 → `:where(html:not([data-theme="light"])) { ... }` 와 결합되도록 selector 조정.
  - 새 블록 `html[data-theme="dark"] { ... }` 추가 — 강제 다크.
  - `html[data-theme="light"]` 는 라이트 변수만, 다크 셀렉터를 override.
- 초기 로드 깜빡임 방지: `<head>` 의 `theme.js` 직전에 인라인 스크립트 `if (localStorage.gah_theme && localStorage.gah_theme !== 'auto') document.documentElement.setAttribute('data-theme', localStorage.gah_theme);` 삽입.
- **D5 의 `Config.ui_theme` 와의 관계**: 서버사이드 default 만 결정 (예: 신규 사용자 첫 진입 시 light or dark). 사용자 토글은 클라이언트 사이드 `localStorage` 가 진실. `Config.ui_theme` 변경 시 페이지 reload 시점에 `<html data-theme>` 가 한 번 set 되고, 그 후 사용자 토글이 `localStorage` 를 갱신.

### D7 — Windows 자동 시작 (`platform/autostart.py`)

신규 파일 `src/gah/platform/autostart.py`:

```python
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_VALUE_NAME = "GameAssetHelper"

def is_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
            value, _ = winreg.QueryValueEx(key, APP_VALUE_NAME)
            return bool(value)
    except (OSError, FileNotFoundError):
        return False

def set_autostart(enabled: bool, exe_path: Path | None = None) -> None:
    if sys.platform != "win32":
        logger.info("autostart no-op on non-Windows")
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            target = _resolve_exe_command(exe_path)
            winreg.SetValueEx(key, APP_VALUE_NAME, 0, winreg.REG_SZ, target)
        else:
            try:
                winreg.DeleteValue(key, APP_VALUE_NAME)
            except FileNotFoundError:
                pass

def _resolve_exe_command(exe_path: Path | None) -> str:
    """`.exe` 빌드면 exe + ' --tray', 개발 환경이면 'pythonw.exe -m gah --tray'."""
    if exe_path is not None:
        return f'"{exe_path}" --tray'
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    # dev fallback — pythonw 로 콘솔 없이
    return f'"{sys.executable}" -m gah --tray'
```

- 모든 함수가 비-Windows 에서 안전 (no-op, return False).
- 예외 처리: `OSError` (권한 거부) 는 호출처에서 캐치 → 토글 UI 에 "권한 거부" 표시 + Config 캐시 롤백.
- 테스트: `winreg` 를 `pytest-mock` 으로 mock — 실제 레지스트리는 건드리지 않음.

### D8 — `/settings` 페이지 + `POST /api/settings`

신규 라우터 `src/gah/web/routers/settings.py`:

```python
router = APIRouter()

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, deps: WebDeps = Depends(get_web_deps)):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "config": deps.config,
        "autostart_actual": is_autostart_enabled(),
        "current_locale": request.state.locale,
    })

@router.post("/api/settings")
async def update_settings(payload: SettingsUpdate, deps: WebDeps = Depends(get_web_deps)):
    cfg = deps.config
    if payload.ui_language is not None:
        cfg.ui_language = payload.ui_language
    if payload.ui_theme is not None:
        cfg.ui_theme = payload.ui_theme
    if payload.autostart is not None:
        try:
            set_autostart(payload.autostart)
            cfg.autostart = payload.autostart
        except OSError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    save_config(cfg, deps.paths.config_path)
    response = JSONResponse({"ok": True})
    if payload.ui_language is not None and payload.ui_language != "auto":
        response.set_cookie("gah_locale", payload.ui_language, max_age=31_536_000, samesite="lax")
    return response

class SettingsUpdate(BaseModel):
    ui_language: Literal["ko", "en", "auto"] | None = None
    ui_theme: Literal["auto", "light", "dark"] | None = None
    autostart: bool | None = None
```

- 신규 템플릿 `src/gah/web/templates/settings.html`:
  - 폼 3개 섹션 (언어 / 테마 / 자동 시작)
  - 저장 후 `window.location.reload()` 로 새 locale/theme 즉시 반영
- 사이드바 메뉴에 "설정" 링크 (`_side_panel_*.html` 수정).
- 트레이 메뉴 ([`src/gah/tray.py`](../../../src/gah/tray.py)) 에 "자동 시작" 체크박스 추가 — 같은 `set_autostart` 호출.

## 5. 인터페이스 / 데이터 모델

### 5.1 신규 모듈 / 파일

| 경로 | 종류 | 역할 |
|---|---|---|
| `gah.spec` (저장소 루트) | PyInstaller spec | 빌드 사양 |
| `babel.cfg` (저장소 루트) | Babel config | extractor 설정 |
| `src/gah/web/locale/{ko,en}/LC_MESSAGES/messages.{po,mo}` | gettext 카탈로그 | 번역 데이터 |
| `src/gah/web/locale_middleware.py` | FastAPI middleware | locale 결정 5단계 |
| `src/gah/web/routers/settings.py` | FastAPI router | `/settings`, `/api/settings` |
| `src/gah/web/templates/settings.html` | Jinja2 template | 설정 페이지 |
| `src/gah/web/static/js/theme.js` | JS | 다크모드 Alpine 컴포넌트 |
| `src/gah/platform/autostart.py` | Python module | winreg get/set |
| `scripts/generate_tray_ico.py` | dev 헬퍼 | `_build_app_icon()` 결과를 멀티 사이즈 ICO 로 export |
| `assets/tray.ico` | 정적 자원 | exe 아이콘 (커밋) |

### 5.2 수정 파일

| 경로 | 변경 |
|---|---|
| `src/gah/web/i18n.py` | passthrough → gettext 위임 + `_load_translations` + `setup_jinja_i18n` 시그니처 변경 |
| `src/gah/config.py` | `ui_language`, `ui_theme` 신규 필드 + `from_mapping` 유효성 검사 |
| `src/gah/web/app.py` (또는 `server.py`) | `LocaleMiddleware` 등록, `_load_translations` boot 호출, `setup_jinja_i18n` 시그니처 변경 반영 |
| `src/gah/web/templates/_global_header.html` | 테마 토글 + 언어 셀렉터 추가 |
| `src/gah/web/templates/_side_panel*.html` | "설정" 메뉴 항목 |
| `src/gah/web/templates/**/*.html` (전체) | 한글 hardcode → `{{ _("English msgid") }}` |
| `src/gah/web/static/css/main.css` (또는 동등) | `[data-theme]` 셀렉터 추가, 기존 `@media` 조정 |
| `src/gah/tray.py` | "자동 시작" 체크박스 |
| `pyproject.toml` | `Babel>=2.14` 런타임, `pyinstaller>=6` dev |
| `.gitignore` | `dist/`, `build/`, `*.spec.pyc` 추가 (이미 있을 가능성 → 확인) |
| `README.md` | "사용자 설치 (.exe)" + "개발자 빌드 (`pyinstaller gah.spec`)" + "번역 추가" 섹션 |

### 5.3 `Config` 신규 필드 (D5 재인용)

```python
ui_language: Literal["ko", "en", "auto"] = "auto"
ui_theme: Literal["auto", "light", "dark"] = "auto"
# autostart 는 기존
```

### 5.4 `SettingsUpdate` Pydantic 모델 (D8 재인용)

```python
class SettingsUpdate(BaseModel):
    ui_language: Literal["ko", "en", "auto"] | None = None
    ui_theme: Literal["auto", "light", "dark"] | None = None
    autostart: bool | None = None
```

## 6. 테스트 전략

신규 테스트 ~30~40 케이스 (현재 1011 → 목표 ~1050).

| 파일 | 대상 | 핵심 케이스 (예상) | 케이스 수 |
|---|---|---|---:|
| `tests/test_i18n.py` | `_t()`, `_load_translations` | ko/en 출력, msgid 미번역 폴백, locale 누락 | ~6 |
| `tests/test_locale_middleware.py` | 5단계 우선순위 | URL > 쿠키 > Config > Accept-Language > ko, 잘못된 lang 값 무시, ContextVar 격리 | ~8 |
| `tests/test_autostart.py` | `is_/set_autostart` (winreg mock) | get/set/clear, 권한 거부, 비-Windows no-op, `_resolve_exe_command` 분기 | ~7 |
| `tests/test_settings_router.py` | `/settings` GET + POST | 렌더 200, Config 저장, 쿠키 set, autostart 동기화, 잘못된 payload 422 | ~6 |
| `tests/test_dark_mode_markup.py` | 헤더 마크업 정합성 | 토글 버튼 존재, `x-data="themeToggle()"`, theme.js 로드 | ~3 |
| `tests/test_pyinstaller_spec.py` | `gah.spec` 정합성 | spec 파싱, 번들 `datas` 경로 실재, excludes 검증 | ~4 |
| `tests/test_config_m8.py` | Config 신규 필드 | default, serialize/load roundtrip, 잘못된 값 폴백 | ~5 |
| `tests/test_i18n_extraction.py` | 추출 정합성 | `babel.cfg` 로 `pybabel extract` 시 주요 msgid 추출됨 (smoke, 일부 샘플 키만) | ~2 |

- 실 빌드 (`pyinstaller gah.spec`) 와 실 레지스트리 변경은 **수동 검증** (`milestones/M8_verification.md`).
- Playwright e2e 는 본 M8 범위 외 (사용자 결정: 핵심 최소).

## 7. Phase 분할 (subagent-driven-development 패턴)

| Phase | 내용 | 신규 테스트 | 예상 |
|---|---|---:|---:|
| **0** — 스캐폴딩 | `Babel>=2.14` + `pyinstaller>=6` 의존성, `locale/{ko,en}/LC_MESSAGES/` 디렉터리 + 빈 `.po`, `babel.cfg`, `Config` 신규 필드, `platform/autostart.py` 스켈레톤, 신규 테스트 파일 placeholder | ~10 | 0.5일 |
| **1** — i18n 인프라 | `_t()` gettext 위임, `_load_translations`, `setup_jinja_i18n` 신 시그니처, `LocaleMiddleware`, `ContextVar`, app.py 통합 | ~14 | 1일 |
| **2** — 문자열 추출 + ko/en 번역 | 모든 템플릿/Python 한글 → 영어 msgid 변환, `pybabel extract` → `messages.pot` → `ko.po`/`en.po` 작성, `.mo` 컴파일 + git 커밋 | ~2 (smoke) | 1.5일 |
| **3** — `/settings` 페이지 + 다크모드 | `routers/settings.py`, `settings.html`, 사이드바 메뉴, 헤더 테마 토글, `theme.js`, CSS `[data-theme]` 조정 | ~9 | 1일 |
| **4** — 자동 시작 | `autostart.py` 완성, 트레이 메뉴 통합, `/api/settings` autostart 분기, 사용자 권한 거부 UX | ~7 | 0.5일 |
| **5** — PyInstaller 빌드 | `scripts/generate_tray_ico.py` + `assets/tray.ico`, `gah.spec` 작성, `.gitignore` 정리, README 빌드 가이드, smoke 테스트, 수동 빌드 1회 + 검증 | ~4 | 1일 |
| **6** — verification + 문서 마감 | `M8_verification.md`, `HANDOFF.md`, `CLAUDE.md`, `DESIGN.md` §11 업데이트, 메모리 업데이트, PR 본문 작성 | 0 | 0.5일 |
| **합계** | | **~46** | **6일** |

각 phase 마지막에 `pytest -q` 가 회귀 없이 통과해야 다음 phase 시작. Phase 2 가 가장 노동 집약적 (~50 템플릿 + ~20 라우터/Python 위치) — 이 phase 만 sonnet 1차 + haiku review 더블로 진행.

## 8. 비목표 (v2 또는 영구 미룸)

다음 항목은 **본 M8 에서 의도적으로 다루지 않는다**. M5/M7 에서 미뤘던 후보 중 사용자가 "핵심 최소" 를 선택한 결과.

- **Pack/프로젝트 풍부 UX** (메타 수정, manual_override 토글, pin/block, 사용 분포 차트) — DESIGN §11 명시 후보였으나 v2.
- **Playwright E2E 테스트** — M5/M6 에서 옵트인 인프라만 깔려 있음 (`pytest -m e2e`). 본 M8 도 그대로 유지, 케이스 추가 없음.
- **모바일/태블릿 최적화** — 현재 데스크톱 우선. v2.
- **슬라이더 (검색 가중치) 설정 영속화** — M4 에서 GUI 만, 영속화는 v2.
- **자동 동기화 스케줄러** — M7 에서 v2 로 미룸 그대로 유지.
- **트레이 알림 (분석 완료 등)** — `QSystemTrayIcon.showMessage` 사용 가능하지만 v2.
- **추가 언어 (ja/zh)** — 인프라는 깔리지만 번역은 ko/en 만.
- **자동 업데이트 (Squirrel/Sparkle 등)** — v2.
- **MSI/NSIS 인스톨러** — 본 M8 는 단일 `.exe` (portable). 인스톨러는 v2.
- **코드 서명** — SmartScreen 경고를 피하려면 EV 코드 서명 인증서 필요 ($$$). v2 또는 영구 미룸.
- **번역 워크플로 자동화 (CI 에서 `pybabel compile`)** — 본 M8 는 수동 컴파일 + `.mo` 커밋.

## 9. 위험 / 알려진 한계

- **PyInstaller 빌드 시간** — torch + open_clip 포함이라 첫 빌드 ~5~10분 예상. CI 화는 v2.
- **`.exe` 크기** — ~1.5~2 GB. GitHub release 의 단일 파일 제한 (2 GB) 에 근접. 초과 시 7z 분할 압축 안내.
- **SmartScreen 경고** — 서명 없는 빌드라 사용자가 "추가 정보" 클릭해야 실행. README 에 명시.
- **번역 누락** — 사용자 노출 동적 문자열 (라벨 description, 팩 이름) 은 번역 대상 외. 정적 라벨 ID 와 axis 이름은 추출 대상.
- **레지스트리 권한** — 표준 사용자도 HKCU 는 쓰기 가능. 단 일부 기업/학교 PC 의 GPO 가 막을 수 있음 → 에러 UX 명시.
- **WAL 파일 + .exe** — SQLite WAL 모드라 `.exe` 종료 시 WAL 잔존 가능. 다음 부팅 시 자동 정리 (기존 동작).
- **`pybabel extract` 가 동적 문자열 놓침** — `_t(f"... {var} ...")` f-string 은 extractor 가 못 잡음. extract 후 누락분 수동 보강 task 가 Phase 2 에 포함.

## 10. 검증 시나리오 (사용자 수동 — M8_verification.md 초안)

1. `pip install -e .[dev]` + `pip install pyinstaller` → `pyinstaller gah.spec` → `dist/GameAssetHelper.exe` 생성 확인 (~1.5 GB).
2. `dist/GameAssetHelper.exe --version` → "0.0.1" 출력.
3. `dist/GameAssetHelper.exe --tray` → 트레이 + 브라우저 자동 열림.
4. 브라우저에서 `?lang=en` → 전체 UI 영어.
5. `/settings` → 언어 라디오 "ko" → 저장 → reload → 한국어.
6. 헤더 테마 토글 ☀️/🌙/🌗 사이클 → CSS 변경 시각 확인 → 새로고침해도 유지.
7. `/settings` 자동 시작 토글 on → `regedit` 로 `HKCU\...\Run\GameAssetHelper` 확인 → 토글 off → 값 삭제 확인.
8. 트레이 우클릭 → "자동 시작" 체크박스 동기 동작 확인.
9. PC 재부팅 → 자동 시작 켠 상태라면 GAH 자동 실행 확인.
10. M5/M6/M7 의 기존 시나리오 회귀 없음 (라이브러리 / 검색 / Unity 임포트 / 프로젝트 페이지).

## 11. 마일스톤 종료 조건

- [ ] `pytest -q` 가 **~1050 passed** 도달, 회귀 0
- [ ] `pytest -m mcp_integration -v` 가 20 도구 그대로 확인
- [ ] `pyinstaller gah.spec` 빌드 성공 → `dist/GameAssetHelper.exe --version` 동작
- [ ] 사용자 검증 시나리오 1~10 모두 통과
- [ ] `milestones/M8_verification.md` 작성
- [ ] `HANDOFF.md`, `CLAUDE.md`, `DESIGN.md` §11 갱신 — M8 완료 + v2 보류 항목
- [ ] PR 본문 작성 (한국어)
