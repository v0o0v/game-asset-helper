# M11 — TODO 체크리스트

> 본 todo 는 [`docs/superpowers/plans/2026-05-20-m11-multi-backend-llm.md`](../docs/superpowers/plans/2026-05-20-m11-multi-backend-llm.md) 의 phase 진행 상황을 마일스톤 사이클 형식으로 추적.
>
> spec: [`docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md`](../docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md)
> baseline: 1079 passed → 목표 ~1150 passed (+71 신규) + ~14 옵트인

## Phase 0 — Framework + Ollama wrap (~2일, +22 tests, 회귀 1079→1101 critical)

- [ ] Task 0.0 — `feat/m11-multi-backend-llm` 브랜치 분기 + spec/plan 본문 확인 + pytest 1079 baseline 재검증
- [ ] Task 0.1 — `core/llm/__init__.py` + `core/llm/backends/__init__.py` 스켈레톤 (0 신규 테스트, 회귀 1079)
- [ ] Task 0.2 — `core/llm/base.py` `BackendInfo` + `BackendCapabilities` + `BackendError` + `ChatMessage` + `LLMBackend` Protocol + 4 tests (회귀 1083)
- [ ] Task 0.3 — `core/llm/chain.py` `BackendChain` modality skip + transient fallback + hard raise + embed no-fallback + 7 tests (회귀 1090)
- [ ] Task 0.4 — `core/llm/backends/ollama.py` `OllamaBackend` (기존 `OllamaClient` wrap) + `OllamaError` → `BackendError(transient=True)` 변환 + 5 tests (회귀 1095)
- [ ] Task 0.5 — `config.py` `Config.backends` + `Config.chains` 필드 + `_default_backends()` + `_default_chains()` + `from_mapping` migration (legacy 키 → `[backends.ollama]` 백필) + `core/llm/registry.py` `BackendRegistry.from_config` + 6 tests (회귀 1101)
- [ ] Task 0.6 + 0.7 — `app.py` LLM wiring 을 `BackendRegistry.from_config(cfg)` 로 교체 + analyzer 3종 (`sprite/sound/spritesheet`) + `embedding.EmbeddingEncoder` 시그니처 변경 (`ollama: OllamaClient` → `chain_image: BackendChain` 등) + 기존 fixture 갱신 (1 commit). **회귀 1079 baseline 유지가 acceptance**
- [ ] Task 0.8 — Phase 0 wrap-up — `git log` 5 commit 확인 + spec §11 Phase 0 acceptance 체크 + `pytest -q` 최종 `1101 passed` 확인

## Phase 1 — Gemini backend (~1.5일, +6 mock + 3 옵트인)

- [ ] Task 1.0 — `pyproject.toml` `google-genai>=0.1` 의존성 + `[tool.pytest.ini_options]` `llm_integration` marker + `addopts` deselect 추가 + `pip install -e .` + 회귀 1101
- [ ] Task 1.1 — `core/llm/backends/gemini.py` `GeminiBackend` (image+audio+embed, `gemini-2.5-flash` + `gemini-embedding-001`) + auth 401/403 → hard, 429/5xx → transient + `tests/test_llm_backend_gemini.py` 5 mock 케이스 + `registry._default_gemini_factory` 등록 + registry test 1 케이스 (회귀 1107)
- [ ] Task 1.2 — `tests/test_llm_backend_gemini_integration.py` `@pytest.mark.llm_integration` 옵트인 3 케이스 (text chat / test_connection / embed dim 768) + 기본 실행 시 deselect 검증

## Phase 2 — Claude backend (image only, ~1일, +5 mock + 2 옵트인)

- [ ] Task 2.0 — `pyproject.toml` `anthropic>=0.40` 의존성 + 회귀 1107
- [ ] Task 2.1 — `core/llm/backends/claude.py` `ClaudeBackend` (image only, `claude-haiku-4-5-20251001`, `supports_chat_audio=False`, `supports_text_embed=False`) + audio capability=False 자동 skip 검증 + embed() 호출 시 hard `BackendError(transient=False)` + `tests/test_llm_backend_claude.py` 5 mock 케이스 + `tests/test_llm_backend_claude_integration.py` 옵트인 2 케이스 (회귀 1113)
- [ ] Task 2.2 — `registry._default_claude_factory` 등록 + `tests/test_llm_chain.py` 에 "claude on audio chain → skip" 통합 검증 추가 (회귀 1115)

## Phase 3 — OpenAI backend (~1.5일, +5 mock + 3 옵트인)

- [ ] Task 3.0 — `pyproject.toml` `openai>=1.50` 의존성 + 회귀 1115
- [ ] Task 3.1 — `core/llm/backends/openai_backend.py` `OpenAIBackend` (full modality, `gpt-5.4-mini` + `gpt-4o-audio-preview` + `text-embedding-3-small`) + AuthenticationError → hard, RateLimitError/5xx → transient + `base_url` 파라미터 노출 (Phase 4 OpenRouter 위해) + `tests/test_llm_backend_openai.py` 5 mock + `tests/test_llm_backend_openai_integration.py` 옵트인 3 케이스 + `registry._default_openai_factory` 등록 (회귀 1123)

## Phase 4 — OpenRouter + HuggingFace (~1.5일, +10 mock + 4 옵트인)

