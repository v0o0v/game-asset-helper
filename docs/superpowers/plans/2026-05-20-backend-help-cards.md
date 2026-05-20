# Backend 카드 가격·셋업 안내 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** /settings 페이지의 6 backend 카드에 API key 발급 페이지 direct link + 가격/셋업 안내 (details/summary 접힘) 추가.

**Architecture:** `BackendInfo.setup_url` 신규 필드 + 12 partial 파일 (6 backend × ko/en) + settings.html 의 `<details>` block + Alpine `setupUrls`/`setupLinkLabels` 데이터 + i18n msgid 7건. partial 본문은 msgid 없음 (한국어/영어 직접 작성), 한 줄 link label 과 details summary 만 i18n.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, Alpine.js, Babel gettext, pytest.

**Spec:** [`docs/superpowers/specs/2026-05-20-backend-help-cards-design.md`](../specs/2026-05-20-backend-help-cards-design.md)
**Branch:** `feat/m11-multi-backend-llm` (M11 PR 에 누적, v0.2.0 함께 publish)
**예상 회귀**: 1239 → 1243 (+4 신규)

---

## File Structure

**생성**:
- `src/assetcache/web/templates/settings/help_ollama_ko.html` (Task 2)
- `src/assetcache/web/templates/settings/help_ollama_en.html` (Task 2)
- `src/assetcache/web/templates/settings/help_gemini_ko.html` (Task 2)
- `src/assetcache/web/templates/settings/help_gemini_en.html` (Task 2)
- `src/assetcache/web/templates/settings/help_claude_ko.html` (Task 2)
- `src/assetcache/web/templates/settings/help_claude_en.html` (Task 2)
- `src/assetcache/web/templates/settings/help_openai_ko.html` (Task 2)
- `src/assetcache/web/templates/settings/help_openai_en.html` (Task 2)
- `src/assetcache/web/templates/settings/help_openrouter_ko.html` (Task 2)
- `src/assetcache/web/templates/settings/help_openrouter_en.html` (Task 2)
- `src/assetcache/web/templates/settings/help_huggingface_ko.html` (Task 2)
- `src/assetcache/web/templates/settings/help_huggingface_en.html` (Task 2)
- `tests/test_backend_info_setup_url.py` (Task 1)
- `tests/test_settings_partials_exist.py` (Task 2)

**수정**:
- `src/assetcache/core/llm/base.py` — `BackendInfo` dataclass `setup_url` field (Task 1)
- `src/assetcache/core/llm/backends/ollama.py` — setup_url 박기 (Task 1)
- `src/assetcache/core/llm/backends/gemini.py` — setup_url 박기 (Task 1)
- `src/assetcache/core/llm/backends/claude.py` — setup_url 박기 (Task 1)
- `src/assetcache/core/llm/backends/openai_backend.py` — setup_url 박기 (Task 1)
- `src/assetcache/core/llm/backends/openrouter.py` — setup_url 박기 (Task 1)
- `src/assetcache/core/llm/backends/huggingface.py` — setup_url 박기 (Task 1)
- `src/assetcache/web/routers/settings.py` — settings_page 가 lang 컨텍스트 전달 (Task 3)
- `src/assetcache/web/templates/settings.html` — details block + 한 줄 link + Alpine setupUrls (Task 3)
- `src/assetcache/web/locale/ko/LC_MESSAGES/messages.po` — msgid 7건 추가 (Task 3)
- `src/assetcache/web/locale/en/LC_MESSAGES/messages.po` — msgid 7건 추가 (Task 3)
- `src/assetcache/web/locale/ko/LC_MESSAGES/messages.mo` — 컴파일 (Task 3)
- `src/assetcache/web/locale/en/LC_MESSAGES/messages.mo` — 컴파일 (Task 3)
- `tests/test_settings_router_m11.py` — ko/en 렌더링 2 케이스 추가 (Task 3)

---

## Task 1: `BackendInfo.setup_url` 필드 + 6 backend 박기

**Files:**
- Modify: `src/assetcache/core/llm/base.py` (BackendInfo dataclass)
- Modify: `src/assetcache/core/llm/backends/{ollama,gemini,claude,openai_backend,openrouter,huggingface}.py`
- Create: `tests/test_backend_info_setup_url.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_backend_info_setup_url.py`:

