# M11 — Multi-backend LLM Architecture 구현 plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현재 Ollama 단일 backend → modality 별 backend chain + 외부 LLM 5종 추가 (Gemini · Claude · OpenAI · OpenRouter · HuggingFace) + 자동 fallback + /settings UI. 사용자에게 정확도/비용/오프라인 통제권 부여.

**Architecture:**
- `core/llm/` 패키지 신설 — `LLMBackend` Protocol + `BackendChain` (modality 별) + `BackendRegistry` (config 분기).
- 6 backend wrapper (각 `core/llm/backends/<name>.py`) — 외부 SDK (`google-genai`, `anthropic`, `openai`, `huggingface_hub`) thin wrap.
- 기존 `OllamaClient` 는 `OllamaBackend` 가 wrap (Phase 0 의 호출 패턴 보존이 회귀 1079 baseline 의 열쇠).
- modality: `chat_image` / `chat_audio` / `text_embed` 각각 독립 chain. Claude (audio 미지원) 같은 비대응 backend 는 자동 skip.
- transient (429/5xx/cold-start) → 다음 backend; hard (401/403) → chain 중단 + UI 배너.
- /settings 페이지에 backend 카드 + drag-drop chain 우선순위 + "테스트" 버튼.

**Tech Stack:** Python 3.12, httpx (기존), `google-genai>=0.1`, `anthropic>=0.40`, `openai>=1.50`, `huggingface_hub>=0.24`, FastAPI + HTMX + Alpine.js (/settings UI), `respx` (mock), `pytest-mock`.

**Spec:** [`docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md`](../specs/2026-05-20-m11-multi-backend-llm-design.md)

**Baseline:** 1079 passed + 1 skipped + 40 deselected (2026-05-20 검증). 목표 최종 ~1150 passed.

**Branch:** `feat/m11-multi-backend-llm` (메인 저장소 안에서 직접 checkout — CLAUDE.md §4.5 워크트리 금지). 모든 phase 작업이 누적 → 끝에 main PR.

**의존성:** 신규 런타임 4건 (`google-genai`, `anthropic`, `openai`, `huggingface_hub`). dev 신규 0건 (`respx` 이미 있음).

---

## File Structure

### 신규 (15)

```
src/assetcache/core/llm/__init__.py                       (Task 0.1)
src/assetcache/core/llm/base.py                            (Task 0.2)
src/assetcache/core/llm/chain.py                           (Task 0.3)
src/assetcache/core/llm/registry.py                        (Task 0.5)
src/assetcache/core/llm/backends/__init__.py               (Task 0.4)
src/assetcache/core/llm/backends/ollama.py                 (Task 0.4)
src/assetcache/core/llm/backends/gemini.py                 (Task 1.1)
src/assetcache/core/llm/backends/claude.py                 (Task 2.1)
src/assetcache/core/llm/backends/openai_backend.py         (Task 3.1)
src/assetcache/core/llm/backends/openrouter.py             (Task 4.1)
src/assetcache/core/llm/backends/huggingface.py            (Task 4.2)
src/assetcache/web/templates/settings/_backend_card.html   (Task 5.1)
src/assetcache/web/templates/settings/_chains_panel.html   (Task 5.2)
milestones/M11_verification.md                              (Task 7.5)
tests/test_*.py (10 신규 파일, Task 0.2~6.2 누적)
```

### 수정 (8 핵심 + ~3 부수)

```
src/assetcache/config.py — [backends.*] + [chains] 필드 + migration   (Task 0.5)
src/assetcache/app.py — BackendChain wiring                            (Task 0.6)
src/assetcache/core/analyzer/sprite.py — ollama → chain               (Task 0.7)
src/assetcache/core/analyzer/sound.py — ollama → chain                 (Task 0.7)
src/assetcache/core/analyzer/spritesheet.py — ollama → chain          (Task 0.7)
src/assetcache/core/embedding.py — _EmbedCapable → chain               (Task 0.7)
src/assetcache/core/store.py — backend_image/audio/embed 컬럼          (Task 6.1)
src/assetcache/web/routers/settings.py — backend 라우트 확장          (Task 5.3)
src/assetcache/mcp/models.py — find_asset 응답에 backend_used         (Task 6.2)
src/assetcache/mcp/tools.py — find_asset 결과 매핑                    (Task 6.2)
pyproject.toml — 4 신규 deps + llm_integration marker                  (Task 1.0 / 7.1)
src/assetcache/web/locale/{ko,en}/LC_MESSAGES/messages.po — msgid 추가 (Task 5.4)
```

### 책임 경계

- `core/llm/base.py` — Protocol + dataclass만. 의존성 없음. 순수 타입.
- `core/llm/chain.py` — fallback 로직 + modality 필터링. backend 구현 모름.
- `core/llm/registry.py` — config TOML 읽고 backend 인스턴스 생성. 분기 한곳.
- `core/llm/backends/*` — 각 외부 SDK wrapper. 다른 backend 모름, chain 모름.
- `core/analyzer/*.py` — `BackendChain` 만 의존. 어떤 backend 인지 모름.
- `web/routers/settings.py` — HTTP. backend 인스턴스 직접 다루지 않고 registry 통해 조작.

각 모듈 단일 책임. backend 추가 시 `backends/<name>.py` + `registry.py` 분기 1줄만 수정.

---

## Phase 0 — Framework + Ollama wrap (회귀 1079, ~2일)

목표: `core/llm/` 패키지 + LLMBackend Protocol + BackendChain + OllamaBackend wrap + analyzer 시그니처 마이그레이션. **회귀 1079 baseline 유지가 acceptance criteria.**

### Task 0.0: 브랜치 + spec 확인

**Files:**
- Verify: `git branch` shows main
- Create: `feat/m11-multi-backend-llm` branch

- [ ] **Step 1: spec 본문 확인**

```powershell
cat docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md | Select-Object -First 30
```

Expected: spec 첫 30줄 (한 줄 요약 + Context 시작) 출력. 없으면 spec 부터 생성.

- [ ] **Step 2: main 위에서 분기**

```powershell
git checkout main
git pull
git checkout -b feat/m11-multi-backend-llm
```

- [ ] **Step 3: 회귀 baseline 재확인**

```powershell
pytest -q
```

Expected: `1079 passed, 1 skipped, 40 deselected`. 다르면 멈춤 — baseline 어긋남 디버깅.

### Task 0.1: `core/llm/` 패키지 스켈레톤

**Files:**
- Create: `src/assetcache/core/llm/__init__.py`
- Create: `src/assetcache/core/llm/backends/__init__.py`

- [ ] **Step 1: `__init__.py` 2개 생성 (empty)**

```python
# src/assetcache/core/llm/__init__.py
"""Multi-backend LLM 추상화 (M11).

backend abstraction (Protocol + Chain + Registry) + 6 backend wrappers.
spec: docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md
"""
```

```python
# src/assetcache/core/llm/backends/__init__.py
"""각 외부 LLM SDK 의 thin wrapper. backend 추가 시 여기에 모듈 추가."""
```

- [ ] **Step 2: 회귀 1079 (import 추가 영향만 검증)**

```powershell
pytest -q
```

Expected: `1079 passed`. 새 모듈은 아직 import 되는 곳 없음.

- [ ] **Step 3: 커밋**

```powershell
git add src/assetcache/core/llm
git commit -m "feat(m11): core/llm 패키지 스켈레톤"
```

### Task 0.2: `LLMBackend` Protocol + 보조 타입

**Files:**
- Create: `src/assetcache/core/llm/base.py`
- Create: `tests/test_llm_base.py`

- [ ] **Step 1: failing 테스트**

```python
# tests/test_llm_base.py
"""LLMBackend Protocol 의 runtime_checkable 검증."""

from __future__ import annotations

from assetcache.core.llm.base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
    LLMBackend,
)


def test_backend_info_immutable():
    info = BackendInfo(
        name="x",
        display_name="X",
        homepage="https://example.com/",
        capabilities=BackendCapabilities(True, True, True, embed_dim=None),
    )
    # frozen dataclass — assignment raises
    try:
        info.name = "y"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("BackendInfo 는 frozen 이어야 한다")


def test_backend_error_classification():
    e = BackendError(backend="x", stage="chat", transient=True)
    assert e.transient is True
    assert e.backend == "x"
    assert e.stage == "chat"
    e2 = BackendError(backend="x", stage="chat", transient=False, cause=RuntimeError("fail"))
    assert e2.transient is False
    assert isinstance(e2.cause, RuntimeError)


def test_chat_message_dataclass_fields():
    m = ChatMessage(role="user", content="hi")
    assert m.images_b64 == []
    assert m.audio_b64 == []
    m2 = ChatMessage(role="user", content="x", images_b64=["abc"], audio_b64=[("d", "audio/wav")])
    assert m2.images_b64 == ["abc"]
    assert m2.audio_b64 == [("d", "audio/wav")]


def test_llm_backend_protocol_satisfied_by_stub():
    """runtime_checkable Protocol — duck-typed instance 가 isinstance() 통과."""

    class _Stub:
        info = BackendInfo(
            name="stub",
            display_name="Stub",
            homepage="",
            capabilities=BackendCapabilities(False, False, False, embed_dim=None),
        )

        def chat(self, messages, *, force_json=True, num_ctx=8000):
            return {}

        def embed(self, text, *, model=None):
            return [0.0]

        def test_connection(self):
            return True

    assert isinstance(_Stub(), LLMBackend)
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_llm_base.py -v
```