- [ ] Task 4.1 — `core/llm/backends/openrouter.py` `OpenRouterBackend(OpenAIBackend)` specialization (image only, `base_url="https://openrouter.ai/api/v1"`, `google/gemma-4-27b-it:free` default) + 429 transient (chain fallback) + `tests/test_llm_backend_openrouter.py` 5 mock + 옵트인 2 (회귀 1128)
- [ ] Task 4.2 — `pyproject.toml` `huggingface_hub>=0.24` 의존성 + `core/llm/backends/huggingface.py` `HuggingFaceBackend` (image+audio+embed 사용자 모델 선택) + `tests/test_llm_backend_huggingface.py` 5 mock + 옵트인 2 (회귀 1133)
- [ ] Task 4.3 — `registry._default_openrouter_factory` + `_default_huggingface_factory` 등록 + chain 통합 검증 4 backend 동시 활성 시나리오

## Phase 5 — /settings UI (~2일, +10 tests + 1 e2e)

- [ ] Task 5.1 — `web/templates/settings/_backend_card.html` — Enabled checkbox + API key (password) + model dropdown + "Test" 버튼 HTMX (6 backend 카드)
- [ ] Task 5.2 — `web/templates/settings/_chains_panel.html` — chain drag-drop (SortableJS CDN 또는 Alpine 자체 구현) — chat_image / chat_audio / text_embed 3 영역
- [ ] Task 5.3 — `web/routers/settings.py` 확장 — `POST /settings/backends/<name>` (form 저장) + `POST /settings/backends/<name>/test` (test_connection 호출) + `POST /settings/chains` (순서 저장) + `tests/test_web_routers_settings_backends.py` 6 케이스
- [ ] Task 5.4 — i18n msgid 8건 — ko/en `.po` 추가 ("Backends" / "이미지/오디오/임베딩 체인" / "API key" / "Test connection" / "Connection succeeded" / "Connection failed: %s") + `pybabel compile`
- [ ] Task 5.5 — `web/static/css/main.css` 갱신 (backend 카드 + sortable + 배지) + 다크 테마 호환 검증
- [ ] Task 5.6 — `tests/test_e2e_settings_backends.py` `@pytest.mark.e2e` Playwright 1 시나리오 (Gemini enable → API key 입력 → 저장 → test 클릭 → 결과 표시)

## Phase 6 — per-asset metadata + 가시화 (~1일, +8 tests)

- [ ] Task 6.1 — `core/store.py` 마이그레이션 — `assets.backend_image` / `backend_audio` / `backend_embed` TEXT 컬럼 추가 (legacy row NULL) + `save_asset_analysis()` 시그니처 확장 + `tests/test_store_backend_columns.py` 5 케이스
- [ ] Task 6.2 — `mcp/models.py` `FindAssetItem.backend_used: dict[str, str] | None` + `mcp/tools.py` find_asset 핸들러에서 store 의 backend_* 컬럼 매핑 + `docs/MCP_USAGE_GUIDE.md` 갱신 + `tests/test_mcp_find_asset_backend.py` 3 케이스
- [ ] Task 6.3 — `web/templates/_search_result_card.html` (또는 검색 카드 템플릿) 에 backend 배지 추가 — `{% if result.backend_used %}<span class="badge backend-badge">{{ result.backend_used.image }}</span>{% endif %}` + analyzer 들이 결과에 backend name 포함하도록 (Phase 0 의 `chain.chat()` 튜플 반환 활용)

## Phase 7 — verification + 문서 + PR (~1일, +5 tests)

- [ ] Task 7.1 — `tests/test_llm_integration_cross_backend.py` — fake backend 3개로 chain fallback 실제 시나리오 (transient → fallback / hard → 즉시 raise / modality skip / 전체 실패) 5 케이스
- [ ] Task 7.2 — `DESIGN.md` 갱신 — §3 (아키텍처 `core/llm/` 다이어그램) + §4.5 (MCP find_asset 응답 schema 의 `backend_used`) + §10 (Config `[backends.*]` + `[chains]`) + §11 (로드맵 M11 ✅)
- [ ] Task 7.3 — `README.md` "Multi-backend LLM" 섹션 신설 — /settings 사용법 + 6 backend 비교 표 + 환경변수 alternative (GEMINI_API_KEY 등)
- [ ] Task 7.4 — `HANDOFF.md` 갱신 (§1 한 줄 요약 + §2 검증된 사실 표 + §5/§6 마일스톤 정렬) + `CLAUDE.md` 갱신 (§2 진행 현황 표 M11 row + §6 pytest 수 + §8.3 마일스톤 정렬)
- [ ] Task 7.5 — `milestones/M11_verification.md` — spec §11 Phase 7 의 수동 시나리오 6건 (config 마이그레이션 / Gemini enable + test / image chain 1순위 변경 + 분석 / 잘못된 API key fallback / Claude audio skip / embedding chain 변경 시 경고) + 자동 검증 결과 (pytest 1150)
- [ ] Task 7.6 — M11 PR — `git push -u origin feat/m11-multi-backend-llm` + `gh pr create` (제목 + body summary + verification + Generated with badge) + main 머지 후 cleanup (브랜치 delete)
