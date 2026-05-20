# 2026-05-20 — M11 Multi-backend LLM Architecture Design Spec

## 0. 본 spec 의 위치

- 상위 roadmap: [`2026-05-20-roadmap-design.md`](./2026-05-20-roadmap-design.md) §4 M11.
- 본 spec 은 그 §4 M11 을 implementation-ready 수준까지 구체화. 결정 항목은 §3 ~ §10. `milestones/M11_plan.md` 는 본 spec 의 Phase 분할 (§11) 을 그대로 따른다.
- 본 spec 이후 작업 순서: `milestones/M11_plan.md` → `milestones/M11_todo.md` → TDD cycle (Phase 0 부터).

## 1. 한 줄 요약

현재 Ollama `gemma4:e4b` 가 image + audio + embedding 을 모두 처리 → modality 별 backend chain 으로 분리 + 외부 LLM 5종 추가 (Gemini · Claude · OpenAI · OpenRouter · HuggingFace) + 자동 fallback + /settings UI. 회귀 1079 baseline 은 Phase 0 완료 시 유지 (OllamaBackend wrap 만 변경, 호출 패턴 동일).

## 2. Context — 현재 코드 표면

### 2.1 LLM 호출 진입점 (M0~M10 누적)

`src/assetcache/core/ollama_client.py`:
- `class OllamaClient` — `chat(messages, force_json, num_ctx) -> dict` + `embed(text, model) -> list[float]`
- `class ChatMessage` — `role / content / images_b64 / audio_b64`
- `class OllamaError(stage, path, cause)` — backend-level 실패 분류
- 내부: OpenAI-compatible `/v1/chat/completions` 시도 → 4xx/5xx 시 native `/api/chat` fallback. cold-start retry exponential backoff. `threading.Semaphore(parallel)` 로 동시 호출 cap.

`src/assetcache/core/embedding.py`:
- `class EmbeddingEncoder` — `OllamaClient.embed()` wrap, first-use dim lock, `encode_text(text) -> (blob, dim)`.
- `Protocol _EmbedCapable: def embed(text, *, model) -> list[float]` — 이미 abstraction 의 절반이 있음.

### 2.2 호출 사이트 3 곳

1. `core/analyzer/sprite.py` — `SpriteAnalyzer(ollama: OllamaClient, ...)`. `_call_gemma_with_validation` 안에서 `OllamaClient.chat()` 호출. JSON-strict + 라벨 axis 별 응답.
2. `core/analyzer/sound.py` — `SoundAnalyzer(ollama: OllamaClient, ...)`. 1) 원본 wav base64 → chat (with audio_b64). 2) mel-spectrogram PNG → chat (image fallback). 3) 휴리스틱.
3. `core/analyzer/spritesheet.py` — `SpritesheetAnalyzer` — sheet detection + per-frame chat (M6).

이 외에:
- `config.py` — `ollama_url / model_image / model_audio / model_embed / ollama_parallel / analysis_timeout_seconds / analysis_max_retries`.
- `app.py` — `OllamaClient` instantiation + `EmbeddingEncoder` wiring.
- `web/routers/library.py` 등 — UI 표시 (검색 결과의 description 등 — backend 영향 없음).

### 2.3 회귀 baseline

`pytest -q` → **1079 passed + 1 skipped + 40 deselected** (2026-05-20 검증).

## 3. 결정 매트릭스 — LLMBackend 인터페이스

### 3.1 Protocol vs ABC

Python `typing.Protocol`. ABC 대신 Protocol 선택 이유:
- 기존 `_EmbedCapable` 이 이미 Protocol. 일관성.
- 외부 SDK (`openai.OpenAI`, `anthropic.Anthropic`) 의 인스턴스가 들고 있는 메서드 표면을 그대로 만족시키는 thin wrapper 만 작성하면 됨. 상속 강제 X.
- 테스트에서 fake 만들기 쉬움 — 단순 dict-returning stub.

### 3.2 인터페이스 시그니처