```python
"""M11 후속 — BackendInfo.setup_url 필드 + 6 backend 별 정확한 URL."""

from __future__ import annotations

from assetcache.core.llm.backends.claude import ClaudeBackend
from assetcache.core.llm.backends.gemini import GeminiBackend
from assetcache.core.llm.backends.huggingface import HuggingFaceBackend
from assetcache.core.llm.backends.ollama import OllamaBackend
from assetcache.core.llm.backends.openai_backend import OpenAIBackend
from assetcache.core.llm.backends.openrouter import OpenRouterBackend


def test_backend_info_has_setup_url_field():
    """BackendInfo dataclass 에 setup_url 필드 존재."""
    info = OllamaBackend.info
    assert hasattr(info, "setup_url")


def test_ollama_setup_url():
    assert OllamaBackend.info.setup_url == "https://ollama.com/download"


def test_gemini_setup_url():
    assert GeminiBackend.info.setup_url == "https://aistudio.google.com/apikey"


def test_claude_setup_url():
    assert (
        ClaudeBackend.info.setup_url
        == "https://console.anthropic.com/settings/keys"
    )


def test_openai_setup_url():
    assert OpenAIBackend.info.setup_url == "https://platform.openai.com/api-keys"


def test_openrouter_setup_url():
    assert OpenRouterBackend.info.setup_url == "https://openrouter.ai/settings/keys"


def test_huggingface_setup_url():
    assert (
        HuggingFaceBackend.info.setup_url
        == "https://huggingface.co/settings/tokens"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_backend_info_setup_url.py -v
```

Expected: 7 FAILED — `AttributeError: 'BackendInfo' object has no attribute 'setup_url'` (또는 첫 테스트만 attribute error, 나머지는 AttributeError on dataclass).

- [ ] **Step 3: Add `setup_url` field to BackendInfo**

Edit `src/assetcache/core/llm/base.py`:

```python
@dataclass(frozen=True)
class BackendInfo:
    name: str
    display_name: str
    homepage: str
    capabilities: BackendCapabilities
    setup_url: str | None = None  # M11 후속 — API key 발급 (또는 ollama 설치) 직접 link
```

(기존 4 필드 유지 + 5번째 `setup_url: str | None = None` default 추가)

- [ ] **Step 4: Add `setup_url` to each backend's `info`**

Edit `src/assetcache/core/llm/backends/ollama.py` 의 `OllamaBackend.info`:

```python
class OllamaBackend:
    info = BackendInfo(
        name="ollama",
        display_name="Ollama (local)",
        homepage="https://ollama.com/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=True,
            supports_text_embed=True,
            embed_dim=None,
        ),
        setup_url="https://ollama.com/download",
    )
```

Edit `src/assetcache/core/llm/backends/gemini.py` 의 `GeminiBackend.info`:

```python
class GeminiBackend:
    info = BackendInfo(
        name="gemini",
        display_name="Google Gemini",
        homepage="https://ai.google.dev/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=True,
            supports_text_embed=True,
            embed_dim=768,
        ),
        setup_url="https://aistudio.google.com/apikey",
    )
```

Edit `src/assetcache/core/llm/backends/claude.py` 의 `ClaudeBackend.info`:

```python
class ClaudeBackend:
    info = BackendInfo(
        name="claude",
        display_name="Anthropic Claude",
        homepage="https://docs.claude.com/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=False,
            supports_text_embed=False,
            embed_dim=None,
        ),
        setup_url="https://console.anthropic.com/settings/keys",
    )
```

Edit `src/assetcache/core/llm/backends/openai_backend.py` 의 `OpenAIBackend.info`:

```python
class OpenAIBackend:
    info = BackendInfo(
        name="openai",
        display_name="OpenAI",
        homepage="https://platform.openai.com/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=True,
            supports_text_embed=True,
            embed_dim=1536,
        ),
        setup_url="https://platform.openai.com/api-keys",
    )
```

Edit `src/assetcache/core/llm/backends/openrouter.py` 의 `OpenRouterBackend.info`:

```python
class OpenRouterBackend(OpenAIBackend):
    info = BackendInfo(
        name="openrouter",
        display_name="OpenRouter (free routing)",
        homepage="https://openrouter.ai/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=False,
            supports_text_embed=False,
            embed_dim=None,
        ),
        setup_url="https://openrouter.ai/settings/keys",
    )
```

Edit `src/assetcache/core/llm/backends/huggingface.py` 의 `HuggingFaceBackend.info`:

```python
class HuggingFaceBackend:
    info = BackendInfo(
        name="huggingface",
        display_name="HuggingFace Inference",
        homepage="https://huggingface.co/docs/inference-providers/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=True,
            supports_text_embed=True,
            embed_dim=None,
        ),
        setup_url="https://huggingface.co/settings/tokens",
    )
```

- [ ] **Step 5: Run test to verify it passes**

```powershell
pytest tests/test_backend_info_setup_url.py -v
```

Expected: 7 PASSED.

- [ ] **Step 6: Full regression**

```powershell
pytest -q
```

Expected: `1246 passed + 1 skipped + 53 deselected` (1239 baseline + 7 신규).

- [ ] **Step 7: Commit**

```powershell
git add src/assetcache/core/llm/base.py src/assetcache/core/llm/backends/ollama.py src/assetcache/core/llm/backends/gemini.py src/assetcache/core/llm/backends/claude.py src/assetcache/core/llm/backends/openai_backend.py src/assetcache/core/llm/backends/openrouter.py src/assetcache/core/llm/backends/huggingface.py tests/test_backend_info_setup_url.py
git commit -m "feat(m11+): BackendInfo.setup_url + 6 backend best-known URL + 7 테스트"
```

---

## Task 2: 12 partial 파일 (6 backend × ko/en) + existence 테스트

**Files:**
- Create: `src/assetcache/web/templates/settings/help_<name>_<lang>.html` × 12
- Create: `tests/test_settings_partials_exist.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_partials_exist.py`:

```python
"""M11 후속 — 12 backend help partial 파일이 모두 존재."""

from __future__ import annotations

from pathlib import Path


_TEMPLATES_DIR = (
    Path(__file__).parent.parent / "src" / "assetcache" / "web" / "templates" / "settings"
)

_BACKENDS = ("ollama", "gemini", "claude", "openai", "openrouter", "huggingface")
_LANGS = ("ko", "en")


def test_settings_partial_dir_exists():
    assert _TEMPLATES_DIR.is_dir(), f"{_TEMPLATES_DIR} not found"


def test_all_12_partials_exist():
    missing = []
    for name in _BACKENDS:
        for lang in _LANGS:
            partial = _TEMPLATES_DIR / f"help_{name}_{lang}.html"
            if not partial.is_file():
                missing.append(partial.name)
    assert not missing, f"missing partials: {missing}"


def test_partials_have_disclaimer_class_when_external():
    """external provider (ollama 제외 5개) partial 은 disclaimer 문구 포함."""
    for name in ("gemini", "claude", "openai", "openrouter", "huggingface"):
        for lang in _LANGS:
            partial = _TEMPLATES_DIR / f"help_{name}_{lang}.html"
            content = partial.read_text(encoding="utf-8")
            assert (
                'class="disclaimer"' in content
            ), f"{partial.name} missing disclaimer class"
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_settings_partials_exist.py -v
```

Expected: FAILED — directory 또는 파일 부재.

- [ ] **Step 3: Create 12 partial files**

Create `src/assetcache/web/templates/settings/help_ollama_ko.html`:

```html
{# Ollama (local) — 무료 + 단계별 셋업 #}
<p><strong>무료</strong> · 자기 PC 에서 동작</p>
<ol>
  <li><a href="https://ollama.com/download" target="_blank" rel="noopener noreferrer">Ollama 설치</a> (Windows / Mac / Linux 모두 지원)</li>
  <li>터미널 열고: <code>ollama pull gemma4:e4b</code> (≈ 9.6 GB 다운로드)</li>
  <li>확인: <code>ollama list</code> → <code>gemma4:e4b</code> 가 보이면 OK</li>
</ol>
<p>위 모델 입력란의 기본값 <code>gemma4:e4b</code> 와 모델 ID 가 동일해야 합니다.</p>
```

Create `src/assetcache/web/templates/settings/help_ollama_en.html`:

```html
{# Ollama (local) — free + step-by-step setup #}
<p><strong>Free</strong> · runs on your PC</p>
<ol>
  <li><a href="https://ollama.com/download" target="_blank" rel="noopener noreferrer">Install Ollama</a> (Windows / Mac / Linux supported)</li>
  <li>Open a terminal: <code>ollama pull gemma4:e4b</code> (≈ 9.6 GB download)</li>
  <li>Verify: <code>ollama list</code> → <code>gemma4:e4b</code> should be listed</li>
</ol>
<p>The model ID in the input above must match <code>gemma4:e4b</code> (the default).</p>
```

