# M11.9 — 백엔드 정리 (6 → 3 backend, v0.2.7+ candidate)

본 plan 은 [`consensus-m11-9-backend-cleanup-2026-05-22`](../.omc/plans/consensus-m11-9-backend-cleanup.md) 의 RALPLAN-DR SHORT 결과를 마일스톤 형식으로 옮긴 것.

## 1. 목표

AssetCacheMCP 의 multi-backend LLM 아키텍처를 **6 backend → 3 backend (Ollama / Gemini / OpenAI)** 로 단순화. v0.0.1~v0.2.7 외부 PyPI 사용자 0 으로 호환성 비용 0 — **full purge**, 8 표면 atomic 동시 정리.

## 2. 산출물

| 표면 | 내용 |
|---|---|
| 1. 코드 모듈 | `src/assetcache/core/llm/backends/{claude,openrouter,huggingface}.py` 3 파일 삭제 |
| 2. registry | `_default_{claude,openrouter,huggingface}_factory` 3 함수 + `from_config` 의 3 kwargs + 3 default assign + factory dict 3 엔트리 + `:70` stale comment 제거 |
| 3. config | `_KNOWN_BACKENDS` 3 키 + `_default_backends()` 3 키 + docstring `6 backend` → `3 backend` |
| 4. tests | mock 3 + 옵트인 LIVE 3 = 6 파일 삭제 + cross-backend dependency 6 파일 정리 (chain / registry / setup_url / cross_backend / settings_router / partials / config_migration) + `test_llm_backend_supports_batch.py` 6→3 |
| 5. 의존성 | `pyproject.toml` 의 `anthropic>=0.40` + `huggingface_hub>=0.24` 2 라인 제거 + `llm_integration` marker description 갱신. `openai>=1.50` 유지 |
| 6. UI | `settings.html` 의 Jinja loop backend 배열 + JS `backendOrder` + `setupUrls` / `setupLinkLabels` 의 3 entries 제거 + 6 help partial 파일 삭제 (`help_{claude,openrouter,huggingface}_{ko,en}.html`) |
| 7. i18n | `messages.po` (ko/en) 의 3 msgid 제거 (Anthropic Console / OpenRouter Settings / HuggingFace token) + `.mo` 재컴파일.  ⚠️ babel.cfg 의 `**.py` 패턴이 recurse 안 해 pot 재추출은 skip (직접 .po 편집 + compile only) |
| 8. docs | `README.md:46`, `AGENTS.md:66`, `DESIGN.md:557`, `HANDOFF.md:144 + :158`, `milestones/ROADMAP.md:24`, `docs/SETUP.md:35`, 5 deepinit AGENTS.md (`core/AGENTS.md`, `core/llm/AGENTS.md`, `core/llm/backends/AGENTS.md`, `web/templates/AGENTS.md`, `core/llm/__init__.py`), `openai_backend.py` 의 OpenRouter 참조 comment |

### 보존 (변경 X)
- `milestones/HISTORY.md` + `milestones/M11_*.md` + `docs/superpowers/specs/*` + `docs/superpowers/plans/*` — historical 기록 유지.
- `palette.neutral` 라벨 — M11.6 tone group enum 의 핵심 토큰 (mood.neutral / mood.minimalist 와 별개).

## 3. 작업 단위

### Phase 0 — Discovery + AC 매핑 (~30 min)
- 6 git grep 으로 ~15 추가 surface 식별 + plan AC 35 항목 매핑.
- baseline 변경 확인: `04c205e` (plan 측정) → `a5c8dbb` (M11.8 머지 후 main) → 실 실측 **1612 passed + 1 skipped + 64 deselected**.

### Phase 1 — 코드 + registry + config 정리 (TDD red→green, ~1.5~2h)
- 1-A: `feat/m11-9-backend-cleanup` 브랜치 + baseline pytest 확인.
- 1-B: `tests/test_m11_9_backend_purge.py` 9 케이스 작성 → **8 failed + 1 passed** (chains default 가 baseline 에서 이미 안전, 자연 PASSED).
- 1-C: 3 backend 모듈 삭제 + registry `_default_*_factory` 3 + 6 kwargs + factory dict 3 엔트리 + stale comment 제거 + config 3 키 + docstring. → **5 PASSED + 4 still red (Phase 2 대상)**.