```python
# core/llm/base.py

from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass(frozen=True)
class BackendCapabilities:
    supports_chat_image: bool
    supports_chat_audio: bool
    supports_text_embed: bool
    embed_dim: int | None       # known dim (None = unknown, lock on first use)

@dataclass(frozen=True)
class BackendInfo:
    name: str                    # slug: "ollama" / "gemini" / "claude" / "openai" / "openrouter" / "huggingface"
    display_name: str            # UI: "Google Gemini" 등
    homepage: str                # /settings 의 외부 링크
    capabilities: BackendCapabilities

class BackendError(RuntimeError):
    """모든 backend 가 던지는 통일 에러. transient / hard 분류 caller 가 함."""
    def __init__(self, *, backend: str, stage: str,
                 transient: bool, cause: Exception | None = None) -> None: ...

@runtime_checkable
class LLMBackend(Protocol):
    info: BackendInfo
    def chat(self, messages: list[ChatMessage], *,
             force_json: bool = True, num_ctx: int = 8000) -> dict: ...
    def embed(self, text: str, *, model: str | None = None) -> list[float]: ...
    def test_connection(self) -> bool: ...  # /settings "테스트" 버튼용
```

### 3.3 modality 기반 호출 차단

`backend.info.capabilities.supports_chat_audio` 가 False 면 `BackendChain` 이 audio chain 에서 그 backend 를 건너뜀 (config 에 audio chain 에 등록돼 있어도). Claude (audio 미지원) 가 사용자가 실수로 audio chain 에 추가해도 자동으로 skip 되고 다음 backend 로.

## 4. BackendChain — fallback semantics

### 4.1 호출 흐름

```python
# core/llm/chain.py

class BackendChain:
    def __init__(self, backends: list[LLMBackend], *,
                 modality: Literal["chat_image", "chat_audio", "text_embed"]) -> None: ...

    def chat(self, messages, *, force_json=True, num_ctx=8000) -> tuple[dict, str]:
        """Return (response, backend_name_used)."""
        for backend in self._eligible(self.modality):
            try:
                return backend.chat(messages, force_json=force_json, num_ctx=num_ctx), backend.info.name
            except BackendError as e:
                if not e.transient:
                    raise  # auth fail / quota 영구 — 사용자 알림 필요 (다음 backend 도 별 의미 X 일 가능성 → 일단 단순화: hard 면 chain 중단)
                # transient: rate limit / cold-start retry exhausted / network → 다음 backend
                continue
        raise BackendError(backend="<chain>", stage=self.modality, transient=False)
```

### 4.2 transient vs hard 분류

각 backend wrapper 가 자기 SDK 의 에러를 다음으로 분류:

| 분류 | 예 | 동작 |
|---|---|---|
| **transient** | HTTP 429 / 5xx / connect timeout / cold-start | 다음 backend 로 fallback |
| **hard** | HTTP 401 (auth fail) / 403 (quota exceeded) / 4xx 명시적 거절 | chain 즉시 raise, /settings 배너로 알림 |

config 에 chain[1] auth fail 이면 chain[0] 으로 더 이상 fallback 못 함 — UI 가 사용자에게 즉시 알림.

### 4.3 modality 별 chain 독립

```toml
[chains]
chat_image = ["ollama", "gemini"]
chat_audio = ["ollama"]
text_embed = ["ollama"]
```

embedding chain 은 fallback 안 함 (dim 일관성 위해 1순위만 사용). 사용자가 변경하면 전체 re-embed 권유 (수동 verification 시나리오).

### 4.4 timeout 정책

- per-backend timeout: `analysis_timeout_seconds` 그대로 (default 60s)
- 외부 API backend 는 SDK 의 timeout 옵션을 동일 값으로 강제
- chain total timeout = sum(per-backend timeout) — 사실상 N × 60s 까지 가능. 사용자 분석 큐 ETA 영향 — UI 에서 가시화.

## 5. 6 Backend 상세

| Backend | 패키지 | image | audio | embed | auth | 기본 모델 (시드) | 권장 가치 |
|---|---|:-:|:-:|:-:|---|---|---|
| **ollama** | (이미 있음, httpx 직접 호출) | ✅ | ✅ | ✅ | none | `gemma4:e4b` / `nomic-embed-text` | 로컬, 무료, 오프라인 |
| **gemini** | `google-genai>=0.1` | ✅ | ✅ | ✅ | API key | `gemini-2.5-flash` / `gemini-embedding-001` | 무료 tier + 통합 multimodal |
| **claude** | `anthropic>=0.40` | ✅ | ❌ | ❌ | API key | `claude-haiku-4-5-20251001` | 이미지 라벨 품질, 1M context, 비싸지만 정확 |
| **openai** | `openai>=1.50` | ✅ | ✅ | ✅ | API key | `gpt-5.4-mini` / `text-embedding-3-small` | image+audio 양쪽 양호, paid |
| **openrouter** | `openai>=1.50` (base_url 변경) | ✅ | ❌* | ❌* | API key | `:free` 접미사 모델 (Gemma 4 / Llama 4 / Qwen VL) | 무료 라우팅, 20 req/min |
| **huggingface** | `huggingface_hub>=0.24` | ✅ | ✅ | ✅ | HF token | 사용자 선택 (오픈소스) | 월 small quota, 모델 폭 넓음 |