Expected: `ImportError: cannot import name 'BackendCapabilities' from 'assetcache.core.llm.base'`.

- [ ] **Step 3: `base.py` 구현**

```python
# src/assetcache/core/llm/base.py
"""LLMBackend Protocol + 보조 타입 (M11 §3).

ChatMessage 는 기존 ollama_client.ChatMessage 와 동일 구조 — Phase 0 에서
이쪽으로 canonical 이전. ollama_client.ChatMessage 는 별칭으로 유지.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ChatMessage:
    role: str                                              # 'system' | 'user'
    content: str
    images_b64: list[str] = field(default_factory=list)
    audio_b64: list[tuple[str, str]] = field(default_factory=list)  # (data, mime)


@dataclass(frozen=True)
class BackendCapabilities:
    supports_chat_image: bool
    supports_chat_audio: bool
    supports_text_embed: bool
    embed_dim: int | None                                  # None = first-use lock


@dataclass(frozen=True)
class BackendInfo:
    name: str                                              # slug
    display_name: str
    homepage: str
    capabilities: BackendCapabilities


class BackendError(RuntimeError):
    """모든 backend wrapper 가 던지는 통일 에러.

    transient=True → BackendChain 이 다음 backend 로 fallback.
    transient=False → chain 즉시 raise + UI 배너 (auth / quota / 모델 X).
    """

    def __init__(
        self,
        *,
        backend: str,
        stage: str,
        transient: bool,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(f"BackendError(backend={backend}, stage={stage}, transient={transient})")
        self.backend = backend
        self.stage = stage
        self.transient = transient
        self.cause = cause


@runtime_checkable
class LLMBackend(Protocol):
    info: BackendInfo

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        force_json: bool = True,
        num_ctx: int = 8000,
    ) -> dict: ...

    def embed(self, text: str, *, model: str | None = None) -> list[float]: ...

    def test_connection(self) -> bool: ...
```

- [ ] **Step 4: 테스트 통과 확인**

```powershell
pytest tests/test_llm_base.py -v
```

Expected: 4 passed.

- [ ] **Step 5: 회귀**

```powershell
pytest -q
```

Expected: `1083 passed` (1079 + 4 신규).

- [ ] **Step 6: 커밋**

```powershell
git add src/assetcache/core/llm/base.py tests/test_llm_base.py
git commit -m "feat(m11): LLMBackend Protocol + BackendInfo/Capabilities/Error"
```

### Task 0.3: `BackendChain` (fallback semantics)

**Files:**
- Create: `src/assetcache/core/llm/chain.py`
- Create: `tests/test_llm_chain.py`

- [ ] **Step 1: failing 테스트**

```python
# tests/test_llm_chain.py
"""BackendChain — modality skip + transient fallback + hard raise."""

from __future__ import annotations

import pytest

from assetcache.core.llm.base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
)
from assetcache.core.llm.chain import BackendChain


def _backend(name, *, img=True, aud=True, emb=True, chat_result=None,
             chat_error=None, embed_result=None, embed_error=None):
    class _Stub:
        info = BackendInfo(
            name=name,
            display_name=name,
            homepage="",
            capabilities=BackendCapabilities(img, aud, emb, embed_dim=None),
        )

        def chat(self, messages, **kw):
            if chat_error is not None:
                raise chat_error
            return chat_result if chat_result is not None else {"backend": name}

        def embed(self, text, *, model=None):
            if embed_error is not None:
                raise embed_error
            return embed_result if embed_result is not None else [1.0, 2.0]

        def test_connection(self):
            return True

    return _Stub()


def test_chain_chat_first_success():
    chain = BackendChain([_backend("a"), _backend("b")], modality="chat_image")
    result, used = chain.chat([ChatMessage("user", "hi")])
    assert used == "a"
    assert result == {"backend": "a"}


def test_chain_chat_transient_fallback():
    a_fail = _backend("a", chat_error=BackendError(backend="a", stage="chat", transient=True))
    b_ok = _backend("b")
    chain = BackendChain([a_fail, b_ok], modality="chat_image")
    result, used = chain.chat([ChatMessage("user", "hi")])
    assert used == "b"
    assert result == {"backend": "b"}


def test_chain_chat_hard_raises_immediately():
    a_hard = _backend("a", chat_error=BackendError(backend="a", stage="chat", transient=False))
    b_ok = _backend("b")
    chain = BackendChain([a_hard, b_ok], modality="chat_image")
    with pytest.raises(BackendError) as exc:
        chain.chat([ChatMessage("user", "hi")])
    assert exc.value.backend == "a"
    assert exc.value.transient is False


def test_chain_modality_skip_audio_unsupported():
    a_no_audio = _backend("a", aud=False)
    b_ok = _backend("b")
    chain = BackendChain([a_no_audio, b_ok], modality="chat_audio")
    result, used = chain.chat([ChatMessage("user", "hi")])
    assert used == "b"


def test_chain_all_fail_raises_chain_error():
    a = _backend("a", chat_error=BackendError(backend="a", stage="chat", transient=True))
    b = _backend("b", chat_error=BackendError(backend="b", stage="chat", transient=True))
    chain = BackendChain([a, b], modality="chat_image")
    with pytest.raises(BackendError) as exc:
        chain.chat([ChatMessage("user", "hi")])
    assert exc.value.backend == "<chain>"


def test_chain_embed_no_fallback():
    """embedding chain 은 1순위만 사용 — dim 일관성 보장."""
    a_fail = _backend("a", embed_error=BackendError(backend="a", stage="embed", transient=True))
    b_ok = _backend("b", embed_result=[3.0])
    chain = BackendChain([a_fail, b_ok], modality="text_embed")
    with pytest.raises(BackendError):
        chain.embed("x")


def test_chain_empty_raises():
    chain = BackendChain([], modality="chat_image")
    with pytest.raises(BackendError):
        chain.chat([ChatMessage("user", "hi")])
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_llm_chain.py -v
```

Expected: ImportError for `BackendChain`.

- [ ] **Step 3: `chain.py` 구현**

```python
# src/assetcache/core/llm/chain.py
"""BackendChain — modality 별 fallback 로직.

semantics:
- 1순위 success → 1순위 반환 + name.
- 1순위 transient 에러 → 다음 backend.
- 1순위 hard 에러 → 즉시 raise (다음 backend 시도 안 함).
- modality 비대응 backend (Claude on audio) → 자동 skip.
- text_embed modality 는 fallback 안 함 (dim 일관성).
- 모두 실패 / 빈 chain → BackendError(backend="<chain>").
"""

from __future__ import annotations

import logging
from typing import Literal

from .base import BackendError, ChatMessage, LLMBackend

log = logging.getLogger(__name__)

Modality = Literal["chat_image", "chat_audio", "text_embed"]


class BackendChain:
    def __init__(self, backends: list[LLMBackend], *, modality: Modality) -> None:
        self.backends = list(backends)
        self.modality = modality

    def _eligible(self) -> list[LLMBackend]:
        """capabilities 가 modality 를 지원하는 backend 만."""
        result = []
        for b in self.backends:
            cap = b.info.capabilities
            if self.modality == "chat_image" and cap.supports_chat_image:
                result.append(b)
            elif self.modality == "chat_audio" and cap.supports_chat_audio:
                result.append(b)
            elif self.modality == "text_embed" and cap.supports_text_embed:
                result.append(b)
        return result

    def chat(self, messages: list[ChatMessage], *, force_json: bool = True,
             num_ctx: int = 8000) -> tuple[dict, str]:
        """Return ``(response_dict, backend_name_used)``."""
        eligible = self._eligible()
        if not eligible:
            raise BackendError(backend="<chain>", stage=self.modality, transient=False)
        for backend in eligible:
            try:
                response = backend.chat(messages, force_json=force_json, num_ctx=num_ctx)
                return response, backend.info.name
            except BackendError as e:
                if not e.transient:
                    raise
                log.info("backend %s transient fail (%s); trying next", backend.info.name, e.stage)
                continue
        raise BackendError(backend="<chain>", stage=self.modality, transient=False)

    def embed(self, text: str, *, model: str | None = None) -> tuple[list[float], str]:
        """text_embed chain — fallback 안 함, 1순위만 사용."""
        if self.modality != "text_embed":
            raise BackendError(backend="<chain>", stage="embed", transient=False,
                               cause=ValueError(f"embed() called on {self.modality} chain"))
        eligible = self._eligible()
        if not eligible:
            raise BackendError(backend="<chain>", stage="embed", transient=False)
        primary = eligible[0]
        return primary.embed(text, model=model), primary.info.name
```

- [ ] **Step 4: 테스트 통과**

```powershell
pytest tests/test_llm_chain.py -v
```

Expected: 7 passed.

- [ ] **Step 5: 회귀**

```powershell
pytest -q
```

Expected: `1090 passed` (1083 + 7).

- [ ] **Step 6: 커밋**

```powershell
git add src/assetcache/core/llm/chain.py tests/test_llm_chain.py
git commit -m "feat(m11): BackendChain — fallback semantics + modality skip"
```

