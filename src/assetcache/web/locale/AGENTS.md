<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# locale

## Purpose
M8 i18n 카탈로그. Babel gettext 포맷 — `messages.pot` (추출 템플릿) + 언어별 `LC_MESSAGES/messages.po` (번역 소스) + `LC_MESSAGES/messages.mo` (런타임 컴파일). 부팅 시 `i18n._load_translations` 가 `.mo` 를 메모리에 로드, 요청 처리 시 `_t(msgid, locale)` 가 카탈로그 조회.

지원 언어: **ko (기본) + en**. `LocaleMiddleware` 가 `Accept-Language` / 쿠키 / URL 쿼리 로 결정, 미지원 locale 은 ko 폴백.

## Key Files
| File | Description |
|------|-------------|
| `messages.pot` | Babel 추출 결과 (msgid 만, 번역 없음). `pybabel extract -F babel.cfg -o src/assetcache/web/locale/messages.pot src/` |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `ko/LC_MESSAGES/` | 한국어 — `messages.po` 번역 소스 + `messages.mo` 컴파일 산출물 |
| `en/LC_MESSAGES/` | 영어 — 동일 구조 |

## For AI Agents

### Working In This Directory
- **워크플로 (msgid 갱신 시)**:
  1. 템플릿/코드에 `{{ _('...') }}` / `_t('...')` 추가
  2. `pybabel extract -F babel.cfg -o src/assetcache/web/locale/messages.pot src/`
  3. `pybabel update -i src/assetcache/web/locale/messages.pot -d src/assetcache/web/locale -l ko`
     `pybabel update -i src/assetcache/web/locale/messages.pot -d src/assetcache/web/locale -l en`
  4. 각 `messages.po` 열어서 번역 채우기
  5. `pybabel compile -d src/assetcache/web/locale` → `.mo` 갱신
  6. `.po` + `.mo` + `.pot` 모두 commit (PyPI 패키지에 `.mo` 포함되어야 동작 — `pyproject.toml [tool.setuptools.package-data]` 의 `"assetcache.web" = ["locale/**/*.mo"]`)
- **`.mo` 미존재 시 i18n 폴백** — `_load_translations` 가 warning 로그만 남기고 msgid 자체를 반환. boot 깨지진 않음.
- **새 locale 추가 시** — `pybabel init -i ... -d ... -l {locale}` + `i18n.SUPPORTED_LOCALES` 튜플 + `LocaleMiddleware` 의 매칭 로직 갱신.
- **번역 누락된 msgid** — `_t` 가 ko 카탈로그로 1차 폴백, 그래도 없으면 msgid 그대로 반환. 사용자에게 영문 msgid 가 노출되면 ko 번역 누락 의심.

### Testing Requirements
- `tests/test_i18n.py` — 카탈로그 로드 + 폴백 체인 (locale → ko → msgid) + 미지원 locale 처리.

### Common Patterns
- msgid 는 한글로 작성 (기본 locale 이 ko) — 영문 번역은 en 카탈로그에 보충. 영문 msgid 채택 시 ko 번역까지 다 채워야 함.
- 동적 문자열 보간은 gettext `%(name)s` 패턴 — Jinja2 `{{ }}` 와 충돌하지 않게 주의.

## Dependencies

### Internal
- `../i18n.py` — 카탈로그 로드 + `_t`.
- `../locale_middleware.py` — locale 결정.
- `../templates/` — `{{ _('...') }}` 소비.
- 루트 `babel.cfg` — 추출 설정.

### External
- `Babel>=2.14` (extract / update / compile).

<!-- MANUAL: 새 locale 지원 시 SUPPORTED_LOCALES + LocaleMiddleware + 이 문서 셋 모두 갱신. -->
