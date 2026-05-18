"""M6 — tool_suggest_animation_frames."""
from __future__ import annotations

import time

import pytest

from gah.core.manifest import PackManifest
from gah.core.store import SpriteMeta, Store
from gah.mcp.models import SuggestAnimationFramesRequest
from gah.mcp.tools import McpToolError, ToolDeps, tool_suggest_animation_frames


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "metadata.db")
    s.initialize()
    yield s
    s.close()


@pytest.fixture()
def deps(store):
    from unittest.mock import MagicMock
    return ToolDeps(
        store=store, search=MagicMock(), usage=MagicMock(),
        registry=MagicMock(), queue=None, config=MagicMock(),
        paths=None,
    )


def _seed_spritesheet(store: Store, animations: dict) -> int:
    pid = store.upsert_pack(
        "p", PackManifest(None, None, None, None, None), scanned_at=int(time.time())
    )
    aid = store.upsert_asset(
        pid, "p/x.png", "spritesheet", "h", 1024, added_at=int(time.time())
    )
    meta = SpriteMeta(
        width=256, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=[],
        frame_w=32, frame_h=32, frame_count=8,
        animation_tags=list(animations.keys()),
        animations_json=animations,
    )
    store.save_sprite_meta(aid, meta)
    return aid


def test_aseprite_frame_tag_lookup(deps, store):
    aid = _seed_spritesheet(store, {
        "walk": {"start_frame": 0, "end_frame": 7, "fps_hint": 12, "source": "json_tag"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    res = tool_suggest_animation_frames(deps, req)
    assert res.frame_indices == [0, 1, 2, 3, 4, 5, 6, 7]
    assert res.fps_hint == 12


def test_gemma_inferred_lookup(deps, store):
    aid = _seed_spritesheet(store, {
        "idle": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "gemma_inferred"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="idle")
    res = tool_suggest_animation_frames(deps, req)
    assert res.frame_indices == [0, 1, 2, 3]


def test_asset_not_found(deps):
    req = SuggestAnimationFramesRequest(asset_id=999, animation="walk")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "404_not_found"


def test_kind_sprite_400(deps, store):
    pid = store.upsert_pack(
        "p2", PackManifest(None, None, None, None, None), scanned_at=int(time.time())
    )
    aid = store.upsert_asset(pid, "p2/sword.png", "sprite", "h2", 64, added_at=int(time.time()))
    store.save_sprite_meta(aid, SpriteMeta(
        width=32, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=[],
    ))
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "400_invalid_input"
    assert "spritesheet" in exc_info.value.message.lower()


def test_kind_sound_400(deps, store):
    pid = store.upsert_pack(
        "p3", PackManifest(None, None, None, None, None), scanned_at=int(time.time())
    )
    aid = store.upsert_asset(pid, "p3/x.wav", "sound", "h3", 64, added_at=int(time.time()))
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "400_invalid_input"


def test_animation_not_in_sheet_404_with_available(deps, store):
    aid = _seed_spritesheet(store, {
        "walk": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "json_tag"},
        "idle": {"start_frame": 4, "end_frame": 7, "fps_hint": 8, "source": "json_tag"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="attack")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "404_not_found"
    assert "walk" in exc_info.value.message
    assert "idle" in exc_info.value.message


def test_inclusive_range(deps, store):
    aid = _seed_spritesheet(store, {
        "walk": {"start_frame": 2, "end_frame": 5, "fps_hint": 10, "source": "json_tag"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    res = tool_suggest_animation_frames(deps, req)
    assert res.frame_indices == [2, 3, 4, 5]
    assert res.fps_hint == 10


def test_fps_hint_default_12(deps, store):
    aid = _seed_spritesheet(store, {
        "walk": {"start_frame": 0, "end_frame": 1, "fps_hint": 12, "source": "gemma_inferred"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    res = tool_suggest_animation_frames(deps, req)
    assert res.fps_hint == 12


def test_fps_hint_aseprite_average(deps, store):
    aid = _seed_spritesheet(store, {
        "walk": {"start_frame": 0, "end_frame": 7, "fps_hint": 11, "source": "json_tag"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    res = tool_suggest_animation_frames(deps, req)
    assert res.fps_hint == 11


def test_animations_json_null_returns_404(deps, store):
    pid = store.upsert_pack(
        "p4", PackManifest(None, None, None, None, None), scanned_at=int(time.time())
    )
    aid = store.upsert_asset(pid, "p4/x.png", "spritesheet", "h4", 64, added_at=int(time.time()))
    store.save_sprite_meta(aid, SpriteMeta(
        width=128, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=[],
        frame_w=32, frame_h=32, frame_count=4,
        animations_json=None,
    ))
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "404_not_found"


def test_empty_animations_dict_returns_404(deps, store):
    aid = _seed_spritesheet(store, {})
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "404_not_found"


def test_correct_index_sequence_for_long_range(deps, store):
    aid = _seed_spritesheet(store, {
        "run": {"start_frame": 0, "end_frame": 23, "fps_hint": 24, "source": "json_tag"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="run")
    res = tool_suggest_animation_frames(deps, req)
    assert res.frame_indices == list(range(24))
    assert res.fps_hint == 24