### Task 0.4: `OllamaBackend` wrapper

**Files:**
- Create: `src/assetcache/core/llm/backends/ollama.py`
- Create: `tests/test_llm_backend_ollama.py`

- [ ] **Step 1: failing 테스트**

```python
# tests/test_llm_backend_ollama.py
"""OllamaBackend — 기존 OllamaClient 의 wrapping. 호출 위임 검증."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from assetcache.core.llm.backends.ollama import OllamaBackend
from assetcache.core.llm.base import BackendError, ChatMessage, LLMBackend
from assetcache.core.ollama_client import OllamaError


def _client():
    c = MagicMock()
    c.base_url = "http://127.0.0.1:11434"
    return c


def test_ollama_backend_is_protocol():
    b = OllamaBackend(client=_client())
    assert isinstance(b, LLMBackend)


def test_ollama_backend_info_capabilities():
    b = OllamaBackend(client=_client())
    assert b.info.name == "ollama"
    cap = b.info.capabilities
    assert cap.supports_chat_image
    assert cap.supports_chat_audio
    assert cap.supports_text_embed


def test_ollama_backend_chat_delegates():
    c = _client()
    c.chat.return_value = {"ok": True}
    b = OllamaBackend(client=c)
    out = b.chat([ChatMessage("user", "hi")], force_json=True, num_ctx=8000)
    assert out == {"ok": True}
    c.chat.assert_called_once()


def test_ollama_backend_chat_wraps_ollama_error_as_transient():
    c = _client()
    c.chat.side_effect = OllamaError(stage="chat", path="native")
    b = OllamaBackend(client=c)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.backend == "ollama"
    assert exc.value.transient is True  # cold-start exhausted → transient


def test_ollama_backend_embed_delegates():
    c = _client()
    c.embed.return_value = [0.1, 0.2]
    b = OllamaBackend(client=c)
    assert b.embed("text") == [0.1, 0.2]
```

- [ ] **Step 2: 실패 확인 → 구현**

```powershell
pytest tests/test_llm_backend_ollama.py -v
```

Expected: ImportError.

```python
# src/assetcache/core/llm/backends/ollama.py
"""OllamaBackend — 기존 OllamaClient wrap.

행동 보존: chat/embed 시그니처 + 에러 분류만 BackendError 로 통일. cold-start
retry / OpenAI↔native fallback 은 OllamaClient 내부에서 그대로.
"""

from __future__ import annotations

import httpx

from ...ollama_client import OllamaClient, OllamaError
from ..base import BackendCapabilities, BackendError, BackendInfo, ChatMessage, LLMBackend


class OllamaBackend:
    info = BackendInfo(
        name="ollama",
        display_name="Ollama (local)",
        homepage="https://ollama.com/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=True,
            supports_text_embed=True,
            embed_dim=None,                # nomic-embed-text 는 768; first-use lock
        ),
    )

    def __init__(self, client: OllamaClient) -> None:
        self._client = client

    def chat(self, messages: list[ChatMessage], *, force_json: bool = True,
             num_ctx: int = 8000) -> dict:
        try:
            return self._client.chat(messages, force_json=force_json, num_ctx=num_ctx)
        except OllamaError as e:
            # cold-start retry 가 OllamaClient 내부에서 소진된 후라면 transient → 다음 backend
            raise BackendError(backend="ollama", stage="chat", transient=True, cause=e) from e

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        try:
            return self._client.embed(text, model=model)
        except OllamaError as e:
            raise BackendError(backend="ollama", stage="embed", transient=True, cause=e) from e

    def test_connection(self) -> bool:
        try:
            r = httpx.get(f"{self._client.base_url}/api/tags", timeout=2.0)
            r.raise_for_status()
            return True
        except Exception:
            return False


# Protocol 만족 sanity check
_: LLMBackend = OllamaBackend.__new__(OllamaBackend)  # type: ignore[arg-type]
```

- [ ] **Step 3: 통과 + 회귀**

```powershell
pytest tests/test_llm_backend_ollama.py -v
pytest -q
```

Expected: 5 passed → 회귀 `1095 passed`.

- [ ] **Step 4: 커밋**

```powershell
git add src/assetcache/core/llm/backends/ollama.py tests/test_llm_backend_ollama.py
git commit -m "feat(m11): OllamaBackend wrapper — OllamaClient를 LLMBackend로"
```

### Task 0.5: Config `[backends.ollama]` + `[chains]` + migration

**Files:**
- Modify: `src/assetcache/config.py`
- Create: `src/assetcache/core/llm/registry.py`
- Create: `tests/test_config_m11_migration.py`
- Create: `tests/test_llm_registry.py`

- [ ] **Step 1: config migration 테스트**

```python
# tests/test_config_m11_migration.py
"""Config — [backends.*] / [chains] migration (M11 §6.2)."""

from __future__ import annotations

import textwrap

import pytest

from assetcache.config import Config, load_config, save_config


def test_legacy_only_config_migrates_to_backends_ollama(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        ollama_url = "http://1.2.3.4:11434"
        model_image = "gemma4:e4b"
        model_audio = "gemma4:e4b"
        model_embed = "nomic-embed-text"
    """))
    cfg = load_config(p)
    assert cfg.backends["ollama"]["enabled"] is True
    assert cfg.backends["ollama"]["base_url"] == "http://1.2.3.4:11434"
    assert cfg.backends["ollama"]["model_image"] == "gemma4:e4b"
    assert cfg.chains["chat_image"] == ["ollama"]
    assert cfg.chains["chat_audio"] == ["ollama"]
    assert cfg.chains["text_embed"] == ["ollama"]


def test_new_keys_only_preserved(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        [backends.ollama]
        enabled = true
        base_url = "http://5.6.7.8:11434"
        model_image = "gemma3:7b"

        [backends.gemini]
        enabled = true
        api_key = "AIzaSecret"
        model_image = "gemini-2.5-flash"

        [chains]
        chat_image = ["gemini", "ollama"]
        chat_audio = ["ollama"]
        text_embed = ["ollama"]
    """))
    cfg = load_config(p)
    assert cfg.backends["ollama"]["base_url"] == "http://5.6.7.8:11434"
    assert cfg.backends["gemini"]["api_key"] == "AIzaSecret"
    assert cfg.chains["chat_image"] == ["gemini", "ollama"]


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "config.toml"
    cfg = Config()
    save_config(cfg, p)
    cfg2 = load_config(p)
    assert cfg2.backends["ollama"]["enabled"] is True
    assert "gemini" in cfg2.backends
    assert "claude" in cfg2.backends
    assert "openai" in cfg2.backends
    assert "openrouter" in cfg2.backends
    assert "huggingface" in cfg2.backends


def test_unknown_chain_modality_falls_back_to_default(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        [chains]
        bogus_modality = ["x"]
    """))
    cfg = load_config(p)
    # chains 의 알려진 키 3개만 적용; bogus 무시
    assert "bogus_modality" not in cfg.chains
    assert cfg.chains["chat_image"] == ["ollama"]
```

- [ ] **Step 2: `config.py` 의 `Config` 에 `backends`/`chains` 필드 + migration 추가**

기존 `Config` 의 `model_image / model_audio / model_embed / ollama_url / ollama_parallel` 는 유지 (하위 호환). 새 필드 추가:

```python
# src/assetcache/config.py 의 Config dataclass 에 추가
    # M11 fields — backends 사전 + chains
    backends: dict[str, dict[str, Any]] = field(default_factory=lambda: _default_backends())
    chains: dict[str, list[str]] = field(default_factory=lambda: _default_chains())
```

`_default_backends()` 와 `_default_chains()` 헬퍼는 같은 파일 module-level:

```python
def _default_backends() -> dict[str, dict[str, Any]]:
    return {
        "ollama": {
            "enabled": True,
            "base_url": "http://127.0.0.1:11434",
            "model_image": "gemma4:e4b",
            "model_audio": "gemma4:e4b",
            "model_embed": "nomic-embed-text",
        },
        "gemini": {
            "enabled": False,
            "api_key": "",
            "model_image": "gemini-2.5-flash",
            "model_audio": "gemini-2.5-flash",
            "model_embed": "gemini-embedding-001",
        },
        "claude": {
            "enabled": False,
            "api_key": "",
            "model_image": "claude-haiku-4-5-20251001",
        },
        "openai": {
            "enabled": False,
            "api_key": "",
            "model_image": "gpt-5.4-mini",
            "model_audio": "gpt-4o-audio-preview",
            "model_embed": "text-embedding-3-small",
        },
        "openrouter": {
            "enabled": False,
            "api_key": "",
            "model_image": "google/gemma-4-27b-it:free",
        },
        "huggingface": {
            "enabled": False,
            "api_key": "",
            "model_image": "Qwen/Qwen2.5-VL-72B-Instruct",
            "model_audio": "",
            "model_embed": "",
        },
    }


def _default_chains() -> dict[str, list[str]]:
    return {
        "chat_image": ["ollama"],
        "chat_audio": ["ollama"],
        "text_embed": ["ollama"],
    }


_VALID_CHAIN_MODALITIES = {"chat_image", "chat_audio", "text_embed"}
```

`Config.from_mapping` 에 migration 로직 추가:

```python
    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Config":
        # ... 기존 로직 ...
        # M11: backends/chains migration
        backends = _default_backends()
        for name, override in (data.get("backends") or {}).items():
            if name not in backends:
                continue  # 알려진 backend 만
            backends[name].update(override)
        # legacy 키 → backends.ollama 로 백필 (data 에 새 키 없는 경우)
        if "backends" not in data:
            if "ollama_url" in data:
                backends["ollama"]["base_url"] = data["ollama_url"]
            for legacy_key in ("model_image", "model_audio", "model_embed"):
                if legacy_key in data:
                    backends["ollama"][legacy_key] = data[legacy_key]
        filtered["backends"] = backends

        chains = _default_chains()
        for modality, order in (data.get("chains") or {}).items():
            if modality in _VALID_CHAIN_MODALITIES and isinstance(order, list):
                chains[modality] = [str(x) for x in order]
        filtered["chains"] = chains

        return cls(**filtered)
```

- [ ] **Step 3: 통과 + 회귀**

```powershell
pytest tests/test_config_m11_migration.py -v
pytest -q
```

Expected: 4 passed → 회귀 `1099 passed` (기존 1095 + 4).

- [ ] **Step 4: registry 테스트**

```python
# tests/test_llm_registry.py
"""BackendRegistry — config 의 [backends.*] + [chains] → BackendChain 구성."""

from __future__ import annotations

from assetcache.config import Config
from assetcache.core.llm.registry import BackendRegistry


def test_registry_builds_ollama_default():
    cfg = Config()
    reg = BackendRegistry.from_config(cfg, ollama_client_factory=lambda **_: None)
    # 모든 chain 이 ollama 하나만
    assert reg.get_chain("chat_image").backends[0].info.name == "ollama"
    assert reg.get_chain("chat_audio").backends[0].info.name == "ollama"
    assert reg.get_chain("text_embed").backends[0].info.name == "ollama"


def test_registry_skips_disabled_backend():
    cfg = Config()
    cfg.backends["ollama"]["enabled"] = False
    cfg.backends["gemini"]["enabled"] = True
    cfg.backends["gemini"]["api_key"] = "AIzaTest"
    cfg.chains["chat_image"] = ["ollama", "gemini"]
    reg = BackendRegistry.from_config(cfg, ollama_client_factory=lambda **_: None,
                                       gemini_factory=lambda **_: _FakeGemini())
    names = [b.info.name for b in reg.get_chain("chat_image").backends]
    assert "ollama" not in names
    assert "gemini" in names


class _FakeGemini:
    from assetcache.core.llm.base import BackendInfo, BackendCapabilities
    info = BackendInfo("gemini", "Google Gemini", "https://ai.google.dev/",
                       BackendCapabilities(True, True, True, embed_dim=768))

    def chat(self, *a, **kw): return {}
    def embed(self, *a, **kw): return [0.0]
    def test_connection(self): return True
```

- [ ] **Step 5: `registry.py` 구현**

```python
# src/assetcache/core/llm/registry.py
"""config → BackendChain 의 변환 한곳.

Phase 0: ollama 만 인식. Phase 1~4 에서 각 backend factory 추가.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Literal

from ...config import Config
from ..ollama_client import OllamaClient
from .base import LLMBackend
from .chain import BackendChain
from .backends.ollama import OllamaBackend

log = logging.getLogger(__name__)

Modality = Literal["chat_image", "chat_audio", "text_embed"]


def _make_ollama(*, base_url: str, model_image: str, model_audio: str, model_embed: str,
                 timeout: float, parallel: int, max_retries: int) -> LLMBackend:
    client = OllamaClient(base_url=base_url, model=model_image,
                          timeout_seconds=timeout, max_retries=max_retries,
                          parallel=parallel)
    return OllamaBackend(client=client)


class BackendRegistry:
    def __init__(self, instances: dict[str, LLMBackend], chains: dict[Modality, BackendChain]) -> None:
        self._instances = instances
        self._chains = chains

    def get_chain(self, modality: Modality) -> BackendChain:
        return self._chains[modality]

    def get_backend(self, name: str) -> LLMBackend | None:
        return self._instances.get(name)

    @classmethod
    def from_config(
        cls,
        cfg: Config,
        *,
        ollama_client_factory: Callable[..., Any] | None = None,
        # Phase 1~4 에서 추가:
        gemini_factory: Callable[..., LLMBackend] | None = None,
        claude_factory: Callable[..., LLMBackend] | None = None,
        openai_factory: Callable[..., LLMBackend] | None = None,
        openrouter_factory: Callable[..., LLMBackend] | None = None,
        huggingface_factory: Callable[..., LLMBackend] | None = None,
    ) -> "BackendRegistry":
        instances: dict[str, LLMBackend] = {}
        for name, settings in cfg.backends.items():
            if not settings.get("enabled"):
                continue
            try:
                if name == "ollama":
                    instances[name] = _make_ollama(
                        base_url=settings["base_url"],
                        model_image=settings["model_image"],
                        model_audio=settings["model_audio"],
                        model_embed=settings["model_embed"],
                        timeout=cfg.analysis_timeout_seconds,
                        parallel=cfg.ollama_parallel,
                        max_retries=cfg.analysis_max_retries,
                    )
                elif name == "gemini" and gemini_factory is not None:
                    instances[name] = gemini_factory(settings=settings, cfg=cfg)
                elif name == "claude" and claude_factory is not None:
                    instances[name] = claude_factory(settings=settings, cfg=cfg)
                elif name == "openai" and openai_factory is not None:
                    instances[name] = openai_factory(settings=settings, cfg=cfg)
                elif name == "openrouter" and openrouter_factory is not None:
                    instances[name] = openrouter_factory(settings=settings, cfg=cfg)
                elif name == "huggingface" and huggingface_factory is not None:
                    instances[name] = huggingface_factory(settings=settings, cfg=cfg)
                # 모르는 backend 는 skip + warn
            except Exception as e:
                log.warning("backend %s instantiation failed: %s", name, e)

        chains: dict[Modality, BackendChain] = {}
        for modality, order in cfg.chains.items():
            ordered_backends = [instances[n] for n in order if n in instances]
            chains[modality] = BackendChain(ordered_backends, modality=modality)  # type: ignore[arg-type]
        return cls(instances, chains)
```

- [ ] **Step 6: registry 테스트 통과 + 회귀**

```powershell
pytest tests/test_llm_registry.py -v
pytest -q
```

Expected: 2 passed → 회귀 `1101 passed` (1099 + 2).

- [ ] **Step 7: 커밋**

```powershell
git add src/assetcache/config.py src/assetcache/core/llm/registry.py tests/test_config_m11_migration.py tests/test_llm_registry.py
git commit -m "feat(m11): Config [backends.*]/[chains] + BackendRegistry"
```

### Task 0.6: `app.py` wiring — BackendChain 주입

**Files:**
- Modify: `src/assetcache/app.py`

- [ ] **Step 1: 현재 wiring 확인**

```powershell
grep -n "OllamaClient\|EmbeddingEncoder" src/assetcache/app.py
```

Expected: `OllamaClient(...)` 생성 + `EmbeddingEncoder(client=ollama_client)` 호출 위치 식별.

- [ ] **Step 2: `app.py` 의 LLM 부트 부분을 `BackendRegistry.from_config(cfg)` 호출로 교체**

기존 `OllamaClient(...)` 직접 생성을 제거하고, `BackendRegistry` 가 만든 chain 을 analyzer/embedder 에 전달. 호출 패턴 유지 (Task 0.7 에서 analyzer 시그니처 변경 후 양쪽 변경 commit).

이 task 는 Task 0.7 와 한 커밋으로 묶음 — analyzer 시그니처가 BackendChain 받도록 변경됐을 때 app.py 의 호출도 같이 바꿔야 회귀 안 깨짐.

### Task 0.7: analyzer + embedder 시그니처 마이그레이션

**Files:**
- Modify: `src/assetcache/core/analyzer/sprite.py`
- Modify: `src/assetcache/core/analyzer/sound.py`
- Modify: `src/assetcache/core/analyzer/spritesheet.py`
- Modify: `src/assetcache/core/embedding.py`
- Modify: `src/assetcache/app.py` (Task 0.6 의 두번째 단계)

- [ ] **Step 1: analyzer 들의 ollama 호출 위치 식별**

```powershell
grep -n "self.ollama.chat\|self.ollama.embed" src/assetcache/core/analyzer
```

Expected: sprite.py / sound.py / spritesheet.py 각각 chat 호출.

- [ ] **Step 2: SpriteAnalyzer 시그니처 변경**

```python
# src/assetcache/core/analyzer/sprite.py 의 __init__
class SpriteAnalyzer:
    def __init__(
        self,
        *,
        chain_image: "BackendChain",   # 변경: ollama: OllamaClient → chain_image
        clip: "ClipLabeler | None",
        embedder: "EmbeddingEncoder",
        registry: "LabelRegistry",
        max_long_edge: int = 768,
    ) -> None:
        self.chain_image = chain_image
        # ...
```

`_call_gemma_with_validation` 같은 내부 메서드에서 `self.ollama.chat(messages, ...)` → `self.chain_image.chat(messages, ...)[0]`. `chat` 이 `(dict, name)` 튜플 반환하므로 `[0]` 으로 dict 만 사용 (backend name 은 Phase 6 에서 활용).