\* OpenRouter free 모델은 대부분 image-text. audio 지원 모델은 paid only — M11 에선 image chain 에만 노출.

### 5.1 Ollama (wrap, 행동 보존)

`core/llm/backends/ollama.py`:
```python
class OllamaBackend:
    info = BackendInfo(name="ollama", display_name="Ollama (local)",
                       homepage="https://ollama.com/",
                       capabilities=BackendCapabilities(True, True, True, embed_dim=None))
    def __init__(self, client: OllamaClient) -> None: self._c = client
    def chat(self, messages, **kw): return self._c.chat(messages, **kw)
    def embed(self, text, *, model=None): return self._c.embed(text, model=model)
    def test_connection(self):
        try: httpx.get(f"{self._c.base_url}/api/tags", timeout=2.0).raise_for_status(); return True
        except: return False
```

기존 `OllamaClient` 는 그대로 둠. `OllamaBackend` 는 thin wrapper — 회귀 1079 baseline 유지의 핵심.

### 5.2 Gemini

`google-genai` SDK 사용. 통합 멀티모달이라 image+audio 같은 메시지에 함께 보낼 수 있음. embedding 은 `gemini-embedding-001` (768 또는 3072 dim — 모델 선택).

```python
from google import genai
class GeminiBackend:
    def __init__(self, *, api_key, model_image, model_audio, model_embed, timeout):
        self._client = genai.Client(api_key=api_key)
        self.model_image = model_image  # default "gemini-2.5-flash"
        ...
    def chat(self, messages, force_json=True, num_ctx=8000):
        # ChatMessage → contents list (Part.from_bytes(image) / Part.from_bytes(audio))
        # response = self._client.models.generate_content(model=self.model_image_or_audio, contents=...)
        # force_json: response_schema=... 또는 system prompt 에 strict JSON 지시
        ...
```

modality 자동 선택: `messages` 에 audio_b64 있으면 `model_audio`, image_b64 있으면 `model_image` (현재 둘 다 `gemini-2.5-flash` 같음 — 사용자가 다르게 둘 수도).

에러 분류:
- `genai.errors.ServerError` / `503` / `429` → transient
- `401` / `403` / API key invalid → hard

### 5.3 Claude (image only)

`anthropic` SDK. **audio 미지원** — `capabilities.supports_chat_audio = False`. audio chain 에 추가해도 BackendChain 이 skip.

```python
from anthropic import Anthropic
class ClaudeBackend:
    def __init__(self, *, api_key, model_image, timeout):
        self._client = Anthropic(api_key=api_key)
        self.model_image = model_image  # default "claude-haiku-4-5-20251001" (저렴)
    def chat(self, messages, ...):
        # ChatMessage → Anthropic Messages API
        # image: source={"type": "base64", "media_type": "image/png", "data": img_b64}
        # force_json: tool_use 패턴으로 강제 또는 system prompt JSON 지시
        ...
```

에러 분류:
- `anthropic.RateLimitError` / `APIStatusError` 5xx → transient
- `anthropic.AuthenticationError` / `BadRequestError` → hard

### 5.4 OpenAI

`openai` SDK. image (Vision API) + audio (Chat Completions with audio input modality).

```python
from openai import OpenAI
class OpenAIBackend:
    def __init__(self, *, api_key, model_image, model_audio, model_embed, timeout, base_url=None):
        self._client = OpenAI(api_key=api_key, base_url=base_url)  # base_url None → OpenAI
        self.model_image = model_image  # default "gpt-5.4-mini"
        self.model_audio = model_audio  # default "gpt-4o-audio-preview"
        self.model_embed = model_embed  # default "text-embedding-3-small"
```

