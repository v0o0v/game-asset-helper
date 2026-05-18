"""M6 — SpritesheetAnalyzer (시트 감지 + Gemma + 폴백)."""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from gah.core.analyzer.base import AnalyzerInput, AnalyzerResult
from gah.core.analyzer.spritesheet import SpritesheetAnalyzer

FIXTURES = Path(__file__).parent / "fixtures" / "sheets"


def _make_sheet_png(path: Path, frame_count: int, fw: int = 32, fh: int = 32, gap: int = 2):
    total_w = frame_count * fw + (frame_count - 1) * gap
    img = Image.new("RGBA", (total_w, fh), (0, 0, 0, 0))
    for i in range(frame_count):
        tile = Image.new("RGBA", (fw, fh), (((i * 30) % 255), 100, 50, 255))
        img.paste(tile, (i * (fw + gap), 0))
    img.save(path)


def _make_single_png(path: Path):
    Image.new("RGBA", (32, 32), (200, 100, 50, 255)).save(path)


@pytest.fixture()
def sprite_mock():
    """SpriteAnalyzer mock — analyze() 가 dummy AnalyzerResult 반환."""
    from gah.core.store import SpriteMeta
    from gah.core.searchable import SearchableTexts
    sa = MagicMock()
    sa.analyze.return_value = AnalyzerResult(
        kind="sprite", state="ok", error=None,
        sprite_meta=SpriteMeta(width=32, height=32, has_alpha=True,
                              is_pixel_art=True, dominant_colors=["#000000"]),
        sound_meta=None,
        labels=[],
        searchable=SearchableTexts(for_fts="x", for_embed="x"),
        embedding_vector=b"\0" * 4, embedding_dim=1,
        embedding_model="test",
        description="",
    )
    return sa


@pytest.fixture()
def ollama_mock():
    """OllamaClient mock — animation_hint=['walk'] 응답."""
    o = MagicMock()
    o.chat.return_value = {
        "description": "hero walking", "subject": "hero",
        "category": "character", "style": "pixel_art",
        "mood": ["energetic"], "palette": ["warm"],
        "animation_hint": ["walk"], "confidence": 0.8,
    }
    return o


@pytest.fixture()
def registry_mock():
    r = MagicMock()
    r.list_labels.return_value = ["walk", "idle", "run", "attack", "hurt",
                                  "death", "cast", "crouch", "jump", "other"]
    return r


@pytest.fixture()
def embedder_mock():
    e = MagicMock()
    e.model = "test-embed"
    e.encode_text.return_value = (b"\0\0\0\0", 1)
    return e


def test_aseprite_json_sidecar_promotes_to_spritesheet(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "hero_walk_aseprite_array.png"
    shutil.copy(FIXTURES / "hero_walk_aseprite_array.json",
                tmp_path / "hero_walk_aseprite_array.json")
    _make_sheet_png(png, frame_count=8)

    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=1, pack_id=1,
                       abs_path=png, rel_path="x/hero_walk.png")
    result = analyzer.analyze(inp)

    assert result.kind == "spritesheet"
    assert result.sprite_meta is not None
    assert result.sprite_meta.frame_count == 8
    assert result.sprite_meta.frame_w == 32
    assert result.sprite_meta.frame_h == 32
    assert "walk" in (result.sprite_meta.animations_json or {})
    walk = result.sprite_meta.animations_json["walk"]
    assert walk["start_frame"] == 0
    assert walk["end_frame"] == 7
    assert walk["source"] == "json_tag"


def test_grid_only_uses_full_sheet_range(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "slime.png"
    _make_sheet_png(png, frame_count=4)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=2, pack_id=1, abs_path=png, rel_path="x/slime.png")
    result = analyzer.analyze(inp)

    assert result.kind == "spritesheet"
    assert result.sprite_meta.frame_count == 4
    anim = result.sprite_meta.animations_json
    assert "walk" in anim
    assert anim["walk"]["start_frame"] == 0
    assert anim["walk"]["end_frame"] == 3
    assert anim["walk"]["source"] == "gemma_inferred"


def test_single_image_falls_back_to_sprite(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "sword.png"
    _make_single_png(png)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=3, pack_id=1, abs_path=png, rel_path="x/sword.png")
    result = analyzer.analyze(inp)

    assert result.kind == "sprite"
    sprite_mock.analyze.assert_called_once()


def test_animation_tags_backward_compat(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "x_aseprite.png"
    shutil.copy(FIXTURES / "hero_walk_aseprite_array.json",
                tmp_path / "x_aseprite.json")
    _make_sheet_png(png, frame_count=8)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=4, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    assert "walk" in (result.sprite_meta.animation_tags or [])


def test_gemma_failure_partial_state(tmp_path, sprite_mock, registry_mock, embedder_mock):
    from gah.core.ollama_client import OllamaError
    bad_ollama = MagicMock()
    bad_ollama.chat.side_effect = OllamaError(stage="chat", path="/api/chat")
    png = tmp_path / "x.png"
    shutil.copy(FIXTURES / "hero_walk_aseprite_array.json",
                tmp_path / "x.json")
    _make_sheet_png(png, frame_count=8)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=bad_ollama,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=5, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    assert result.kind == "spritesheet"
    assert result.sprite_meta.frame_count == 8
    assert result.state == "partial"
    assert "walk" in (result.sprite_meta.animations_json or {})


def test_aseprite_tags_take_priority_over_gemma(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    ollama_mock.chat.return_value = {
        "description": "x", "subject": "x",
        "category": "character", "style": "pixel_art",
        "mood": [], "palette": [],
        "animation_hint": ["run"], "confidence": 0.5,
    }
    png = tmp_path / "x.png"
    shutil.copy(FIXTURES / "hero_walk_aseprite_array.json",
                tmp_path / "x.json")
    _make_sheet_png(png, frame_count=8)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=6, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    anim = result.sprite_meta.animations_json
    assert "walk" in anim
    assert anim["walk"]["source"] == "json_tag"
    if "run" in anim:
        assert anim["run"]["source"] == "gemma_inferred"


def test_multi_label_gemma_full_sheet_range(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    ollama_mock.chat.return_value = {
        "description": "x", "subject": "x",
        "category": "character", "style": "pixel_art",
        "mood": [], "palette": [],
        "animation_hint": ["walk", "idle"], "confidence": 0.6,
    }
    png = tmp_path / "x.png"
    _make_sheet_png(png, frame_count=4)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=7, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    anim = result.sprite_meta.animations_json
    assert "walk" in anim and "idle" in anim
    assert anim["walk"]["end_frame"] == 3
    assert anim["idle"]["end_frame"] == 3


def test_non_rgba_png_handled(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "rgb.png"
    Image.new("RGB", (128, 32), (100, 100, 100)).save(png)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=8, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    assert result.kind == "sprite"
    sprite_mock.analyze.assert_called_once()


def test_detection_grid_no_animation_hint(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    ollama_mock.chat.return_value = {
        "description": "x", "subject": "x",
        "category": "character", "style": "pixel_art",
        "mood": [], "palette": [],
        "animation_hint": [], "confidence": 0.7,
    }
    png = tmp_path / "x.png"
    _make_sheet_png(png, frame_count=4)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=9, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    assert result.kind == "spritesheet"
    assert result.sprite_meta.animations_json == {}


def test_analyzer_input_propagated_to_sprite_fallback(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "single.png"
    _make_single_png(png)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=42, pack_id=1, abs_path=png, rel_path="single.png")
    analyzer.analyze(inp)
    call_args = sprite_mock.analyze.call_args
    assert call_args[0][0].asset_id == 42
    assert call_args[0][0].abs_path == png