Create `src/assetcache/web/templates/settings/help_gemini_ko.html`:

```html
{# Gemini — 무료 tier 있음 #}
<p><strong>무료 tier 있음</strong> · 카드 등록 불필요</p>
<ul>
  <li><code>gemini-2.5-flash</code>: 무료 1,500 req/day · 15 req/min · 1M token/min</li>
  <li>유료: input $0.30 / output $2.50 per 1M tokens</li>
  <li>일반적인 개인 사용은 무료 tier 로 충분</li>
</ul>
<p class="disclaimer">
  <em>2026-05 기준. 최신은 <a href="https://ai.google.dev/gemini-api/docs/pricing" target="_blank" rel="noopener noreferrer">공식 가격 페이지</a> 참조.</em>
</p>
```

Create `src/assetcache/web/templates/settings/help_gemini_en.html`:

```html
{# Gemini — free tier available #}
<p><strong>Free tier available</strong> · no credit card required</p>
<ul>
  <li><code>gemini-2.5-flash</code>: free 1,500 req/day · 15 req/min · 1M token/min</li>
  <li>Paid: input $0.30 / output $2.50 per 1M tokens</li>
  <li>Personal use typically fits within the free tier</li>
</ul>
<p class="disclaimer">
  <em>As of 2026-05. See <a href="https://ai.google.dev/gemini-api/docs/pricing" target="_blank" rel="noopener noreferrer">official pricing page</a> for current rates.</em>
</p>
```

Create `src/assetcache/web/templates/settings/help_claude_ko.html`:

```html
{# Claude — 유료 only #}
<p><strong>유료 only</strong> · 첫 가입 시 $5 trial credit</p>
<ul>
  <li><code>claude-haiku-4-5</code>: input $1 / output $5 per 1M tokens</li>
  <li>이미지 분석 1회 ≈ 1.5K input tokens (대략) → 1만 장 ≈ $15 input + 응답 토큰</li>
  <li>이미지 전용 (오디오 / 임베딩 미지원)</li>
</ul>
<p class="disclaimer">
  <em>2026-05 기준. 최신은 <a href="https://platform.claude.com/docs/en/about-claude/pricing" target="_blank" rel="noopener noreferrer">공식 가격 페이지</a> 참조.</em>
</p>
```

Create `src/assetcache/web/templates/settings/help_claude_en.html`:

```html
{# Claude — paid only #}
<p><strong>Paid only</strong> · $5 trial credit on signup</p>
<ul>
  <li><code>claude-haiku-4-5</code>: input $1 / output $5 per 1M tokens</li>
  <li>Image analysis ≈ 1.5K input tokens per call (rough) → 10K images ≈ $15 input + response</li>
  <li>Image only (no audio / embedding support)</li>
</ul>
<p class="disclaimer">
  <em>As of 2026-05. See <a href="https://platform.claude.com/docs/en/about-claude/pricing" target="_blank" rel="noopener noreferrer">official pricing page</a> for current rates.</em>
</p>
```

Create `src/assetcache/web/templates/settings/help_openai_ko.html`:

```html
{# OpenAI — 유료 only #}
<p><strong>유료 only</strong> · 첫 가입 시 $5 trial credit</p>
<ul>
  <li><code>gpt-4o-mini</code>: input $2.50 / output $10 per 1M tokens (또는 <code>gpt-4.1-mini</code> $0.40 / $1.60 권장)</li>
  <li><code>text-embedding-3-small</code>: $0.02 per 1M tokens (1만 텍스트 ≈ $0.01 정도, 매우 저렴)</li>
  <li>이미지 + 오디오 + 임베딩 모두 지원</li>
</ul>
<p class="disclaimer">
  <em>2026-05 기준. 최신은 <a href="https://openai.com/api/pricing/" target="_blank" rel="noopener noreferrer">공식 가격 페이지</a> 참조.</em>
</p>
```

Create `src/assetcache/web/templates/settings/help_openai_en.html`:

```html
{# OpenAI — paid only #}
<p><strong>Paid only</strong> · $5 trial credit on signup</p>
<ul>
  <li><code>gpt-4o-mini</code>: input $2.50 / output $10 per 1M tokens (or <code>gpt-4.1-mini</code> $0.40 / $1.60, recommended)</li>
  <li><code>text-embedding-3-small</code>: $0.02 per 1M tokens (10K texts ≈ $0.01, very cheap)</li>
  <li>Supports image + audio + embedding</li>
</ul>
<p class="disclaimer">
  <em>As of 2026-05. See <a href="https://openai.com/api/pricing/" target="_blank" rel="noopener noreferrer">official pricing page</a> for current rates.</em>
</p>
```