- [ ] **Step 3: SoundAnalyzer 시그니처 변경**

```python
# src/assetcache/core/analyzer/sound.py
class SoundAnalyzer:
    def __init__(
        self,
        *,
        chain_audio: "BackendChain",      # 변경
        chain_image: "BackendChain",      # 추가 — mel-spectrogram fallback 용
        embedder: "EmbeddingEncoder",
        # ...
    ) -> None:
        self.chain_audio = chain_audio
        self.chain_image = chain_image
        # ...
```

audio 첫 시도 → `self.chain_audio.chat(...)`, fallback (mel-spectrogram PNG) → `self.chain_image.chat(...)`.

- [ ] **Step 4: SpritesheetAnalyzer 시그니처 변경**

`SpriteAnalyzer` 와 동일 패턴 — `chain_image` 받음.

- [ ] **Step 5: `EmbeddingEncoder` 시그니처 변경**

```python
# src/assetcache/core/embedding.py
class EmbeddingEncoder:
    def __init__(self, chain_embed: "BackendChain", *, model: str = "nomic-embed-text") -> None:
        self.chain_embed = chain_embed
        # ...

    def encode_text(self, text: str) -> tuple[bytes, int]:
        vec, _ = self.chain_embed.embed(text, model=self.model)
        # ... 나머지 동일
```

기존 `_EmbedCapable` Protocol 은 제거 (BackendChain 이 대신).

- [ ] **Step 6: `app.py` 의 wiring 갱신**

```python
# src/assetcache/app.py 의 boot 함수 LLM 부분
from .core.llm.registry import BackendRegistry

# ... config 로드 후 ...
registry = BackendRegistry.from_config(cfg)

sprite_analyzer = SpriteAnalyzer(
    chain_image=registry.get_chain("chat_image"),
    clip=clip_labeler,
    embedder=EmbeddingEncoder(registry.get_chain("text_embed")),
    registry=label_registry,
)
sound_analyzer = SoundAnalyzer(
    chain_audio=registry.get_chain("chat_audio"),
    chain_image=registry.get_chain("chat_image"),
    embedder=EmbeddingEncoder(registry.get_chain("text_embed")),
    # ...
)
# 등
```

- [ ] **Step 7: 기존 analyzer 테스트 fixture 갱신**

```powershell
grep -rn "OllamaClient(" tests/
```

각 fixture 에서 `OllamaClient(...)` 직접 생성 → `BackendChain([OllamaBackend(OllamaClient(...))], modality="chat_image")` 같은 패턴으로 교체. 또는 fake `BackendChain` 만들기 (chat → 고정 dict 반환).

Helper fixture 작성 권장 (`tests/conftest.py` 에):

```python
@pytest.fixture
def fake_chain_image():
    from assetcache.core.llm.chain import BackendChain
    from tests._fakes import fake_backend
    return BackendChain([fake_backend("test", chat_result={...})], modality="chat_image")
```

- [ ] **Step 8: 통과 + 회귀 (이것이 Phase 0 의 critical 검증)**

```powershell
pytest -q
```

Expected: `1101 passed + 1 skipped` (기존 1079 + 신규 22). 실패하면 fixture/시그니처 정합성 디버깅 — Phase 0 의 회귀 보장이 acceptance.

- [ ] **Step 9: 커밋**

```powershell
git add -A
git commit -m "feat(m11): analyzer/embedder 시그니처 → BackendChain 주입 (회귀 1079→1101)"
```

### Task 0.8: Phase 0 wrap-up

- [ ] **Step 1: `git log feat/m11-multi-backend-llm --oneline` 5개 commit 확인**

Expected: Task 0.1~0.7 의 5개 commit (0.6+0.7 가 한 commit).

- [ ] **Step 2: spec 의 §11 Phase 0 acceptance 체크**

✅ `core/llm/` 패키지 + base/chain/registry/backends/ollama 구성 완료
✅ Config `[backends.*]` + `[chains]` migration 동작
✅ analyzer 3종 + embedder BackendChain 주입
✅ 회귀 1079 → 1101 (+22 신규 테스트)
✅ pytest 시그니처: `pytest -q` 결과 `1101 passed`

- [ ] **Step 3: 회귀 최종 재실행**

```powershell
pytest -q
```

Expected: `1101 passed, 1 skipped, 40 deselected`.

---

## Phase 1 — Gemini backend (~1.5일, +8 테스트)

목표: `google-genai` SDK 통합 + image/audio/embed 3 modality 지원 + chain 의 1순위로 등록 시 동작.

### Task 1.0: 의존성 + marker 추가

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: `dependencies` 에 추가**

```toml
dependencies = [
  # ... 기존 ...
  "google-genai>=0.1",
]
```

- [ ] **Step 2: `[tool.pytest.ini_options]` 에 `llm_integration` marker + deselect 추가**

```toml
addopts = "-ra -m 'not clip_integration and not mcp_integration and not e2e and not llm_integration'"
markers = [
  # ... 기존 ...
  "llm_integration: 실 LLM API key 필요 (Gemini/Claude/OpenAI/OpenRouter/HF). 기본 deselected — `pytest -m llm_integration` 옵트인.",
]
```

- [ ] **Step 3: install + 회귀**

```powershell
pip install -e .
pytest -q
```

Expected: `1101 passed` (의존성만 추가, 호출 없음). 실패 시 google-genai 의 추가 의존이 충돌하는지 디버깅.

- [ ] **Step 4: 커밋**

```powershell
git add pyproject.toml
git commit -m "build(m11): google-genai>=0.1 의존성 + llm_integration marker"
```

### Task 1.1: `GeminiBackend`

**Files:**
- Create: `src/assetcache/core/llm/backends/gemini.py`
- Create: `tests/test_llm_backend_gemini.py`

- [ ] **Step 1: failing 테스트 (mock)**

```python
# tests/test_llm_backend_gemini.py
"""GeminiBackend — google-genai SDK mock 기반."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from assetcache.core.llm.backends.gemini import GeminiBackend
from assetcache.core.llm.base import BackendError, ChatMessage


def test_gemini_capabilities():
    b = GeminiBackend.__new__(GeminiBackend)  # __init__ 없이 info 만 검사
    assert GeminiBackend.info.capabilities.supports_chat_image
    assert GeminiBackend.info.capabilities.supports_chat_audio
    assert GeminiBackend.info.capabilities.supports_text_embed


def test_gemini_chat_text_only(monkeypatch):
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"category": "sprite"}'
    fake_client.models.generate_content.return_value = fake_response

    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    b = GeminiBackend(api_key="x", model_image="m-i", model_audio="m-a",
                      model_embed="m-e", timeout=60.0)
    out = b.chat([ChatMessage("user", "hi")])
    assert out == {"category": "sprite"}


def test_gemini_chat_with_image(monkeypatch):
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"category": "icon"}'
    fake_client.models.generate_content.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    b = GeminiBackend(api_key="x", model_image="m-i", model_audio="m-a",
                      model_embed="m-e", timeout=60.0)
    out = b.chat([ChatMessage("user", "describe", images_b64=["aW1n"])])
    assert out == {"category": "icon"}
    # contents 에 image part 가 포함됐는지 검증
    call = fake_client.models.generate_content.call_args
    contents = call.kwargs.get("contents") or call.args[1]  # SDK shape 에 맞춰
    # part 중 inline_data 타입이 하나 있어야 함 (image)
    # ... (SDK 의 정확한 shape 에 맞춰 단언) ...


def test_gemini_auth_error_is_hard(monkeypatch):
    fake_client = MagicMock()
    # SDK 별 AuthenticationError 또는 PermissionDenied → hard 분류
    class _PermDenied(Exception): ...
    fake_client.models.generate_content.side_effect = _PermDenied("401")
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini._HARD_EXCEPTIONS",
        (_PermDenied,),
    )
    b = GeminiBackend(api_key="x", model_image="m-i", model_audio="m-a",
                      model_embed="m-e", timeout=60.0)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is False


def test_gemini_rate_limit_is_transient(monkeypatch):
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = Exception("429 Too Many Requests")
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    b = GeminiBackend(api_key="x", model_image="m-i", model_audio="m-a",
                      model_embed="m-e", timeout=60.0)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True
```

- [ ] **Step 2: `gemini.py` 구현**

