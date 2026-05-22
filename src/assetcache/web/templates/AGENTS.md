<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# templates

## Purpose
Jinja2 템플릿. **3 종류**:
1. **페이지** (`{name}.html`) — `base.html` extend, 전체 HTML 문서.
2. **fragment partial** (`_{name}.html` — underscore prefix) — HTMX `hx-get`/`hx-post` 응답으로 부분 교체. `<html>` 없이 fragment 만.
3. **서브 카테고리** (`analyzing/`, `settings/`) — 페이지 + 그에 속하는 partial 그룹화.

`pyproject.toml [tool.setuptools.package-data]` 가 `templates/**/*.html` 을 패키지에 포함시켜 PyPI install 시에도 동작.

## Key Files

### 페이지 (base.html extend)
| File | Description |
|------|-------------|
| `base.html` | 공통 레이아웃 — nav + body block + i18n + Alpine.js + HTMX 로드 |
| `library.html` | 라이브러리 검색 페이지 |
| `packs.html` | 팩 카드 그리드 |
| `labels_admin.html` | 라벨 axis 인벤토리 admin |
| `projects_list.html`, `project_detail.html` | 프로젝트 CRUD |
| `asset_detail.html` | 자산 상세 모달/페이지 |
| `unity_asset_store.html` | Unity 캐시 패키지 리스트 |
| `error.html`, `error_fragment.html` | 에러 페이지 + fragment |

### Fragment partial (`_` prefix)
| File | Description |
|------|-------------|
| `_nav.html` | 네비게이션 바 |
| `_header_project_dropdown.html` | 헤더 active 프로젝트 셀렉터 |
| `_pack_card.html`, `_packs_grid.html` | 팩 카드 + 그리드 |
| `_pick_card.html`, `_card_list.html`, `_card_wide.html` | 검색 결과 카드 (list/wide variant) |
| `_results_grid.html`, `_results_cards_only.html` | 결과 그리드 (HTMX swap target) |
| `_side_panel_b.html`, `_side_panel_c.html`, `_side_panel_d.html` | 사이드 패널 variant (M11.x 단계별) |
| `_label_row.html`, `_labels_admin_grid.html` | 라벨 admin 행/그리드 |
| `_modal_new_project.html`, `_modal_usage.html` | 모달 dialog |
| `_preference_panel.html` | 검색 가중 / diversity 조정 |
| `_unity_package_row.html` | Unity 패키지 행 |
| `_search_error.html` | 검색 에러 fragment |
| `_audio_player.html` | sound 자산 inline 재생 |
| `_pypi_update_banner.html` | M10 PyPI 신버전 배너 |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `analyzing/` | M11.1 — `/analyzing` 페이지 + `_partial.html` (HTMX poll target, active/pending/done 카운트 + 항목 행) |
| `settings/` | 설정 페이지 partial + 백엔드별 도움말 (`help_{backend}_{locale}.html` 6 backend × ko/en = 12 파일) + `_batch_card.html` |

## For AI Agents

### Working In This Directory
- **fragment 는 `_` prefix 필수** — 페이지와 구분. 페이지가 fragment include 시 `{% include "_x.html" %}` 또는 HTMX `hx-get` 으로 lazy load.
- **i18n msgid** — 한글 텍스트는 `{{ _('msgid') }}` 로 감싸지 X. 한글 메시지 catalog 가 정책상 'ko' 기본이라 msgid 가 한글이어도 OK. 영문 카탈로그가 필요한 메시지만 `_('...')` 적용.
- **HTMX swap target** — `_results_grid.html` 같은 fragment 는 응답에서 그대로 swap 되도록 root element id 가 stable 해야 한다.
- **Alpine.js + HTMX 공존** — `x-data` 는 fragment swap 후 재초기화. Alpine state 유지가 필요하면 `_results_cards_only.html` 처럼 inner only swap.
- **백엔드 도움말 추가 시** — `settings/help_{backend}_ko.html` + `settings/help_{backend}_en.html` 한 쌍 추가. 7번째 backend 가 생기면 14 파일이 된다 (현재 12).
- **에러 페이지** — full 페이지는 `error.html`, fragment 는 `error_fragment.html` 로 통일.

### Testing Requirements
- 페이지 렌더: `tests/test_web_pages.py`, `tests/test_web_active_project.py`.
- fragment 단언: `tests/test_web_routers_*.py` (응답 본문에 `<html>` 부재 + 기대 마크업).
- 사이드 패널 variant: `tests/test_web_side_panel_{b,c,d}.py`.

### Common Patterns
- `base.html` 의 block: `{% block title %}`, `{% block content %}`, `{% block scripts %}`.
- nav 활성 표시: context 에 `page="library"` 같은 키 전달 → `_nav.html` 가 비교.
- 모달 dialog: `<dialog>` HTML element + Alpine `x-show` + close 버튼.

## Dependencies

### Internal
- `../app.py` — Jinja2Environment + templates_dir 설정.
- `../routers/` — context 주입.
- `../static/` — CSS / JS 참조 (`{{ url_for('static', path='...') }}`).
- `../i18n.py` — `_t` 함수가 Jinja2 globals 에 등록.

### External
- jinja2>=3.1.

<!-- MANUAL: 신규 페이지/fragment 추가 시 파일명 prefix 컨벤션 (페이지=확장자만, partial=`_` prefix) 엄격 유지. -->