embedding dim: `text-embedding-3-small` = 1536 / `text-embedding-3-large` = 3072. 사용자가 모델 변경 시 dim 변경 경고.

### 5.5 OpenRouter

OpenAI-compatible — `openai` SDK 그대로 + `base_url="https://openrouter.ai/api/v1"`. `OpenAIBackend` 의 specialization 으로 구현 가능 (or 별도 클래스):

```python
class OpenRouterBackend(OpenAIBackend):
    info = BackendInfo(name="openrouter", display_name="OpenRouter (free routing)",
                       homepage="https://openrouter.ai/", ...)
    def __init__(self, *, api_key, model_image, timeout):
        super().__init__(api_key=api_key, model_image=model_image, model_audio="",
                         model_embed="", timeout=timeout,
                         base_url="https://openrouter.ai/api/v1")
```

기본 모델 시드: `google/gemma-4-27b-it:free` 또는 `meta-llama/llama-4-maverick:free`. capabilities: image only (`supports_chat_audio=False`, `supports_text_embed=False`).

rate limit: 20 req/min, 200 req/day → 429 transient — chain 의 다음 backend 로 fallback.

### 5.6 HuggingFace

`huggingface_hub.InferenceClient`. 모델별 endpoint 매우 다양 — 사용자가 model id 직접 입력.

```python
from huggingface_hub import InferenceClient
class HuggingFaceBackend:
    def __init__(self, *, api_key, model_image, model_audio, model_embed, timeout):
        self._client = InferenceClient(token=api_key)
        ...
    def chat(self, messages, ...):
        # InferenceClient.chat_completion(model=..., messages=[{"role": ..., "content": [...]}])
        ...
```

free tier monthly credit small — 429 transient.

## 6. Config 스키마 (TOML)

### 6.1 새 키 (기존 키와 공존)

```toml
# 기존 키 (M0~M10) — 호환 유지 (Phase 0 의 migration 에서 [backends.ollama] 로 자동 복사)
ollama_url = "http://127.0.0.1:11434"
model_image = "gemma4:e4b"
model_audio = "gemma4:e4b"
model_embed = "nomic-embed-text"
ollama_parallel = 2
analysis_timeout_seconds = 60
analysis_max_retries = 3

# M11 신규
[backends.ollama]
enabled = true
base_url = "http://127.0.0.1:11434"
model_image = "gemma4:e4b"
model_audio = "gemma4:e4b"
model_embed = "nomic-embed-text"

[backends.gemini]
enabled = false
api_key = ""                    # 빈 문자열 → 환경변수 GEMINI_API_KEY 사용
model_image = "gemini-2.5-flash"
model_audio = "gemini-2.5-flash"
model_embed = "gemini-embedding-001"

[backends.claude]
enabled = false
api_key = ""                    # → ANTHROPIC_API_KEY
model_image = "claude-haiku-4-5-20251001"

[backends.openai]
enabled = false
api_key = ""                    # → OPENAI_API_KEY
model_image = "gpt-5.4-mini"
model_audio = "gpt-4o-audio-preview"
model_embed = "text-embedding-3-small"

[backends.openrouter]
enabled = false
api_key = ""                    # → OPENROUTER_API_KEY
model_image = "google/gemma-4-27b-it:free"

[backends.huggingface]
enabled = false
api_key = ""                    # → HF_TOKEN
model_image = "Qwen/Qwen2.5-VL-72B-Instruct"
model_audio = ""                # 사용자가 모델 직접 선택
model_embed = ""

[chains]
chat_image = ["ollama"]
chat_audio = ["ollama"]
text_embed = ["ollama"]
```

### 6.2 마이그레이션 (Phase 0)

`config.py::Config.from_mapping` 가 다음을 수행:
1. 새 `[backends]` 섹션이 없으면 → 기존 키 (`ollama_url` / `model_image` / `model_audio` / `model_embed`) 를 `[backends.ollama]` 로 복사.
2. `[chains]` 가 없으면 → `chat_image = ["ollama"]` 등 기본값.
3. 기존 키도 그대로 유지 (read-only 호환).

위 동작은 `tests/test_config_migration.py` 에서 검증.

### 6.3 API key 저장 — config.toml vs OS keyring vs env var

**결정**: 3-tier precedence:
1. `[backends.X].api_key` config 값 (비어있지 않으면 사용)
2. 환경변수 (`GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY` / `HF_TOKEN`)
3. (없음 — backend disabled)