Create `src/assetcache/web/templates/settings/help_openrouter_ko.html`:

```html
{# OpenRouter — 무료 tier 있음, 25+ 무료 모델 #}
<p><strong>무료 tier 있음</strong> · 25+ 개 무료 모델 · 카드 등록 불필요</p>
<ul>
  <li>무료: 50 req/day (카드 없음) · $10 credit 추가 시 1,000 req/day</li>
  <li>무료 모델 예: <code>google/gemma-4-27b-it:free</code>, <code>meta-llama/llama-4-70b-instruct:free</code></li>
  <li>유료 모델: provider 가격 동일 pass-through (OpenRouter 추가 수수료 없음)</li>
  <li>이미지 전용 (오디오 / 임베딩 미지원)</li>
</ul>
<p class="disclaimer">
  <em>2026-05 기준. 최신은 <a href="https://openrouter.ai/pricing" target="_blank" rel="noopener noreferrer">공식 가격 페이지</a> 참조.</em>
</p>
```

Create `src/assetcache/web/templates/settings/help_openrouter_en.html`:

```html
{# OpenRouter — free tier available, 25+ free models #}
<p><strong>Free tier available</strong> · 25+ free models · no credit card required</p>
<ul>
  <li>Free: 50 req/day (no card) · 1,000 req/day with $10 credit added</li>
  <li>Free model examples: <code>google/gemma-4-27b-it:free</code>, <code>meta-llama/llama-4-70b-instruct:free</code></li>
  <li>Paid models: provider pricing pass-through (no OpenRouter markup)</li>
  <li>Image only (no audio / embedding support)</li>
</ul>
<p class="disclaimer">
  <em>As of 2026-05. See <a href="https://openrouter.ai/pricing" target="_blank" rel="noopener noreferrer">official pricing page</a> for current rates.</em>
</p>
```

Create `src/assetcache/web/templates/settings/help_huggingface_ko.html`:

```html
{# HuggingFace — 무료 monthly credits, PRO $9/month #}
<p><strong>무료 tier (월 credits)</strong> · PRO $9/month</p>
<ul>
  <li>무료: 월 small credits — 가벼운 테스트용 (정확한 양은 비공개)</li>
  <li>PRO ($9/month): 20× credits (약 2M monthly usage)</li>
  <li>모델별 가격: provider pass-through (HuggingFace 추가 수수료 없음)</li>
  <li>이미지 + 오디오 + 임베딩 모두 지원 (모델 선택에 따라)</li>
</ul>
<p class="disclaimer">
  <em>2026-05 기준. 최신은 <a href="https://huggingface.co/docs/inference-providers/pricing" target="_blank" rel="noopener noreferrer">공식 가격 페이지</a> 참조.</em>
</p>
```

Create `src/assetcache/web/templates/settings/help_huggingface_en.html`:

```html
{# HuggingFace — free monthly credits, PRO $9/month #}
<p><strong>Free tier (monthly credits)</strong> · PRO $9/month</p>
<ul>
  <li>Free: small monthly credits — for light testing (exact amount undisclosed)</li>
  <li>PRO ($9/month): 20× credits (~2M monthly usage)</li>
  <li>Per-model pricing: provider pass-through (no HuggingFace markup)</li>
  <li>Supports image + audio + embedding (depending on selected model)</li>
</ul>
<p class="disclaimer">
  <em>As of 2026-05. See <a href="https://huggingface.co/docs/inference-providers/pricing" target="_blank" rel="noopener noreferrer">official pricing page</a> for current rates.</em>
</p>
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_settings_partials_exist.py -v
```

Expected: 3 PASSED (dir exists + 12 files exist + 10 partials have disclaimer).

- [ ] **Step 5: Full regression**

```powershell
pytest -q
```

Expected: `1249 passed + 1 skipped + 53 deselected` (1246 + 3 신규).

- [ ] **Step 6: Commit**

```powershell
git add src/assetcache/web/templates/settings/ tests/test_settings_partials_exist.py
git commit -m "feat(m11+): 12 backend help partial 파일 (ko/en × 6 backend) + 3 테스트"
```

---