### Phase 2 — Test + 의존성 + UI/i18n 정리 (~2.5~3h)
- 2-A: 6 mock + LIVE test 파일 + `test_llm_integration_cross_backend.py` (cross-backend 파일 전체) 삭제.
- 2-B: chain (3 cross-backend test 제거) / registry (Claude + OpenRouter + HuggingFace + audio fallback 블록 truncate) / setup_url (scope down to 3 backend) / settings_router (claude → openai swap + 6→3 list + en_partial_for_claude → en_partial_for_openai) / partials (6→3 + `_BACKENDS` tuple) / config_migration (6→3 + 제거 backend 부재 assertion).
- 2-C: `test_llm_backend_supports_batch.py` 의 claude/openrouter/huggingface 3 케이스 제거.
- 2-D: `pyproject.toml` 의 `anthropic` + `huggingface_hub` 2 라인 제거 + `llm_integration` marker description 갱신.
- 2-E: `pip uninstall anthropic huggingface_hub -y` + `pip list | Select-String "anthropic|huggingface|openrouter"` 출력 0 확인.
- 2-F: `settings.html` 의 backend 배열 2 위치 (Jinja loop + JS) + `setupUrls` / `setupLinkLabels` 3 entries 제거.
- 2-G: 6 help partial 파일 삭제.
- 2-H: `messages.po` (ko/en) 3 msgid 제거 + `pybabel compile` 로 .mo 재컴파일.  pot 재추출은 babel.cfg pattern issue 로 skip (직접 .po 편집).
- 2-I: 광역 회귀 → **1560 passed + 1 skipped + 57 deselected** (plan AC #15 band `~1555-1569` 정확 적중).

### Phase 3 — Docs 정리 (~1h)
- README/AGENTS/DESIGN/ROADMAP/SETUP/HANDOFF + 5 deepinit AGENTS.md + 2 코드 comment 모두 6→3 으로 갱신.
- historical (HISTORY/M11_*/superpowers) 미변경 확인.

### Phase 4 — 회귀 final + 옵트인 LIVE + 마일스톤 + PR (~1~1.5h)
- pytest -q 최종 + 옵트인 Gemini + OpenAI LIVE.
- 마일스톤 3종 작성 (본 문서 + todo + verification).
- 커밋 분할 + push + PR draft (한글).

## 4. 테스트 전략

### Red phase (Phase 1-B)
- 9 신규 케이스 (`tests/test_m11_9_backend_purge.py`) — 코드 5 + UI/i18n/partial/import 4 surface 각각 검증.
- Plan §1.2 의 "9 failed" 기대치는 실제로 "8 failed + 1 passed" (chains default 자연 안전 — 충분히 합리적).

### Green phase (Phase 1-C + Phase 2)
- Phase 1-C 직후: 5 / 9 PASSED (code+registry+config surface).
- Phase 2 후: 9 / 9 PASSED.

### 광역 회귀 (Phase 2-I + Phase 4-A)
- baseline `1612 passed` → cleanup 후 `1560 passed` (-52, plan band `1555-1569` 정확 적중).
- 1 skipped 유지 (M11.x SSE heartbeat skip).
- 63→57 deselected (옵트인 6 감소 — claude/openrouter/huggingface integration 3 + cross-backend).

### 옵트인 LIVE (Phase 4-B)
- `pytest -m llm_integration tests/test_llm_backend_gemini_integration.py tests/test_llm_backend_openai_integration.py -v` (사용자 GEMINI_API_KEY + OPENAI_API_KEY 전제).

## 5. 검증 기준

`docs/.omc/plans/consensus-m11-9-backend-cleanup.md` §1.3 AC 35+ 항목 + verification metric 13 종 모두 충족 — 실 결과는 [M11_9_verification.md](./M11_9_verification.md) 참조.