config.toml 저장은 평문 파일 — OS keyring 채택은 M11 scope 밖 (별도 reactive task 로 검토 가능, `keyring` 패키지 의존성 추가 필요). 사용자가 git 에 config.toml 올리지 않도록 `%APPDATA%` 에 둠 (기존과 동일).

## 7. per-asset metadata — backend_used

### 7.1 DB 스키마 (M11 신규 컬럼)

`assets` 테이블에 3 컬럼 추가:
```sql
ALTER TABLE assets ADD COLUMN backend_image TEXT;
ALTER TABLE assets ADD COLUMN backend_audio TEXT;
ALTER TABLE assets ADD COLUMN backend_embed TEXT;
```

기존 row 의 값: NULL (legacy — UI 에서 "(legacy)" 또는 빈 배지). 재분석 시 채워짐.

`core/store.py` 의 `save_asset_analysis()` 시그니처에 backend names 추가:
```python
def save_asset_analysis(self, *, asset_id, ..., backend_image, backend_audio, backend_embed) -> None: ...
```

### 7.2 검색 결과 노출 (Phase 6)

`find_asset` MCP 도구의 응답에 `backend_used` 필드 추가 — `{"image": "gemini", "audio": "ollama", "embed": "ollama"}`.

웹 UI 의 검색 결과 카드에 backend 배지 (작은 칩) — 클릭하면 /settings 의 해당 backend 강조.

## 8. /settings UI

### 8.1 페이지 구조 (Phase 5)

`/settings` 페이지 (이미 M8 에서 ui_language/ui_theme 용으로 존재) 에 **Backend** 섹션 추가:

```
[Backend]
┌─ Ollama (local) ─────────────────────────┐
│ Enabled [x]   Base URL [127.0.0.1:11434] │
│ Image  [gemma4:e4b]                      │
│ Audio  [gemma4:e4b]                      │
│ Embed  [nomic-embed-text]                │
│                                  [Test] │
└──────────────────────────────────────────┘
┌─ Google Gemini ──────────────────────────┐
│ Enabled [ ]   API key  [····hidden···]   │
│ Image  [gemini-2.5-flash       ▾]        │
│ Audio  [gemini-2.5-flash       ▾]        │
│ Embed  [gemini-embedding-001   ▾]        │
│                                  [Test] │
└──────────────────────────────────────────┘
... (Claude / OpenAI / OpenRouter / HF)

[Chain 우선순위]
Image:  [Ollama] ▼ [Gemini] ▼ [Claude] ▼  (drag-drop)
Audio:  [Ollama] ▼ [Gemini] ▼
Embed:  [Ollama]  ← 단일 (1순위만 사용)

[저장]
```

- backend 카드: HTMX `hx-post` `/settings/backends/<name>` 으로 부분 저장
- chain 순서: HTMX sortable + `hx-post` `/settings/chains` 로 전체 저장
- "Test" 버튼: `hx-post` `/settings/backends/<name>/test` → "✅ 연결 성공" / "❌ <에러>"
- API key 입력: type=password, 저장 후 ····로 마스킹 표시

### 8.2 templates (Jinja)

`web/templates/settings/_backend_card.html` + `_chains_panel.html` 신설. 기존 `settings/index.html` 에 inclusion.

### 8.3 i18n

ko/en `.po` 에 새 msgid 추가:
- `"Backends"` / `"백엔드"`
- `"Image chain"` / `"이미지 체인 우선순위"` (등)
- `"Test connection"` / `"연결 테스트"`
- `"Connection succeeded"` / `"연결 성공"`
- `"Connection failed: %s"` / `"연결 실패: %s"`

### 8.4 보안

- API key 가 응답 JSON 에 포함되지 않음 — 서버는 "******" placeholder 만 반환, 사용자가 다시 입력하지 않으면 기존 값 보존.
- /settings/backends/<name>/test 요청은 CSRF token 필요 (M5 의 기존 pattern 활용).
- log 에 API key prefix 마스킹 (`AIza...***`).

## 9. 회귀 보장 + 테스트 전략

### 9.1 Phase 0 회귀