## Task 3: settings.html details/summary + Alpine setupUrls + i18n + 라우터 lang context

**Files:**
- Modify: `src/assetcache/web/routers/settings.py` (lang context 추가)
- Modify: `src/assetcache/web/templates/settings.html` (details block + 한 줄 link + Alpine)
- Modify: `src/assetcache/web/locale/ko/LC_MESSAGES/messages.po` (+7 msgid)
- Modify: `src/assetcache/web/locale/en/LC_MESSAGES/messages.po` (+7 msgid)
- Modify: `src/assetcache/web/locale/ko/LC_MESSAGES/messages.mo` (compile)
- Modify: `src/assetcache/web/locale/en/LC_MESSAGES/messages.mo` (compile)
- Modify: `tests/test_settings_router_m11.py` (+2 ko/en 렌더링 케이스)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_settings_router_m11.py`:

```python
def test_settings_page_includes_ko_partial_for_gemini(client, web_deps):
    """ko locale 일 때 gemini 카드의 details block 안에 ko partial 본문 포함."""
    web_deps.config.ui_language = "ko"
    r = client.get("/settings", headers={"Accept-Language": "ko"})
    assert r.status_code == 200
    body = r.text
    # gemini ko partial 의 식별 가능한 본문
    assert "무료 tier 있음" in body
    assert "1,500 req/day" in body
    # setup link label (i18n msgid)
    assert "Google AI Studio" in body


def test_settings_page_includes_en_partial_for_claude(client, web_deps):
    """en locale 일 때 claude 카드의 details block 안에 en partial 본문 포함."""
    web_deps.config.ui_language = "en"
    r = client.get("/settings", headers={"Accept-Language": "en"})
    assert r.status_code == 200
    body = r.text
    # claude en partial 의 식별 가능한 본문
    assert "Paid only" in body
    assert "claude-haiku-4-5" in body
    # setup link label (en msgid)
    assert "Anthropic Console" in body
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_settings_router_m11.py::test_settings_page_includes_ko_partial_for_gemini tests/test_settings_router_m11.py::test_settings_page_includes_en_partial_for_claude -v
```

Expected: 2 FAILED — partial 본문 미포함.

- [ ] **Step 3: Add `lang` context variable to settings router**

Edit `src/assetcache/web/routers/settings.py` 의 `settings_page` 핸들러:

```python
@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """설정 페이지 — 언어 / 테마 / 자동 시작 + M11 backend / chain."""
    deps = request.app.state.deps
    templates = request.app.state.templates
    # M11+ — partial include 에 사용할 lang 변수. LocaleMiddleware 가 request.state.lang
    # 셋팅. 없으면 "en" 폴백.
    lang = getattr(request.state, "lang", "en")
    if lang not in ("ko", "en"):
        lang = "en"
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "page": "settings",
            "config": deps.config,
            "autostart_actual": _autostart_mod.is_autostart_enabled(),
            "lang": lang,
        },
    )
```

- [ ] **Step 4: Add i18n msgid 7건 to ko/en .po**

Edit `src/assetcache/web/locale/ko/LC_MESSAGES/messages.po` — 파일 끝에 추가:

```po
# M11+ — Backend 카드 가격·셋업 안내

#: src/assetcache/web/templates/settings.html
msgid "ⓘ Pricing & setup"
msgstr "ⓘ 가격 + 셋업 안내"

#: src/assetcache/web/templates/settings.html
msgid "Download Ollama →"
msgstr "Ollama 다운로드 →"

#: src/assetcache/web/templates/settings.html
msgid "Get key from Google AI Studio →"
msgstr "Google AI Studio 에서 발급 →"

#: src/assetcache/web/templates/settings.html
msgid "Get key from Anthropic Console →"
msgstr "Anthropic Console 에서 발급 →"

#: src/assetcache/web/templates/settings.html
msgid "Get key from OpenAI Platform →"
msgstr "OpenAI Platform 에서 발급 →"

#: src/assetcache/web/templates/settings.html
msgid "Get key from OpenRouter Settings →"
msgstr "OpenRouter Settings 에서 발급 →"

#: src/assetcache/web/templates/settings.html
msgid "Get token from HuggingFace →"
msgstr "HuggingFace 에서 토큰 발급 →"
```

Edit `src/assetcache/web/locale/en/LC_MESSAGES/messages.po` — 파일 끝에 추가:

```po
# M11+ — Backend cards pricing & setup help

