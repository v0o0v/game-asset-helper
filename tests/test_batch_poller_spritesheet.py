"""Batch poller — spritesheet detection + frameTags persistence.

Patch C (post-v0.2.1, third commit): when ``library_dir`` is set and the
PNG is a spritesheet (Aseprite JSON sidecar or grid-detectable), the
batch path now fills ``frame_w`` / ``frame_h`` / ``frame_count`` /
``animations_json`` / ``animation_tags`` and promotes ``kind`` to
``"spritesheet"`` — same as the sync :class:`SpritesheetAnalyzer`.

Limitation by design: batch prompt is sheet-unaware so Gemma's
``animation_hint`` augmentation is unavailable.  Grid-detected sheets
without a JSON sidecar get frame dimensions but no animation labels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from assetcache.core.batch.poller import BatchPoller


@dataclass(frozen=True)
class _LabelRow:
    label: str
    description: str | None = None


class _StubRegistry:
    def __init__(self, axis_labels: dict[str, list[str]]) -> None:
        self._axis_labels = axis_labels

    def list_labels(
        self,
        axis: str | None = None,
        *,
        enabled_only: bool = True,
        with_description: bool = False,
    ):
        labels = self._axis_labels.get(axis, []) if axis else []
        if with_description:
            return [_LabelRow(label=l) for l in labels]
        return labels


def _image_registry() -> _StubRegistry:
    return _StubRegistry({
        "category": ["character", "other"],
        "style": ["pixel_art", "other"],
        "mood": [], "palette": [], "animation": [],
    })


def _make_poller(*, library_dir: Path):
    store = MagicMock()
    store.list_active_batch_jobs.return_value = []
    chain_registry = MagicMock()
    analysis_queue = MagicMock()
    cfg = MagicMock()
    cfg.batch.poll_interval_seconds = 0.05
    return BatchPoller(
        store=store,
        chain_registry=chain_registry,
        analysis_queue=analysis_queue,
        cfg=cfg,
        registry=_image_registry(),
        library_dir=library_dir,
    ), store


def _write_png(library: Path, rel: str, *, size=(128, 32)) -> Path:
    p = library / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (200, 50, 50, 255)).save(p)
    return p


def _write_aseprite_json(
    library: Path, rel: str, *, frame_w: int, frame_h: int,
    frame_count: int, tags: list[tuple[str, int, int]],
) -> Path:
    """Aseprite hash-mode JSON 사이드카 작성."""
    frames = {
        f"frame_{i}": {
            "frame": {
                "x": i * frame_w, "y": 0, "w": frame_w, "h": frame_h,
            },
            "duration": 83,
        }
        for i in range(frame_count)
    }
    frame_tags = [
        {"name": name, "from": start, "to": end, "direction": "forward"}
        for name, start, end in tags
    ]
    data = {
        "frames": frames,
        "meta": {
            "app": "https://www.aseprite.org/",
            "frameTags": frame_tags,
        },
    }
    p = library / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# === Aseprite JSON sidecar 경로 =========================================


def test_persist_image_payload_spritesheet_via_aseprite_json(tmp_path):
    """JSON 사이드카가 있는 시트 → frame_w/h/count + frameTags 라벨 + kind promote."""
    _write_png(tmp_path, "pack/hero.png", size=(256, 64))
    _write_aseprite_json(
        tmp_path, "pack/hero.json",
        frame_w=32, frame_h=64, frame_count=8,
        tags=[("idle", 0, 3), ("walk", 4, 7)],
    )
    p, store = _make_poller(library_dir=tmp_path)
    asset = MagicMock(id=300, path="pack/hero.png")
    payload = {
        "category": "character", "style": "pixel_art",
        "description": "Hero character",
    }
    p._persist_image_payload(asset, payload)

    # sprite_meta saved with frame fields populated
    store.save_sprite_meta.assert_called_once()
    _, meta = store.save_sprite_meta.call_args.args
    assert meta.frame_w == 32
    assert meta.frame_h == 64
    assert meta.frame_count == 8
    assert meta.animation_tags == ["idle", "walk"]
    assert meta.animations_json == {
        "idle": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "json_tag"},
        "walk": {"start_frame": 4, "end_frame": 7, "fps_hint": 12, "source": "json_tag"},
    }
    # tech fields preserved
    assert meta.width == 256 and meta.height == 64
    assert meta.has_alpha is True

    # kind promoted
    store.update_asset_kind.assert_called_once_with(300, "spritesheet")

    # labels include frameTags animation labels
    saved_labels = store.save_asset_labels.call_args.args[1]
    anim_labels = [l for l in saved_labels if l.axis == "animation"]
    assert {l.label for l in anim_labels} == {"idle", "walk"}
    for l in anim_labels:
        assert l.weight == "primary"
        assert l.score == 1.0


def test_persist_image_payload_spritesheet_fts_includes_frame_tokens(tmp_path):
    """FTS 에 animation:idle 등 토큰이 포함되어야."""
    _write_png(tmp_path, "pack/hero.png", size=(128, 32))
    _write_aseprite_json(
        tmp_path, "pack/hero.json",
        frame_w=32, frame_h=32, frame_count=4,
        tags=[("attack", 0, 3)],
    )
    p, store = _make_poller(library_dir=tmp_path)
    asset = MagicMock(id=301, path="pack/hero.png")
    payload = {"category": "character", "style": "pixel_art", "description": "Hero"}
    p._persist_image_payload(asset, payload)

    _, fts_text = store.update_fts.call_args.args
    assert "animation:attack" in fts_text
    assert "label:attack" in fts_text


def test_persist_image_payload_non_sheet_keeps_sprite_kind(tmp_path):
    """단일 sprite (JSON 사이드카 없고 grid 패턴 아님) → kind 유지."""
    _write_png(tmp_path, "pack/single.png", size=(32, 32))
    p, store = _make_poller(library_dir=tmp_path)
    asset = MagicMock(id=302, path="pack/single.png")
    payload = {"category": "character", "style": "pixel_art", "description": "Single"}
    p._persist_image_payload(asset, payload)

    # sprite_meta saved but no frame fields (시트 아님)
    store.save_sprite_meta.assert_called_once()
    _, meta = store.save_sprite_meta.call_args.args
    assert meta.frame_w is None
    assert meta.frame_count is None
    # kind promotion 안 함
    store.update_asset_kind.assert_not_called()
    # animation 라벨 없음
    saved_labels = store.save_asset_labels.call_args.args[1]
    assert all(l.axis != "animation" for l in saved_labels)


def test_persist_image_payload_sheet_detection_error_falls_back_to_sprite(tmp_path):
    """detect_sheet 에서 예외 → sprite 경로로 graceful fallback."""
    _write_png(tmp_path, "pack/x.png")
    p, store = _make_poller(library_dir=tmp_path)
    asset = MagicMock(id=303, path="pack/x.png")
    payload = {"category": "character", "style": "pixel_art", "description": "x"}

    # detect_sheet 가 예외 던지도록 monkey patch
    import assetcache.core.batch.poller as poller_mod
    def _raise(_):
        raise RuntimeError("boom")
    orig = poller_mod.detect_sheet
    poller_mod.detect_sheet = _raise
    try:
        p._persist_image_payload(asset, payload)
    finally:
        poller_mod.detect_sheet = orig

    # 시트 promote 안 됨, labels 저장은 정상
    store.update_asset_kind.assert_not_called()
    store.save_sprite_meta.assert_called_once()  # tech meta 는 저장
    store.save_asset_labels.assert_called_once()


def test_persist_image_payload_without_library_dir_skips_sheet_detection(tmp_path):
    """library_dir 없으면 sheet 검출 시도 자체 X — sprite 동작."""
    _write_png(tmp_path, "x.png")
    _write_aseprite_json(tmp_path, "x.json",
                         frame_w=16, frame_h=16, frame_count=2,
                         tags=[("idle", 0, 1)])
    store_mock = MagicMock()
    store_mock.list_active_batch_jobs.return_value = []
    cfg = MagicMock()
    cfg.batch.poll_interval_seconds = 0.05
    p = BatchPoller(
        store=store_mock,
        chain_registry=MagicMock(),
        analysis_queue=MagicMock(),
        cfg=cfg,
        registry=_image_registry(),
        library_dir=None,
    )
    asset = MagicMock(id=304, path="x.png")
    p._persist_image_payload(asset, {"category": "character", "description": "x"})

    store_mock.update_asset_kind.assert_not_called()
    store_mock.save_sprite_meta.assert_not_called()  # library_dir 없으면 meta 도 skip
    store_mock.save_asset_labels.assert_called_once()