- 1079 baseline 그대로. `OllamaBackend` wrap 만 변경.
- analyzer 들의 시그니처는 점진 마이그레이션: M11 Phase 0 에서 `SpriteAnalyzer(ollama: OllamaClient, ...)` 시그니처 그대로 유지 (LLMBackend 가 Protocol 이라 OllamaClient 가 자동 만족 X — `OllamaBackend` wrapper 받도록 변경 필요). 단, **호출 패턴은 동일** → 회귀 1079 보장.
- 자세한 Phase 0 회귀 절차: §11.0 참조.

### 9.2 신규 backend 테스트

- 각 backend wrapper 마다 `tests/test_llm_backend_<name>.py` 신설:
  - **mock test** (`respx` for HTTP, `pytest-mock` for SDK) — 기본 실행에 포함
  - **integration test** (`@pytest.mark.llm_integration`) — 실 API key 필요, 기본 deselected
- pyproject.toml `[tool.pytest.ini_options].markers` 에 `llm_integration` 추가, `addopts` 의 `-m 'not ...'` 에도 추가.

### 9.3 BackendChain 테스트

`tests/test_llm_chain.py`:
- 1순위 success → 1순위 결과 반환
- 1순위 transient 실패 + 2순위 success → 2순위 결과 + name="2순위"
- 1순위 hard 실패 → 즉시 raise (2순위 시도 X)
- 모든 backend 실패 → BackendError raise
- modality skip — Claude 가 audio chain 에 있어도 자동 skip
- embedding chain 은 fallback X — 1순위 실패 시 즉시 raise

### 9.4 config migration 테스트

`tests/test_config_migration.py`:
- 기존 키만 있는 config.toml → `[backends.ollama]` 로 migration
- 새 키만 있는 config.toml → 그대로 사용
- 두 가지 모두 있는 config.toml → 새 키 우선 사용
- `[chains]` 누락 → 기본값으로 채워짐

## 10. 알려진 한계 + 후속 마일스톤 의존

### 10.1 M11 scope 밖

- **embedding dim 일치성**: chain 변경으로 dim 바뀌면 검색 cosine 무용지물. M11 은 "변경 시 경고 + 수동 re-embed 권유" 로 해결. 자동 re-embed 는 M12 candidate.
- **OS keyring 채택**: 평문 config.toml 그대로. `keyring` 의존성은 reactive backlog.
- **rate limit token bucket**: 단순 429 transient fallback. 정교한 token bucket / quota tracking 은 M17 (성능).
- **per-asset 분석 시 사용자 선택 backend override**: chain default 만 적용. 사용자가 특정 에셋에 "이건 gemini 로 다시 분석" 같은 명시 override 는 M12 candidate.

### 10.2 후속 의존

- **M12 (측정/벤치마크)**: M11 의 6 backend 결과를 정확도 비교. M11 의 `backend_used` 메타데이터 활용.
- **M13 (Mac/Linux)**: 외부 API backend 들은 OS 영향 거의 없음 — Ollama 의 cross-platform 검증이 핵심.
- **M16 (유사 검색)**: M11 backend 의 image/audio embedding 활용.

## 11. Phase 분할

Phase 별로 commit 가능한 단위. 각 Phase 끝에 `pytest -q` 회귀 확인.

### Phase 0 — Framework + Ollama wrap (회귀 1079)

산출물:
- `src/assetcache/core/llm/__init__.py`
- `src/assetcache/core/llm/base.py` — `BackendInfo / BackendCapabilities / BackendError / LLMBackend (Protocol)` + `ChatMessage` 재수출 (ollama_client.py 에서 가져옴)
- `src/assetcache/core/llm/chain.py` — `BackendChain`
- `src/assetcache/core/llm/registry.py` — config 의 `[backends.*]` + `[chains]` → BackendChain 구성
- `src/assetcache/core/llm/backends/__init__.py`
- `src/assetcache/core/llm/backends/ollama.py` — `OllamaBackend` (기존 `OllamaClient` wrap)
- `config.py` — `[backends.ollama]` / `[chains]` 필드 + migration
- `app.py` — `BackendChain` instantiation, analyzer 에 `BackendChain` 주입 (단, Phase 0 에서는 chain 에 ollama 하나만 — 행동 동일)
- `core/analyzer/sprite.py / sound.py / spritesheet.py` — `OllamaClient` → `BackendChain` 으로 시그니처 변경 (호출 패턴 동일)
- `core/embedding.py` — `OllamaClient` → `BackendChain[modality=text_embed]` 으로 시그니처 변경

