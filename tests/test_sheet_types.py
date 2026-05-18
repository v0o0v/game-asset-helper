"""M6 — sheet 데이터클래스 동등성·해시·repr 회귀."""
from __future__ import annotations

import dataclasses

import pytest

from gah.core.sheet.types import (
    AnimationSpec,
    AsepriteAtlas,
    FrameSpec,
    GridLayout,
    TexturePackerAtlas,
)


def test_frame_spec_frozen_and_equal():
    a = FrameSpec(x=0, y=0, w=32, h=32, duration_ms=100, name="hero 0")
    b = FrameSpec(x=0, y=0, w=32, h=32, duration_ms=100, name="hero 0")
    assert a == b
    # frozen — 변경 시 FrozenInstanceError
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.x = 99  # type: ignore[misc]


def test_animation_spec_round_trip():
    spec = AnimationSpec(name="walk", start_frame=0, end_frame=7,
                          fps_hint=12, source="json_tag")
    assert spec.name == "walk"
    assert spec.start_frame == 0
    assert spec.end_frame == 7
    assert spec.fps_hint == 12
    assert spec.source == "json_tag"


def test_grid_layout_simple():
    g = GridLayout(rows=1, cols=8, frame_w=32, frame_h=32)
    assert g.frame_count == 8


def test_aseprite_atlas_contains_frames_and_tags():
    frame = FrameSpec(x=0, y=0, w=32, h=32, duration_ms=100, name="0")
    tag = AnimationSpec(name="walk", start_frame=0, end_frame=0,
                       fps_hint=10, source="json_tag")
    atlas = AsepriteAtlas(frames=[frame], tags=[tag])
    assert len(atlas.frames) == 1
    assert atlas.tags[0].name == "walk"


def test_texture_packer_atlas_no_tags():
    frame = FrameSpec(x=0, y=0, w=64, h=64, duration_ms=0, name="a.png")
    atlas = TexturePackerAtlas(frames=[frame])
    assert len(atlas.frames) == 1