```python
# src/assetcache/core/llm/backends/gemini.py
"""GeminiBackend — google-genai SDK wrap.

modality:
- chat_image: gemini-2.5-flash 등 multimodal — image+text contents
- chat_audio: 동일 모델 — Part.from_bytes(audio_b64, mime)
- text_embed: gemini-embedding-001 → embed_content
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from google import genai
from google.genai import types as genai_types

from ..base import BackendCapabilities, BackendError, BackendInfo, ChatMessage, LLMBackend

log = logging.getLogger(__name__)


# hard / transient 분류 — SDK 의 구체 예외 타입을 채울 것. 잠정값:
_HARD_EXCEPTIONS: tuple[type[Exception], ...] = ()  # 추후 AuthenticationError 등 추가


def _classify(e: Exception) -> bool:
    """True → transient."""
    if isinstance(e, _HARD_EXCEPTIONS):
        return False
    msg = str(e).lower()
    if "401" in msg or "403" in msg or "permission" in msg or "api key" in msg:
        return False
    return True


class GeminiBackend:
    info = BackendInfo(
        name="gemini",
        display_name="Google Gemini",
        homepage="https://ai.google.dev/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=True,
            supports_text_embed=True,
            embed_dim=768,                 # gemini-embedding-001 default
        ),
    )

    def __init__(
        self,
        *,
        api_key: str,
        model_image: str,
        model_audio: str,
        model_embed: str,
        timeout: float,
    ) -> None:
        if not api_key:
            raise BackendError(backend="gemini", stage="init", transient=False,
                                cause=ValueError("api_key empty"))
        self._client = genai.Client(api_key=api_key)
        self.model_image = model_image
        self.model_audio = model_audio
        self.model_embed = model_embed
        self.timeout = timeout

    def _select_model(self, messages: list[ChatMessage]) -> str:
        has_audio = any(m.audio_b64 for m in messages)
        return self.model_audio if has_audio else self.model_image

    def _to_contents(self, messages: list[ChatMessage]) -> list[Any]:
        parts: list[Any] = []
        for m in messages:
            parts.append(m.content)
            for b64 in m.images_b64:
                parts.append(genai_types.Part.from_bytes(
                    data=base64.b64decode(b64), mime_type="image/png",
                ))
            for data, mime in m.audio_b64:
                parts.append(genai_types.Part.from_bytes(
                    data=base64.b64decode(data), mime_type=mime,
                ))
        return parts

    def chat(self, messages: list[ChatMessage], *, force_json: bool = True,
             num_ctx: int = 8000) -> dict:
        contents = self._to_contents(messages)
        cfg = genai_types.GenerateContentConfig(
            response_mime_type="application/json" if force_json else None,
        )
        try:
            r = self._client.models.generate_content(
                model=self._select_model(messages),
                contents=contents,
                config=cfg,
            )
        except Exception as e:
            transient = _classify(e)
            raise BackendError(backend="gemini", stage="chat",
                                transient=transient, cause=e) from e
        text = getattr(r, "text", "") or ""
        try:
            return json.loads(text) if force_json else {"text": text}
        except (json.JSONDecodeError, ValueError):
            raise BackendError(backend="gemini", stage="chat", transient=True,
                                cause=ValueError(f"non-json response: {text[:80]}"))

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        try:
            r = self._client.models.embed_content(
                model=model or self.model_embed,
                contents=text,
            )
        except Exception as e:
            raise BackendError(backend="gemini", stage="embed",
                                transient=_classify(e), cause=e) from e
        # SDK 응답에서 embedding values 추출 (구체 shape 는 implement 시 확인)
        return list(r.embeddings[0].values)

    def test_connection(self) -> bool:
        try:
            # 가장 가벼운 — model listing
            list(self._client.models.list())
            return True
        except Exception:
            return False
```

- [ ] **Step 3: 통과 + 회귀**

```powershell
pytest tests/test_llm_backend_gemini.py -v
pytest -q
```

Expected: 5 passed → 회귀 `1106 passed`.

- [ ] **Step 4: registry 의 gemini factory 등록**

```python
# src/assetcache/core/llm/registry.py 의 from_config 에 gemini_factory default 추가
# 기존 인자만 추가하는 게 아니라, factory 미지정 시 자체 빌드도 가능하게:
def _default_gemini_factory(*, settings, cfg):
    from .backends.gemini import GeminiBackend
    return GeminiBackend(
        api_key=settings.get("api_key") or _env("GEMINI_API_KEY"),
        model_image=settings["model_image"],
        model_audio=settings["model_audio"],
        model_embed=settings["model_embed"],
        timeout=cfg.analysis_timeout_seconds,
    )

# from_config 의 기본값 변경
gemini_factory: Callable[..., LLMBackend] | None = _default_gemini_factory,
```

`_env(name)` 헬퍼 (같은 파일):

```python
import os
def _env(name: str) -> str:
    return os.environ.get(name, "")
```

- [ ] **Step 5: registry 통합 테스트 추가**

```python
# tests/test_llm_registry.py 에 추가
def test_registry_gemini_via_factory(monkeypatch):
    """gemini_factory 가 호출돼 GeminiBackend 인스턴스가 chain 에 들어가는지."""
    cfg = Config()
    cfg.backends["gemini"]["enabled"] = True
    cfg.backends["gemini"]["api_key"] = "AIzaTest"
    cfg.chains["chat_image"] = ["gemini"]
    # 실 gemini 패키지를 호출하지 않도록 monkeypatch:
    from assetcache.core.llm import registry as reg_mod
    monkeypatch.setattr(reg_mod, "_default_gemini_factory",
                        lambda settings, cfg: _FakeGemini())
    reg = BackendRegistry.from_config(cfg)
    chain = reg.get_chain("chat_image")
    assert chain.backends[0].info.name == "gemini"
```

- [ ] **Step 6: 통과 + 커밋**

```powershell
pytest tests/test_llm_backend_gemini.py tests/test_llm_registry.py -v
pytest -q
```

Expected: 신규 1 + 기존 통과 → `1107 passed`.

```powershell
git add src/assetcache/core/llm/backends/gemini.py src/assetcache/core/llm/registry.py tests/test_llm_backend_gemini.py tests/test_llm_registry.py
git commit -m "feat(m11): GeminiBackend + registry factory"
```

### Task 1.2: Gemini integration 테스트 (옵트인)

**Files:**
- Create: `tests/test_llm_backend_gemini_integration.py`

- [ ] **Step 1: `@pytest.mark.llm_integration` 테스트 추가**

```python
# tests/test_llm_backend_gemini_integration.py
"""GeminiBackend integration — 실 API key 필요 (`pytest -m llm_integration`)."""

from __future__ import annotations

import os

import pytest

from assetcache.core.llm.backends.gemini import GeminiBackend
from assetcache.core.llm.base import ChatMessage


pytestmark = pytest.mark.llm_integration


@pytest.fixture
def gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY env not set")
    return GeminiBackend(
        api_key=api_key,
        model_image="gemini-2.5-flash",
        model_audio="gemini-2.5-flash",
        model_embed="gemini-embedding-001",
        timeout=60.0,
    )


def test_gemini_text_chat(gemini):
    out = gemini.chat([ChatMessage("user", 'reply with {"ok": true}')], force_json=True)
    assert out.get("ok") is True


def test_gemini_test_connection(gemini):
    assert gemini.test_connection() is True


def test_gemini_embed_dim_768(gemini):
    vec = gemini.embed("hello")
    assert len(vec) == 768
```

- [ ] **Step 2: 기본 실행 시 deselect 확인**

```powershell
pytest -q
```

Expected: `1107 passed` (llm_integration 은 deselect).

- [ ] **Step 3: 사용자가 실 key 로 옵트인 검증 (수동)**

`$env:GEMINI_API_KEY = "AIza..."; pytest -m llm_integration tests/test_llm_backend_gemini_integration.py`

- [ ] **Step 4: 커밋**

```powershell
git add tests/test_llm_backend_gemini_integration.py
git commit -m "test(m11): Gemini integration 옵트인 (3 케이스)"
```

---

## Phase 2 — Claude backend (image only, ~1일, +6 테스트)

목표: `anthropic` SDK 통합 + image 전용 (audio 미지원). modality skip 동작 검증.

### Task 2.0: 의존성 추가

```toml
# pyproject.toml dependencies 에
  "anthropic>=0.40",
```

```powershell
pip install -e .
pytest -q
```

Expected: `1107 passed`. 커밋: `build(m11): anthropic>=0.40 의존성`.

### Task 2.1: `ClaudeBackend`

**Files:**
- Create: `src/assetcache/core/llm/backends/claude.py`
- Create: `tests/test_llm_backend_claude.py`
- Create: `tests/test_llm_backend_claude_integration.py`

- [ ] **Step 1: failing mock 테스트**

```python
# tests/test_llm_backend_claude.py
"""ClaudeBackend — anthropic SDK mock 기반. audio 미지원 검증 포함."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from assetcache.core.llm.backends.claude import ClaudeBackend
from assetcache.core.llm.base import BackendError, ChatMessage


def test_claude_capabilities():
    assert ClaudeBackend.info.capabilities.supports_chat_image
    assert ClaudeBackend.info.capabilities.supports_chat_audio is False
    assert ClaudeBackend.info.capabilities.supports_text_embed is False


def test_claude_chat_text_only(monkeypatch):
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text='{"category": "ui"}', type="text")]
    fake_client.messages.create.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(api_key="x", model_image="claude-haiku-4-5-20251001", timeout=60.0)
    out = b.chat([ChatMessage("user", "hi")])
    assert out == {"category": "ui"}


def test_claude_chat_with_image(monkeypatch):
    # ... image part 가 source.type=base64 로 포함되는지 검증 ...
    ...


def test_claude_embed_raises_not_supported():
    b = ClaudeBackend.__new__(ClaudeBackend)
    with pytest.raises(BackendError) as exc:
        b.embed("text")
    assert exc.value.transient is False  # capability 자체 미지원 → hard


def test_claude_auth_error_is_hard(monkeypatch):
    import anthropic
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = anthropic.AuthenticationError(
        message="invalid api key", response=MagicMock(), body=None,
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is False
```