신규 테스트:
- `tests/test_llm_base.py` — Protocol 만족 검증 (OllamaBackend isinstance 체크)
- `tests/test_llm_chain.py` — 1순위 success / transient fallback / hard raise / modality skip / 전부 실패
- `tests/test_llm_registry.py` — config → BackendChain instantiation
- `tests/test_config_migration.py` — 기존 키 → `[backends.ollama]` 마이그레이션
- 기존 `tests/test_*_analyzer.py` 들의 fixture 가 `OllamaClient` 대신 `BackendChain` 받도록 갱신 (호출 패턴 동일하니 변경 최소)

회귀: 1079 + 신규 (~15) = 1094.

### Phase 1 — Gemini backend

산출물:
- `pyproject.toml` 에 `google-genai>=0.1` 의존성 추가
- `core/llm/backends/gemini.py` — `GeminiBackend`
- `config.py` — `[backends.gemini]` 필드 + 환경변수 fallback
- `core/llm/registry.py` — gemini 분기

신규 테스트:
- `tests/test_llm_backend_gemini.py` (mock — `respx` 또는 `pytest-mock` 으로 `google.genai.Client` patch)
- `@pytest.mark.llm_integration` 옵트인 케이스 1~2개 (실 API key — chat image + chat audio + embed 라운드)

회귀: Phase 0 + 신규 (~8) ≈ 1102.

### Phase 2 — Claude backend (image only)

산출물:
- `pyproject.toml` 에 `anthropic>=0.40` 의존성 추가
- `core/llm/backends/claude.py` — `ClaudeBackend` (capabilities.supports_chat_audio=False, supports_text_embed=False)
- `config.py` — `[backends.claude]` 필드
- `core/llm/registry.py` — claude 분기

신규 테스트:
- `tests/test_llm_backend_claude.py` (mock + integration 옵트인)
- BackendChain modality skip 검증 — audio chain 에 claude 있어도 skip

회귀: Phase 1 + 신규 (~6) ≈ 1108.

### Phase 3 — OpenAI backend

산출물:
- `pyproject.toml` 에 `openai>=1.50` 의존성 추가 (이미 deps 에 없는지 확인)
- `core/llm/backends/openai_backend.py` — `OpenAIBackend` (모듈명 충돌 회피)
- `config.py` — `[backends.openai]` 필드

신규 테스트:
- `tests/test_llm_backend_openai.py`

회귀: Phase 2 + 신규 (~8) ≈ 1116.

### Phase 4 — OpenRouter + HuggingFace

산출물:
- `core/llm/backends/openrouter.py` — `OpenRouterBackend(OpenAIBackend)` specialization
- `huggingface_hub>=0.24` 의존성 추가
- `core/llm/backends/huggingface.py` — `HuggingFaceBackend`
- `config.py` — `[backends.openrouter]` + `[backends.huggingface]` 필드

신규 테스트:
- `tests/test_llm_backend_openrouter.py`
- `tests/test_llm_backend_huggingface.py`

회귀: Phase 3 + 신규 (~10) ≈ 1126.

### Phase 5 — /settings UI

산출물:
- `web/routers/settings.py` 확장 — `GET/POST /settings/backends` + `POST /settings/backends/<name>` + `POST /settings/backends/<name>/test` + `POST /settings/chains`
- `web/templates/settings/_backend_card.html` + `_chains_panel.html`
- `web/static/css/main.css` 갱신 (backend 카드 + sortable)
- HTMX sortable JS — `web/static/js/sortable.js` 또는 inline (SortableJS CDN 또는 미니멀 자체 구현)
- i18n `.po` msgid 추가 + `pybabel compile`

신규 테스트:
- `tests/test_web_routers_settings_backends.py` (mock backend.test_connection)
- 기존 `tests/test_web_routers_settings.py` 확장

회귀: Phase 4 + 신규 (~10) ≈ 1136.

### Phase 6 — per-asset backend metadata + 가시화

산출물:
- DB 마이그레이션 — `assets.backend_image` / `backend_audio` / `backend_embed` 컬럼 추가 (`core/store.py`)
- `core/analyzer/*.py` — analyzer 결과에 backend name 포함
- `core/store.py::save_asset_analysis` 시그니처 확장
- MCP `find_asset` 응답에 `backend_used` 필드 추가 — `mcp/models.py` + `mcp/tools.py`
- 웹 검색 결과 카드에 backend 배지 — `web/templates/_search_result_card.html` 등
- DESIGN.md §4.5 (MCP 도구) 갱신 — 응답 스키마

