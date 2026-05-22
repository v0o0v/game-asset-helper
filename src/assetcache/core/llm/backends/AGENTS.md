<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# backends

## Purpose
6개 외부 LLM SDK 의 thin wrapper. 각 모듈은 `Backend` Protocol (`../base.py`) 준수 — `chat(messages, modality)` / `embed(texts)` / `batch_embed` / `supports_batch`. SDK 별 호환 차이는 여기서 흡수해 analyzer/batch 코드를 단순 유지.

## Key Files
| File | Description |
|------|-------------|
| `ollama.py` | Ollama 백엔드 — `gemma4:e4b` 멀티모달 (이미지 + 오디오) + `nomic-embed-text` 임베딩. 1차 추천 백엔드 |
| `gemini.py` | Google Gemini — `gemini-2.0-flash` chat + `text-embedding-004` embed + **Gemini Batch API** (`supports_batch=True`, 50% 비용, M11.1) |
| `claude.py` | Anthropic Claude — chat 만. embed 미지원 |
| `openai_backend.py` | OpenAI — chat + embed (`text-embedding-3-small`). `openai_backend.py` 명명은 SDK 이름 `openai` 와 충돌 회피 |
| `openrouter.py` | OpenRouter — OpenAI 호환 endpoint, 다양한 모델 라우팅 |
| `huggingface.py` | HuggingFace Inference — `huggingface_hub` 기반, image / text |

## For AI Agents

### Working In This Directory
- 각 backend 는 **stateless** + thread-safe. config (API key, model, base_url) 만 보유.
- **SDK import 는 모듈 top-level 에서** — 의존성이 빠지면 ImportError 가 명확하게 발생하도록. 단, 트레이 부팅 시 모든 backend 가 항상 사용 가능해야 하는 건 아니므로 registry 가 graceful 로 흡수.
- **modality 매트릭스** — Ollama 만 audio native. 다른 backend 는 멜 스펙트로그램 이미지 폴백.
- **batch 매트릭스** — 현재 Gemini 만 `supports_batch=True`. OpenAI Batch API + Anthropic Batch API 추가는 HANDOFF backlog D (1~2일 작업).
- **Gemini batch_embed** — M11.3 patch 후 `inlined_requests` 는 `{"contents":[...]}` 단일 dict 로 wrapping (이전엔 list of dict 라 422 발생).
- **OpenAI 호환** — OpenRouter 와 OpenAI 가 같은 wire format. 단 모델명 라우팅 prefix 차이.

### Testing Requirements
- `tests/test_llm_backend_{name}.py` — unit (respx / pytest-mock).
- `tests/test_llm_backend_{name}_integration.py` — 옵트인 `pytest -m llm_integration` (실 API key, ~6 시나리오 PASSED 목표).
- `tests/test_llm_backend_gemini_batch.py` + `test_llm_backend_gemini_batch_integration.py` — batch API.
- `tests/test_llm_backend_gemini_inventory_item_integration.py` — M11.4 신규 category 옵트인.

### Common Patterns
- HTTP 호출은 `httpx` 또는 SDK 의 내장 클라이언트. timeout 명시 (Ollama 기본 5분, 다른 SDK 는 default).
- 응답 JSON 파싱은 analyzer 의 `payload_parser` 가 모두 흡수 — backend 는 raw payload 만 반환.

## Dependencies

### Internal
- `../base.py` (Backend Protocol).
- `../../analyzer/messages.py` (BATCH_* 프롬프트 — backend 와 별개로 prompt 는 analyzer 가 보유).

### External
- `httpx` (Ollama).
- `google-genai>=0.1` (Gemini).
- `anthropic>=0.40` (Claude).
- `openai>=1.50` (OpenAI + OpenRouter).
- `huggingface_hub>=0.24` (HF).

<!-- MANUAL: openai_backend.py 의 _backend 접미사는 SDK `import openai` 와의 충돌 회피용. 다른 backend 와 명명 비대칭이지만 의도적. -->