- [ ] **Step 2: `claude.py` 구현**

```python
# src/assetcache/core/llm/backends/claude.py
"""ClaudeBackend — anthropic SDK wrap. **audio 미지원** — capability=False.

embed: Claude 는 embedding 모델 없음 → embed() 호출 시 hard BackendError.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
from anthropic import Anthropic

from ..base import BackendCapabilities, BackendError, BackendInfo, ChatMessage

log = logging.getLogger(__name__)

_HARD = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.BadRequestError,
)


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
    )

    def __init__(self, *, api_key: str, model_image: str, timeout: float) -> None:
        if not api_key:
            raise BackendError(backend="claude", stage="init", transient=False,
                                cause=ValueError("api_key empty"))
        self._client = Anthropic(api_key=api_key, timeout=timeout)
        self.model_image = model_image

    def _to_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        out = []
        for m in messages:
            content: list[dict[str, Any]] = [{"type": "text", "text": m.content}]
            for b64 in m.images_b64:
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": b64},
                })
            # audio_b64 은 무시 — capability 가 false 라 chain 이 audio 모드에선 skip
            out.append({"role": m.role, "content": content})
        return out

    def chat(self, messages: list[ChatMessage], *, force_json: bool = True,
             num_ctx: int = 8000) -> dict:
        sys_prompt = "Reply with strict JSON only." if force_json else ""
        try:
            r = self._client.messages.create(
                model=self.model_image,
                max_tokens=2000,
                system=sys_prompt,
                messages=self._to_messages(messages),
            )
        except _HARD as e:
            raise BackendError(backend="claude", stage="chat", transient=False, cause=e) from e
        except (anthropic.RateLimitError, anthropic.APIStatusError) as e:
            raise BackendError(backend="claude", stage="chat", transient=True, cause=e) from e
        except Exception as e:
            raise BackendError(backend="claude", stage="chat", transient=True, cause=e) from e
        text = ""
        for block in r.content:
            if getattr(block, "type", None) == "text":
                text += block.text
        if force_json:
            try:
                return json.loads(text)
            except (json.JSONDecodeError, ValueError):
                raise BackendError(backend="claude", stage="chat", transient=True,
                                    cause=ValueError(f"non-json: {text[:80]}"))
        return {"text": text}

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        raise BackendError(backend="claude", stage="embed", transient=False,
                            cause=NotImplementedError("Claude has no embedding model"))

    def test_connection(self) -> bool:
        try:
            self._client.messages.create(
                model=self.model_image, max_tokens=1,
                messages=[{"role": "user", "content": "x"}],
            )
            return True
        except Exception:
            return False
```

- [ ] **Step 3: integration 옵트인 + 통과 + 커밋**

```python
# tests/test_llm_backend_claude_integration.py — Gemini 와 동일 패턴
```

```powershell
pytest tests/test_llm_backend_claude.py -v
pytest -q
git add ...
git commit -m "feat(m11): ClaudeBackend (image only, audio 미지원)"
```

Expected: `1113 passed`.

### Task 2.2: registry claude factory + modality skip 검증

**Files:**
- Modify: `src/assetcache/core/llm/registry.py`
- Modify: `tests/test_llm_chain.py` (추가 케이스)

- [ ] **Step 1: registry 에 claude_factory 등록 (Phase 1 패턴 그대로)**
- [ ] **Step 2: chain 통합 테스트 — claude 가 audio chain 에 있으면 skip 되는지 추가 검증**
- [ ] **Step 3: 통과 + 커밋**

Expected: `1115 passed` (claude factory 1 + chain skip 1).

---

## Phase 3 — OpenAI backend (~1.5일, +8 테스트)

목표: `openai` SDK 통합 + image (Vision) + audio (gpt-4o-audio-preview) + embed (text-embedding-3-small).

### Task 3.0: 의존성

```toml
  "openai>=1.50",
```

### Task 3.1: `OpenAIBackend`

**Files:**
- Create: `src/assetcache/core/llm/backends/openai_backend.py` (모듈명 `openai` 충돌 회피)
- Create: `tests/test_llm_backend_openai.py`
- Create: `tests/test_llm_backend_openai_integration.py`

`openai.OpenAI(api_key=..., base_url=...)` 사용. `base_url` 인자가 Phase 4 의 OpenRouter 에서 specialization 가능하도록 expose:

```python
class OpenAIBackend:
    info = BackendInfo(
        name="openai", display_name="OpenAI", homepage="https://platform.openai.com/",
        capabilities=BackendCapabilities(True, True, True, embed_dim=1536),
    )
    def __init__(self, *, api_key, model_image, model_audio, model_embed,
                 timeout, base_url=None):
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        # ... model_* 저장 ...

    def chat(self, messages, *, force_json=True, num_ctx=8000):
        # messages → openai chat completions 의 multipart (image_url / input_audio)
        # response_format={"type": "json_object"} for force_json
        ...
    def embed(self, text, *, model=None):
        r = self._client.embeddings.create(model=model or self.model_embed, input=text)
        return list(r.data[0].embedding)
```

에러 분류:
- `openai.AuthenticationError / PermissionDeniedError` → hard
- `openai.RateLimitError / APIStatusError(5xx) / APIConnectionError` → transient

- [ ] mock 테스트 (5 케이스) — Phase 1 패턴 그대로
- [ ] integration 옵트인 (3 케이스: chat text / embed dim 1536 / test_connection)
- [ ] registry openai_factory 등록
- [ ] 통과 + 커밋 → `1123 passed`

---

## Phase 4 — OpenRouter + HuggingFace (~1.5일, +10 테스트)

### Task 4.1: `OpenRouterBackend`

`OpenAIBackend` 의 specialization (subclass). modality: image only.

```python
class OpenRouterBackend(OpenAIBackend):
    info = BackendInfo(
        name="openrouter", display_name="OpenRouter (free routing)",
        homepage="https://openrouter.ai/",
        capabilities=BackendCapabilities(True, False, False, embed_dim=None),
    )
    def __init__(self, *, api_key, model_image, timeout):
        super().__init__(
            api_key=api_key, model_image=model_image, model_audio="",
            model_embed="", timeout=timeout,
            base_url="https://openrouter.ai/api/v1",
        )
```

rate limit 429 → transient (BackendChain 이 다음으로 fallback).

- [ ] mock 5 케이스 + integration 옵트인 2 케이스 (실 OpenRouter API key 필요)

### Task 4.2: `HuggingFaceBackend`

```python
from huggingface_hub import InferenceClient
class HuggingFaceBackend:
    info = BackendInfo(
        name="huggingface", display_name="HuggingFace Inference",
        homepage="https://huggingface.co/docs/inference-providers/",
        capabilities=BackendCapabilities(True, True, True, embed_dim=None),
    )
    def __init__(self, *, api_key, model_image, model_audio, model_embed, timeout):
        self._client = InferenceClient(token=api_key)
        # ...
    def chat(self, messages, **kw):
        out = self._client.chat_completion(model=..., messages=[...])
        # ...
    def embed(self, text, *, model=None):
        return self._client.feature_extraction(text, model=model or self.model_embed)
```

- [ ] mock 5 케이스 + integration 옵트인 2 케이스

### Task 4.3: registry 통합 + 커밋

- [ ] openrouter_factory + huggingface_factory 등록
- [ ] 통과 + 회귀 → `1133 passed`
- [ ] 커밋

---

## Phase 5 — /settings UI (~2일, +10 테스트)

목표: 6 backend 카드 UI + chain 우선순위 drag-drop + "테스트" 버튼.

### Task 5.1: `_backend_card.html` 템플릿

**Files:**
- Create: `src/assetcache/web/templates/settings/_backend_card.html`

기존 `web/templates/settings/index.html` 의 구조 따라 HTMX 부분 갱신 패턴. 카드 1개에:
- Enabled checkbox (`hx-post` `/settings/backends/<name>` `name="enabled"`)
- API key input (password type)
- Model dropdown 또는 input (사전 정의 + custom 입력)
- "테스트" 버튼 (`hx-post` `/settings/backends/<name>/test`)
- 결과 표시 영역 (`hx-swap-oob`)

### Task 5.2: `_chains_panel.html` 템플릿

drag-drop 리스트. SortableJS CDN 1개 추가 또는 alpine.js 자체 구현.

```html
<div x-data="{ list: {{ chains.chat_image | tojson }} }" class="sortable">
  <template x-for="name in list" :key="name">
    <div class="chain-item" :data-name="name">
      <span x-text="name"></span>
    </div>
  </template>
</div>
```

### Task 5.3: `web/routers/settings.py` 확장

```python
@router.post("/settings/backends/{name}")
async def update_backend(name: str, request: Request, cfg: Config = Depends(get_config)):
    # form data → cfg.backends[name] update
    # save_config
    # 응답: 변경된 카드 HTML fragment (HTMX)
    ...

@router.post("/settings/backends/{name}/test")
async def test_backend(name: str, registry: BackendRegistry = Depends(get_registry)):
    backend = registry.get_backend(name)
    if not backend:
        return HTMLResponse('<span class="error">backend not configured</span>')
    ok = backend.test_connection()
    return HTMLResponse(f'<span class="{"ok" if ok else "error"}">{"✅ 성공" if ok else "❌ 실패"}</span>')

@router.post("/settings/chains")
async def update_chains(request: Request, ...):
    # form data: chat_image_order=ollama,gemini,claude → cfg.chains["chat_image"] = [...]
    ...
```