신규 테스트:
- `tests/test_store_backend_columns.py` — 마이그레이션 + read/write
- `tests/test_mcp_find_asset_backend.py` — MCP 응답 검증

회귀: Phase 5 + 신규 (~10) ≈ 1146.

### Phase 7 — 통합 + 문서 + verification

산출물:
- `tests/test_llm_integration_cross_backend.py` — Phase 0~6 통합 — chain 의 fallback 이 실제 mock backend 3개로 동작하는지 (1순위 transient → 2순위 hard skip → 3순위 success)
- `milestones/M11_plan.md` (선행 작성) + `milestones/M11_todo.md` + `milestones/M11_verification.md` 갱신
- DESIGN.md §3 (아키텍처) + §4.5 (MCP 도구) + §10 (Config) + §11 (로드맵) 갱신
- HANDOFF.md 갱신
- CLAUDE.md §2 (진행 현황) + §8.3 (마일스톤 정렬) 갱신
- README.md — "Multi-backend LLM" 섹션 신설 + /settings 사용법

수동 verification (`M11_verification.md`):
1. config 마이그레이션 — 기존 사용자 설치 → 새 키 자동 생성 확인
2. /settings 에서 Gemini backend enable + API key + Test 클릭 → ✅ 표시
3. Image chain 에 Gemini 1순위 + Ollama 2순위 → 새 에셋 드롭 → 분석 결과의 `backend_used.image == "gemini"` 확인
4. Gemini API key 일부러 invalid 입력 → 분석 시 자동 Ollama fallback + UI 배너
5. Claude 를 audio chain 에 추가 시도 → /settings 에서 경고 또는 skip 표시
6. embedding chain 변경 → "재분석 권유" 안내 표시 확인

회귀: Phase 6 + 신규 (~5) ≈ 1151. **목표 최종**: ~1150 회귀.

## 12. 출처

### 본 spec 의 web research (2026-05-20)

- [Google Gen AI Python SDK (google-genai)](https://github.com/googleapis/python-genai) + [Models | Gemini API](https://ai.google.dev/gemini-api/docs/models) + [Multimodal Input Guide](https://www.mintlify.com/googleapis/python-genai/guides/multimodal)
- [Anthropic Claude Python SDK](https://github.com/anthropics/anthropic-sdk-python) + [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview) + [Pricing 2026](https://platform.claude.com/docs/en/about-claude/pricing) — image 지원, audio 미지원
- [OpenAI Python SDK Models](https://developers.openai.com/api/docs/models) + [GPT-4o Audio Model](https://developers.openai.com/api/docs/models/gpt-4o-audio-preview) + [Next-generation audio models](https://openai.com/index/introducing-our-next-generation-audio-models/)
- [OpenRouter Free Models 2026](https://costgoat.com/pricing/openrouter-free-models) + [OpenRouter Free Models](https://openrouter.ai/collections/free-models) + [OpenRouter Vision Models](https://openrouter.ai/collections/vision-models)
- [HuggingFace Inference Providers](https://huggingface.co/docs/inference-providers/index) + [Pricing and Rate limits](https://huggingface.co/docs/api-inference/en/pricing)

### 본 프로젝트 historical fact

- `src/assetcache/core/ollama_client.py` (행동 패턴 + cold-start retry + OpenAI-compat fallback) — M11 OllamaBackend wrap 의 baseline
- `src/assetcache/core/embedding.py` (Protocol `_EmbedCapable`) — M11 의 LLMBackend Protocol 의 선례
- `src/assetcache/core/analyzer/{sprite,sound,spritesheet}.py` — 3 호출 사이트
- `2026-05-20-roadmap-design.md` §4 M11 — 본 spec 의 상위 컨테이너

### 향후 참고

- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing) — 비용 가시화 (M12 의존)
- [Anthropic Claude API Pricing](https://docs.claude.com/en/docs/about-claude/pricing)
- [OpenAI API Pricing](https://openai.com/api/pricing/)
- [OpenRouter Free Models 카탈로그](https://openrouter.ai/collections/free-models)