#: src/assetcache/web/templates/settings.html
msgid "ⓘ Pricing & setup"
msgstr "ⓘ Pricing & setup"

#: src/assetcache/web/templates/settings.html
msgid "Download Ollama →"
msgstr "Download Ollama →"

#: src/assetcache/web/templates/settings.html
msgid "Get key from Google AI Studio →"
msgstr "Get key from Google AI Studio →"

#: src/assetcache/web/templates/settings.html
msgid "Get key from Anthropic Console →"
msgstr "Get key from Anthropic Console →"

#: src/assetcache/web/templates/settings.html
msgid "Get key from OpenAI Platform →"
msgstr "Get key from OpenAI Platform →"

#: src/assetcache/web/templates/settings.html
msgid "Get key from OpenRouter Settings →"
msgstr "Get key from OpenRouter Settings →"

#: src/assetcache/web/templates/settings.html
msgid "Get token from HuggingFace →"
msgstr "Get token from HuggingFace →"
```

- [ ] **Step 5: Compile .mo files**

```powershell
pybabel compile -d src/assetcache/web/locale
```

Expected: 두 줄 "compiling catalog ..." 출력.

- [ ] **Step 6: Update settings.html — add details/summary + setup link + Alpine data**

Edit `src/assetcache/web/templates/settings.html`:

a) backend 카드 fieldset 안의 legend 아래, API key label 위에 `<details>` block 추가:

```html
        <legend>
          <input type="checkbox" :id="`bk-${name}-enabled`"
                 x-model="backends[name].enabled">
          <label :for="`bk-${name}-enabled`" x-text="name"></label>
        </legend>

        {# M11+ — 가격 + 셋업 안내 (접힘 기본) #}
        <details class="backend-help">
          <summary>{{ _("ⓘ Pricing & setup") }}</summary>
          {% for bname in ["ollama", "gemini", "claude", "openai", "openrouter", "huggingface"] %}
            <template x-if="name === '{{ bname }}'">
              <div>
                {% include "settings/help_" + bname + "_" + lang + ".html" %}
              </div>
            </template>
          {% endfor %}
        </details>

        <label class="field" x-show="'api_key' in backends[name]">
```

(Alpine `x-if` 로 현재 backend name 에 매칭되는 partial 만 렌더 — Jinja 의 `{% for %}` 로 6 backend 별 template 미리 펼침)

b) API key input 아래 setup link `<small>` 추가:

```html
        <label class="field" x-show="'api_key' in backends[name]">
          <span>{{ _("API key") }}</span>
          <input type="password" autocomplete="off"
                 x-model="backends[name].api_key"
                 placeholder="—">
          {# M11+ — direct link to provider's API key page #}
          <small class="setup-link">
            <a :href="setupUrls[name]" target="_blank" rel="noopener noreferrer"
               x-text="setupLinkLabels[name]"></a>
          </small>
        </label>
```

c) Alpine `settingsForm()` 객체 안에 `setupUrls` 와 `setupLinkLabels` 추가 — 기존 `backends:` 다음 줄:

```javascript
        // M11 — backends
        backends: backendsInit,
        backendOrder: backendOrder,
        backendSaving: {},
        backendTesting: {},
        backendTestResult: {},

        // M11+ — backend 별 setup URL + 한 줄 label
        setupUrls: {
            ollama: "https://ollama.com/download",
            gemini: "https://aistudio.google.com/apikey",
            claude: "https://console.anthropic.com/settings/keys",
            openai: "https://platform.openai.com/api-keys",
            openrouter: "https://openrouter.ai/settings/keys",
            huggingface: "https://huggingface.co/settings/tokens",
        },
        setupLinkLabels: {
            ollama: "{{ _('Download Ollama →') }}",
            gemini: "{{ _('Get key from Google AI Studio →') }}",
            claude: "{{ _('Get key from Anthropic Console →') }}",
            openai: "{{ _('Get key from OpenAI Platform →') }}",
            openrouter: "{{ _('Get key from OpenRouter Settings →') }}",
            huggingface: "{{ _('Get token from HuggingFace →') }}",
        },
```

- [ ] **Step 7: Run test to verify it passes**

```powershell
pytest tests/test_settings_router_m11.py::test_settings_page_includes_ko_partial_for_gemini tests/test_settings_router_m11.py::test_settings_page_includes_en_partial_for_claude -v
```

Expected: 2 PASSED.

- [ ] **Step 8: Full regression**

```powershell
pytest -q
```

Expected: `1251 passed + 1 skipped + 53 deselected` (1249 + 2 신규).

- [ ] **Step 9: Commit**

```powershell
git add src/assetcache/web/routers/settings.py src/assetcache/web/templates/settings.html src/assetcache/web/locale/ko/LC_MESSAGES/messages.po src/assetcache/web/locale/ko/LC_MESSAGES/messages.mo src/assetcache/web/locale/en/LC_MESSAGES/messages.po src/assetcache/web/locale/en/LC_MESSAGES/messages.mo tests/test_settings_router_m11.py
git commit -m "feat(m11+): settings.html details/summary + setup link + i18n 7 msgid + 2 테스트"
```

---

## Task 4: 최종 회귀 + 수동 검증 안내

- [ ] **Step 1: 트레이 재시작 (사용자) — 변경된 settings.html 반영**

기존 background 트레이는 코드 reload 안 함. 검증 전 재시작:

```powershell
# 사용자가 트레이 아이콘 우클릭 → "종료" 또는 Claude 가 background process kill
# 그 후 새 트레이 시작:
python -m assetcache --tray
```

- [ ] **Step 2: 브라우저로 /settings 페이지 확인**

URL: `http://127.0.0.1:9874/settings`

각 backend 카드에서 확인:
- legend 아래 "ⓘ 가격 + 셋업 안내" 접힌 details summary 표시
- summary 클릭 시 ko/en partial 본문 펼쳐짐
- API key input 아래 "Google AI Studio 에서 발급 →" 같은 한 줄 link 표시
- link 클릭 시 새 탭으로 provider 페이지 이동

- [ ] **Step 3: 최종 회귀**

```powershell
pytest -q
```

Expected: `1251 passed + 1 skipped + 53 deselected`.

- [ ] **Step 4: 변경 요약 commit log 확인**

```powershell
git log --oneline 9a808e6..HEAD
```

Expected: 3 신규 commit (Task 1 + Task 2 + Task 3).

---

## Self-Review

### Spec coverage

| spec §  | 요구사항 | 해당 task |
|---|---|---|
| 4.1 | BackendInfo.setup_url 필드 + 6 backend 박기 | Task 1 |
| 4.2 | 12 partial 파일 (6 × ko/en) | Task 2 |
| 4.3 | settings.html details/summary + setup link + Alpine | Task 3 |
| 4.4 | i18n msgid 7건 + ko 번역 | Task 3 |
| 5 | 컴포넌트 의존도 | 전체 task 흐름이 정합 |
| 6 | 데이터 플로우 | Task 3 의 router → template → partial |
| 7 | 에러 처리 | router 의 `getattr(request.state, "lang", "en")` 폴백 |
| 8 | 테스트 전략 +4 케이스 (실제 +7 — backend 6 + partial 3 + 렌더링 2) | 충실 — 회귀 +12 |
| 9 | 알려진 한계 | spec 명시 — 코드 변경 없음 |
| 10 | 가격 데이터 | Task 2 의 partial 본문에 박힘 |
| 11 | 구현 순서 | Task 1→2→3→4 |

### Placeholder scan
- TBD/TODO: 없음
- "Add appropriate ...": 없음
- "Similar to Task N": 없음 — 모든 코드 명시
- 빈 step: 없음

### Type consistency
- `BackendInfo.setup_url: str | None = None` — Task 1/3 일관
- 12 partial 파일명 패턴 `help_<name>_<lang>.html` — Task 2/3 일관
- Alpine `setupUrls` / `setupLinkLabels` 키 6 backend — Task 3 settings.html 안에서 일관
- i18n msgid 정확히 7건 — Task 3 .po 와 settings.html 의 `_()` 호출 매칭

### 회귀 예상치

| Phase | 회귀 |
|---|---:|
| 시작 | 1239 |
| Task 1 commit 후 | 1246 (+7) |
| Task 2 commit 후 | 1249 (+3) |
| Task 3 commit 후 | 1251 (+2) |
| **합계** | **+12** |

(spec §8 예상치 +4 보다 +8 더 많음 — partial existence 검증 3건 + setup_url 매핑 6건 + rendering 2건 + spec §8 의 4를 다 충실히 + 추가 검증)

---

## Execution Handoff

플랜 작성 완료. `docs/superpowers/plans/2026-05-20-backend-help-cards.md` 저장.
