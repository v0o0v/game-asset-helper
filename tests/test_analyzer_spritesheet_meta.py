"""Unit tests for analyzer.spritesheet_meta — sheet detection → SpriteMeta enrichment."""

from __future__ import annotations

import pytest

from assetcache.core.analyzer.spritesheet_meta import (
    detection_to_animation_labels,
    enrich_sprite_meta_with_sheet,
)
from assetcache.core.sheet.detect import SheetDetection
from assetcache.core.sheet.types import AnimationSpec, FrameSpec
from assetcache.core.store import LabelScore, SpriteMeta


def _base_meta() -> SpriteMeta:
    return SpriteMeta(
        width=256, height=64,
        has_alpha=True, is_pixel_art=True,
        dominant_colors=["#ff0000", "#00ff00", "#0000ff", "#000000", "#ffffff"],
    )


def _frame(i: int, *, w: int = 32, h: int = 64) -> FrameSpec:
    return FrameSpec(x=i * w, y=0, w=w, h=h, duration_ms=83, name=str(i))


def _tag(name: str, *, start: int, end: int, fps: int = 12) -> AnimationSpec:
    return AnimationSpec(
        name=name, start_frame=start, end_frame=end,
        fps_hint=fps, source="json_tag",
    )


# === enrich_sprite_meta_with_sheet =====================================


def test_enrich_preserves_tech_fields_and_fills_frame_dimensions():
    base = _base_meta()
    detection = SheetDetection(
        frames=[_frame(i) for i in range(8)],
        tags=[_tag("idle", start=0, end=3),
              _tag("walk", start=4, end=7)],
        source="json",
    )
    meta = enrich_sprite_meta_with_sheet(base, detection)
    # tech 필드는 보존
    assert meta.width == 256 and meta.height == 64
    assert meta.has_alpha is True
    assert meta.is_pixel_art is True
    assert meta.dominant_colors == base.dominant_colors
    # frame 차원 + count
    assert meta.frame_w == 32
    assert meta.frame_h == 64
    assert meta.frame_count == 8


def test_enrich_builds_animations_json_from_tags():
    base = _base_meta()
    detection = SheetDetection(
        frames=[_frame(i) for i in range(8)],
        tags=[
            _tag("idle", start=0, end=3, fps=8),
            _tag("walk", start=4, end=7, fps=16),
        ],
        source="json",
    )
    meta = enrich_sprite_meta_with_sheet(base, detection)
    assert meta.animations_json == {
        "idle": {"start_frame": 0, "end_frame": 3, "fps_hint": 8, "source": "json_tag"},
        "walk": {"start_frame": 4, "end_frame": 7, "fps_hint": 16, "source": "json_tag"},
    }
    assert meta.animation_tags == ["idle", "walk"]


def test_enrich_with_no_tags_leaves_animations_none():
    base = _base_meta()
    detection = SheetDetection(
        frames=[_frame(i) for i in range(4)],
        tags=[],
        source="grid",
    )
    meta = enrich_sprite_meta_with_sheet(base, detection)
    assert meta.frame_count == 4
    assert meta.frame_w == 32
    assert meta.animation_tags is None
    assert meta.animations_json is None


def test_enrich_with_no_frames_returns_base_unchanged():
    base = _base_meta()
    detection = SheetDetection(frames=[], tags=[], source="grid")
    meta = enrich_sprite_meta_with_sheet(base, detection)
    assert meta is base  # 정확히 동일 instance — 변경 0


def test_enrich_frame_dimensions_from_first_frame_only():
    """프레임 크기가 들쭉날쭉해도 첫 프레임 기준 (sync 동작과 동일)."""
    base = _base_meta()
    detection = SheetDetection(
        frames=[
            FrameSpec(x=0, y=0, w=40, h=50, duration_ms=0, name="0"),
            FrameSpec(x=40, y=0, w=10, h=20, duration_ms=0, name="1"),
        ],
        tags=[],
        source="grid",
    )
    meta = enrich_sprite_meta_with_sheet(base, detection)
    assert meta.frame_w == 40
    assert meta.frame_h == 50
    assert meta.frame_count == 2


# === detection_to_animation_labels =====================================


def test_animation_labels_from_tags():
    detection = SheetDetection(
        frames=[_frame(i) for i in range(8)],
        tags=[
            _tag("idle", start=0, end=3),
            _tag("walk", start=4, end=7),
        ],
        source="json",
    )
    labels = detection_to_animation_labels(detection)
    assert [l.label for l in labels] == ["idle", "walk"]
    for l in labels:
        assert l.axis == "animation"
        assert l.weight == "primary"
        assert l.score == 1.0
        assert l.source == "gemma"  # 기존 DB 라벨 row 와 호환


def test_animation_labels_deduplicates_by_name():
    detection = SheetDetection(
        frames=[_frame(i) for i in range(4)],
        tags=[
            _tag("idle", start=0, end=1),
            _tag("idle", start=2, end=3),  # 같은 이름
        ],
        source="json",
    )
    labels = detection_to_animation_labels(detection)
    assert len(labels) == 1
    assert labels[0].label == "idle"


def test_animation_labels_empty_for_grid_detection():
    detection = SheetDetection(
        frames=[_frame(i) for i in range(4)],
        tags=[],
        source="grid",
    )
    labels = detection_to_animation_labels(detection)
    assert labels == []


def test_animation_labels_custom_score_and_source():
    detection = SheetDetection(
        frames=[_frame(0)],
        tags=[_tag("attack", start=0, end=0)],
        source="json",
    )
    labels = detection_to_animation_labels(
        detection, score=0.5, source="batch",
    )
    assert labels[0].score == 0.5
    assert labels[0].source == "batch"
