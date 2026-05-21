"""M11.4 Phase 4 — sync SpriteAnalyzer 의 inventory_item / ui_icon 분류 회귀.

batch BATCH_IMAGE_PROMPT 와 동일 가이드 (enum + hex 거부 + crown/sword/potion
예시) 를 sync ``_build_system_prompt`` 에도 적용한다.  registry 기반 enum
자동 주입 덕에 ``inventory_item`` / ``ui_icon`` 토큰은 시드에 등록되면
prompt 에 자동 포함되지만, hex 거부 + inventory 예시 가이드는 명시적으로
prompt 텍스트에 들어가야 한다.
"""
from __future__ import annotations

import pytest

from assetcache.core.analyzer.sprite import SpriteAnalyzer
from assetcache.core.clip_labeler import ClipLabeler, FakeBackend
from assetcache.core.embedding import EmbeddingEncoder
from assetcache.core.labels import LabelRegistry
from assetcache.core.ollama_client import OllamaClient


class _FakeEmbedOllama:
    def embed(self, text, *, model=None):  # noqa: ANN001
        return [0.1] * 16


@pytest.fixture
def analyzer(store) -> SpriteAnalyzer:
    registry = LabelRegistry(store)
    registry.bootstrap()
    client = OllamaClient(
        base_url="http://127.0.0.1:11434", model="gemma4:e4b",
        timeout_seconds=5, max_retries=1,
    )
    embedder = EmbeddingEncoder(_FakeEmbedOllama())  # type: ignore[arg-type]
    clip = ClipLabeler(
        backend=FakeBackend(dim=64), store=store,
        registry=registry, enabled=False,
    )
    return SpriteAnalyzer(
        ollama=client, clip=clip, embedder=embedder, registry=registry,
    )


def test_sync_prompt_category_enum_includes_inventory_item_and_ui_icon(
    analyzer: SpriteAnalyzer,
) -> None:
    """sync prompt 의 category enum 에 신규 토큰 inventory_item / ui_icon 포함."""
    prompt = analyzer._build_system_prompt(language="en")
    assert "inventory_item" in prompt
    assert "ui_icon" in prompt


def test_sync_prompt_rejects_hex_palette_explicitly(
    analyzer: SpriteAnalyzer,
) -> None:
    """sync prompt 도 batch 와 동일하게 hex palette 사용 금지 명시."""
    prompt = analyzer._build_system_prompt(language="en")
    assert "hex" in prompt.lower()


def test_sync_prompt_has_inventory_item_guidance_with_examples(
    analyzer: SpriteAnalyzer,
) -> None:
    """sync prompt 가 crown/sword/potion 같은 inventory 예시로 분류 유도."""
    lower = analyzer._build_system_prompt(language="en").lower()
    examples = ("crown", "sword", "potion", "gem", "scroll", "key")
    assert any(e in lower for e in examples), \
        "sync prompt should mention at least one inventory item example"


def test_sync_prompt_drops_inventory_item_guidance_when_label_disabled(
    store,
) -> None:
    """M11.4 cleanup #9 — inventory_item 라벨 disable 시 guidance 텍스트도 사라짐."""
    registry = LabelRegistry(store)
    registry.bootstrap()
    registry.set_enabled("category", "inventory_item", False)

    client = OllamaClient(
        base_url="http://127.0.0.1:11434", model="gemma4:e4b",
        timeout_seconds=5, max_retries=1,
    )
    embedder = EmbeddingEncoder(_FakeEmbedOllama())  # type: ignore[arg-type]
    clip = ClipLabeler(
        backend=FakeBackend(dim=64), store=store,
        registry=registry, enabled=False,
    )
    analyzer = SpriteAnalyzer(
        ollama=client, clip=clip, embedder=embedder, registry=registry,
    )
    prompt = analyzer._build_system_prompt(language="en")
    # registry enum 자동 + guidance 둘 다 inventory_item 사라짐
    assert "inventory_item" not in prompt
    # ui_icon 은 여전히 enabled 라 guidance 유지
    assert "ui_icon" in prompt


def test_sync_prompt_drops_all_guidance_when_no_relevant_labels_enabled(
    store,
) -> None:
    """inventory_item + ui_icon 모두 disable → Guidance 섹션 자체 없음."""
    registry = LabelRegistry(store)
    registry.bootstrap()
    registry.set_enabled("category", "inventory_item", False)
    registry.set_enabled("category", "ui_icon", False)

    client = OllamaClient(
        base_url="http://127.0.0.1:11434", model="gemma4:e4b",
        timeout_seconds=5, max_retries=1,
    )
    embedder = EmbeddingEncoder(_FakeEmbedOllama())  # type: ignore[arg-type]
    clip = ClipLabeler(
        backend=FakeBackend(dim=64), store=store,
        registry=registry, enabled=False,
    )
    analyzer = SpriteAnalyzer(
        ollama=client, clip=clip, embedder=embedder, registry=registry,
    )
    prompt = analyzer._build_system_prompt(language="en")
    assert "inventory_item" not in prompt
    assert "ui_icon" not in prompt
    assert "Guidance:" not in prompt
