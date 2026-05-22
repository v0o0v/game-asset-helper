<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# llm

## Purpose
M11 — Multi-backend LLM 추상화. Protocol(`base`) + Chain(`chain`) + Registry(`registry`) 위에 3 backend wrapper (`backends/*`). modality 별 chain 으로 자동 fallback. spec: `docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md`. M11.9 에서 claude/openrouter/huggingface 제거 (6→3).

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | `unwrap_chat_result(result)` — `BackendChain.chat` `(dict, name)` ↔ `OllamaClient.chat` `dict` 양쪽 흡수. Phase 0 transitional helper |
| `base.py` | `Backend` Protocol — `chat(messages, modality)` / `embed(texts)` / `batch_embed` / `supports_batch` 정의 |
| `chain.py` | `BackendChain` — modality 별 backend 우선순위 + 자동 fallback. 결과는 `(payload, backend_name)` 튜플 |
| `registry.py` | `BackendRegistry` — 설정에서 backend instance 빌드 + chain 조합. `/settings` UI 의 backend 토글이 여기로 연결 |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `backends/` | 각 외부 LLM SDK 의 thin wrapper — Ollama / Gemini / OpenAI (see `backends/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- **새 backend 추가 시** — `backends/{name}.py` 신설 + `Backend` Protocol 준수 + `registry.py` 의 builder 등록 + `/settings` UI help card (`web/templates/settings/help_{name}_{lang}.html`) + i18n msgid 추가.
- **modality 별 chain** — `chat_image` / `chat_audio` / `chat_spritesheet` / `embed` / `batch_embed`. 새 modality 신설 시 `chain.py` + 각 backend 의 supports 매트릭스 갱신.
- **`supports_batch`** — 현재는 Gemini 만 True. OpenAI Batch API 는 HANDOFF backlog D (M11.9 에서 Anthropic 백엔드 제거).
- **`unwrap_chat_result`** — analyzer 측에서 backend 가 chain 일 수도 / 단일 client 일 수도 있는 호환. M11 Phase 6 에서 signature 통일 후 deprecate 예정.

### Testing Requirements
- `tests/test_llm_base.py` — Protocol.
- `tests/test_llm_chain.py` + `test_llm_chain_spritesheet.py` — chain fallback + modality.
- `tests/test_llm_registry.py` — registry 빌더.
- `tests/test_llm_backend_supports_batch.py` — supports_batch 매트릭스.
- `tests/test_llm_backend_{name}.py` — unit (mock).  (M11.9: cross-backend smoke 는 chain test 의 fallback assertion 으로 흡수, `test_llm_integration_cross_backend.py` 파일 제거.)
- `tests/test_llm_backend_{name}_integration.py` — 옵트인 `pytest -m llm_integration` (실 API key).  (M11.9: gemini + openai 만 잔존.)

### Common Patterns
- `chain.chat()` 호출 → 1차 backend 실패 시 다음으로 자동 폴백 → 모두 실패 시 raise.
- backend instance 는 stateless (config 만 보유) — thread-safe.

## Dependencies

### Internal
- `../analyzer/` (chain 호출자).
- `../batch/` (Gemini Batch API).
- `../../config.py` (`Config.backends` 설정).

### External
- `httpx` (Ollama), `google-genai`, `openai` (M11.9 에서 `anthropic` / `huggingface_hub` 제거).

<!-- MANUAL: backend 추가 시 /settings help card + i18n msgid + supports 매트릭스 갱신 필수. -->