### Task 5.4: i18n msgid

`web/locale/ko/LC_MESSAGES/messages.po` + `en/...`:
- `"Backends"` / `"백엔드"`
- `"Image chain"` / `"이미지 체인"`
- `"Audio chain"` / `"오디오 체인"`
- `"Embedding chain"` / `"임베딩 체인"`
- `"API key"` / `"API 키"`
- `"Test connection"` / `"연결 테스트"`
- `"Connection succeeded"` / `"연결 성공"`
- `"Connection failed: %s"` / `"연결 실패: %s"`

```powershell
pybabel extract -F src/assetcache/web/babel.cfg -o src/assetcache/web/locale/messages.pot src/assetcache/web
pybabel update -i src/assetcache/web/locale/messages.pot -d src/assetcache/web/locale
# .po 편집 후
pybabel compile -d src/assetcache/web/locale
```

### Task 5.5: 테스트

```python
# tests/test_web_routers_settings_backends.py
"""POST /settings/backends/<name> + /test + /chains."""

def test_post_backend_enables_and_saves(client, tmp_config):
    r = client.post("/settings/backends/gemini",
                     data={"enabled": "true", "api_key": "AIzaTest", "model_image": "x"})
    assert r.status_code == 200
    cfg = load_config(tmp_config)
    assert cfg.backends["gemini"]["enabled"] is True
    assert cfg.backends["gemini"]["api_key"] == "AIzaTest"


def test_post_backend_test_connection(client, mock_registry):
    mock_registry.get_backend("ollama").test_connection = lambda: True
    r = client.post("/settings/backends/ollama/test")
    assert "성공" in r.text


def test_post_chains_reorder(client, tmp_config):
    r = client.post("/settings/chains",
                     data={"chat_image_order": "gemini,ollama"})
    assert r.status_code == 200
    cfg = load_config(tmp_config)
    assert cfg.chains["chat_image"] == ["gemini", "ollama"]
```

- [ ] 통과 + 커밋 → `1143 passed`

### Task 5.6: e2e Playwright 1 케이스 (옵트인 `e2e` marker)

- [ ] `tests/test_e2e_settings_backends.py` — 사용자 시나리오:
  1. `/settings` 진입
  2. Gemini 카드의 Enable 체크
  3. API key 입력 → 저장
  4. "테스트" 버튼 클릭 → "❌ 실패" 표시 (실 key 없으므로)
  5. config.toml 에 enabled=true / api_key 저장 확인

---

## Phase 6 — per-asset metadata + 가시화 (~1일, +10 테스트)

### Task 6.1: DB 컬럼 추가

**Files:**
- Modify: `src/assetcache/core/store.py`

```python
# core/store.py 의 SCHEMA 또는 _migrate() 에 추가
ALTER TABLE assets ADD COLUMN backend_image TEXT;
ALTER TABLE assets ADD COLUMN backend_audio TEXT;
ALTER TABLE assets ADD COLUMN backend_embed TEXT;
```

`save_asset_analysis()` 시그니처에 3 인자 추가. SQL `INSERT/UPDATE assets` 갱신.

- [ ] `tests/test_store_backend_columns.py` (5 케이스):
  - 새 컬럼 마이그레이션 (기존 row NULL)
  - save_asset_analysis 가 backend_image 저장
  - 검색 SELECT 가 backend_* 컬럼 반환

### Task 6.2: MCP find_asset 응답에 `backend_used`

**Files:**
- Modify: `src/assetcache/mcp/models.py`
- Modify: `src/assetcache/mcp/tools.py`

```python
# models.py
class FindAssetItem(BaseModel):
    # ... 기존 필드 ...
    backend_used: dict[str, str] | None = None  # {"image": "gemini", ...}

# tools.py 의 find_asset 핸들러에서 store 의 backend_* 값을 매핑
```

`docs/MCP_USAGE_GUIDE.md` 갱신 — find_asset 응답 예시에 `backend_used` 추가.

- [ ] `tests/test_mcp_find_asset_backend.py` (3 케이스):
  - find_asset 응답에 backend_used 포함
  - legacy NULL row 의 응답에 backend_used=None
  - 새로 분석된 row 의 응답에 backend_used={"image": "...", ...}

### Task 6.3: 웹 검색 결과 카드에 backend 배지

**Files:**
- Modify: `src/assetcache/web/templates/_search_result_card.html` (또는 비슷)

```html
{% if result.backend_used %}
  <span class="badge backend-badge" title="{{ _('Analyzed by %s') | format(result.backend_used.image) }}">
    {{ result.backend_used.image }}
  </span>
{% endif %}
```

- [ ] 통과 + 커밋 → `1153 passed`

---

## Phase 7 — verification + 문서 (~1일, +5 테스트)

### Task 7.1: cross-backend integration 테스트

**Files:**
- Create: `tests/test_llm_integration_cross_backend.py`

```python
# tests/test_llm_integration_cross_backend.py
"""실제 BackendChain 3개 backend mock 으로 fallback 시나리오 검증."""

def test_chain_first_transient_then_success(monkeypatch):
    # backend 1 (ollama) 가 transient fail → backend 2 (gemini) success
    ...

def test_chain_first_hard_immediately_raises(monkeypatch):
    ...

def test_chain_modality_skip_in_real_setup(monkeypatch):
    # claude 가 audio chain 에 있어도 skip + ollama 가 처리
    ...
```

### Task 7.2: DESIGN.md 갱신

- §3 (아키텍처) — `core/llm/` 패키지 + Multi-backend 다이어그램 추가
- §4.5 (MCP 도구) — find_asset 응답 schema 에 backend_used 추가
- §10 (Config) — `[backends.*]` + `[chains]` 섹션 추가
- §11 (로드맵) — M11 완료 표시 + M12 candidate 갱신

### Task 7.3: README.md "Multi-backend LLM" 섹션

- /settings 사용법 + 6 backend 비교 표 (M11 spec §5 의 표 재사용)
- 환경변수 alternative (GEMINI_API_KEY 등)

### Task 7.4: HANDOFF.md + CLAUDE.md 갱신

- HANDOFF.md §1 한 줄 요약 — M11 완료 + 신규 테스트 수
- CLAUDE.md §2 진행 현황 표 — M11 row 추가 (✅ 완료)
- CLAUDE.md §6 — pytest 수 갱신 (1153 passed)
- CLAUDE.md §8.3 마일스톤 정렬 — M11 row 갱신 (✅)

### Task 7.5: `milestones/M11_verification.md`

수동 시나리오 6건 (spec §11 Phase 7 참조). 자동 검증은 cross-backend integration 으로.

### Task 7.6: M11 PR

```powershell
git push -u origin feat/m11-multi-backend-llm
gh pr create --title "M11 — Multi-backend LLM Architecture (Ollama+Gemini+Claude+OpenAI+OpenRouter+HF)" --body @"
## Summary
- Modality 별 backend chain (chat_image / chat_audio / text_embed) + 자동 fallback
- 6 backend: Ollama (local) + Gemini + Claude + OpenAI + OpenRouter + HuggingFace
- /settings 페이지: backend 카드 + drag-drop 우선순위 + 연결 테스트
- per-asset `backend_used` 메타데이터 + 검색 결과 카드 배지
- 신규 의존성 4건 (google-genai / anthropic / openai / huggingface_hub)

## Verification
- `pytest -q` → 1153 passed + 1 skipped + 40 deselected (회귀 1079 → +74)
- `pytest -m llm_integration` 옵트인 — 실 API key 필요
- 수동 시나리오 6건 — `milestones/M11_verification.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
"@
```

머지 후 main checkout + cleanup (feat/m11 delete).

---

## Self-Review 결과

본 plan 의 Phase/Task 별 spec §11 acceptance 매핑:

| spec §11 Phase | plan Task | acceptance criteria |
|---|---|---|
| Phase 0 | Task 0.0~0.8 | 회귀 1079 → 1101 (+22 신규) |
| Phase 1 (Gemini) | Task 1.0~1.2 | +6 mock + 3 integration 옵트인 |
| Phase 2 (Claude) | Task 2.0~2.2 | +5 mock + 2 integration / audio skip |
| Phase 3 (OpenAI) | Task 3.0~3.1 | +5 mock + 3 integration |
| Phase 4 (OpenRouter + HF) | Task 4.0~4.3 | +10 mock + 4 integration |
| Phase 5 (/settings UI) | Task 5.1~5.6 | +10 라우터/템플릿 테스트 + 1 e2e |
| Phase 6 (metadata) | Task 6.1~6.3 | +8 (DB + MCP + 카드 배지) |
| Phase 7 (verification) | Task 7.1~7.6 | +5 cross-backend integration, 문서, PR |

**최종 목표**: ~1153 passed (회귀 1079 + 74 신규).

---

## Execution 옵션

**1. Subagent-Driven (권장)** — Phase 0 끝까지는 main session 진행 (회귀 1079 → 1101 critical), Phase 1~7 은 task 단위 subagent dispatch + review.

**2. Inline Execution** — main session 에서 phase 단위로 batch 실행, 각 phase 끝에 회귀 + commit.
