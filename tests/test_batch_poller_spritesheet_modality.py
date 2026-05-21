"""M11.2 — BatchPoller 의 chat_spritesheet handler.

_persist_spritesheet_payload 가 sync SpritesheetAnalyzer 와 동등한 결과
(category/style/mood/palette + animation_hint 라벨 + sprite_meta enrich +
kind='spritesheet' 보존) 를 DB 에 저장하는지.
"""

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
    def __init__(self, axis_labels):
        self._axis_labels = axis_labels

    def list_labels(self, axis=None, *, enabled_only=True, with_description=False):
        labels = self._axis_labels.get(axis, []) if axis else []
        if with_description:
            return [_LabelRow(label=l) for l in labels]
        return labels


def _registry():
    return _StubRegistry({
        "category": ["character", "other"],
        "style": ["pixel_art", "other"],
        "mood": ["calm"],
        "palette": ["vibrant"],
        "animation": ["idle", "walk", "run", "attack"],
    })


def _make_poller(library_dir: Path):
    store = MagicMock()
    store.list_active_batch_jobs.return_value = []
    cfg = MagicMock()
    cfg.batch.poll_interval_seconds = 0.05
    return BatchPoller(
        store=store, chain_registry=MagicMock(), analysis_queue=MagicMock(),
        cfg=cfg, registry=_registry(), library_dir=library_dir,
    ), store


def _aseprite_sheet(library: Path, base: str, *, count, tags):
    fw, fh = 32, 32
    img = Image.new("RGBA", (fw * count, fh), (200, 50, 50, 255))
    p = library / f"{base}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)
    frames = {
        f"f_{i}": {
            "frame": {"x": i * fw, "y": 0, "w": fw, "h": fh},
            "duration": 83,
        }
        for i in range(count)
    }
    frame_tags = [
        {"name": n, "from": s, "to": e, "direction": "forward"}
        for n, s, e in tags
    ]
    (library / f"{base}.json").write_text(
        json.dumps({"frames": frames, "meta": {"frameTags": frame_tags}}),
        encoding="utf-8",
    )


def test_persist_spritesheet_payload_validates_and_emits_animation_labels(tmp_path):
    """payload 의 animation_hint + frameTags 모두 라벨로 등록."""
    _aseprite_sheet(tmp_path, "pack/hero", count=4, tags=[("idle", 0, 3)])
    p, store = _make_poller(tmp_path)
    asset = MagicMock(id=1, path="pack/hero.png")
    payload = {
        "category": "character",
        "style": "pixel_art",
        "mood": [],
        "palette": [],
        "animation_hint": ["walk", "run"],
        "description": "Hero animation",
        "confidence": 0.85,
    }
    p._persist_spritesheet_payload(asset, payload)

    saved_labels = store.save_asset_labels.call_args.args[1]
    anim = {l.label for l in saved_labels if l.axis == "animation"}
    # Gemma 추측 (walk/run) + frameTags (idle)
    assert anim == {"walk", "run", "idle"}
    # category/style 도 등록
    cat = [l for l in saved_labels if l.axis == "category"]
    assert cat and cat[0].label == "character"


def test_persist_spritesheet_payload_enriches_sprite_meta(tmp_path):
    """sprite_meta 에 frame_w/h/count + animations_json 채워야."""
    _aseprite_sheet(tmp_path, "pack/x", count=4, tags=[("walk", 0, 3)])
    p, store = _make_poller(tmp_path)
    asset = MagicMock(id=2, path="pack/x.png")
    payload = {
        "category": "character", "style": "pixel_art",
        "animation_hint": ["walk"], "description": "x", "confidence": 0.9,
    }
    p._persist_spritesheet_payload(asset, payload)

    store.save_sprite_meta.assert_called_once()
    _, meta = store.save_sprite_meta.call_args.args
    assert meta.frame_w == 32 and meta.frame_h == 32
    assert meta.frame_count == 4
    assert meta.animations_json == {
        "walk": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "json_tag"},
    }


def test_persist_spritesheet_payload_keeps_kind_spritesheet(tmp_path):
    """이미 promoted 된 kind 는 그대로 유지 (재호출 noop)."""
    _aseprite_sheet(tmp_path, "pack/k", count=2, tags=[("idle", 0, 1)])
    p, store = _make_poller(tmp_path)
    asset = MagicMock(id=3, path="pack/k.png")
    p._persist_spritesheet_payload(asset, {
        "category": "character", "style": "pixel_art",
        "animation_hint": ["idle"], "description": "k", "confidence": 1.0,
    })
    # update_asset_kind 는 호출돼도 'spritesheet' 로 — idempotent
    if store.update_asset_kind.called:
        for c in store.update_asset_kind.call_args_list:
            assert c.args[1] == "spritesheet"


def test_persist_spritesheet_payload_fts_includes_animation_tokens(tmp_path):
    """FTS 에 animation:idle 등 토큰 포함."""
    _aseprite_sheet(tmp_path, "pack/a", count=4, tags=[("idle", 0, 3)])
    p, store = _make_poller(tmp_path)
    asset = MagicMock(id=4, path="pack/a.png")
    p._persist_spritesheet_payload(asset, {
        "category": "character", "style": "pixel_art",
        "animation_hint": ["idle"], "description": "a", "confidence": 0.5,
    })
    _, fts_text = store.update_fts.call_args.args
    assert "animation:idle" in fts_text


def test_persist_spritesheet_payload_handles_invalid_animation_hint_gracefully(tmp_path):
    """animation_hint 가 enum 밖이면 demote, frameTags 만 남음."""
    _aseprite_sheet(tmp_path, "pack/b", count=2, tags=[("walk", 0, 1)])
    p, store = _make_poller(tmp_path)
    asset = MagicMock(id=5, path="pack/b.png")
    p._persist_spritesheet_payload(asset, {
        "category": "character", "style": "pixel_art",
        "animation_hint": ["bogus_label", "walk"], "description": "b", "confidence": 0.5,
    })
    saved_labels = store.save_asset_labels.call_args.args[1]
    anim = {l.label for l in saved_labels if l.axis == "animation"}
    assert "walk" in anim  # frameTags + validated payload
    assert "bogus_label" not in anim


def test_persist_spritesheet_payload_grid_only_sheet_still_gets_gemma_anim_labels(tmp_path):
    """JSON 사이드카 없는 grid-only 시트도 Gemma 의 animation_hint 추측을 라벨로 보존.

    M11.2 의 핵심 가치 — PR #18 한계 해소.
    """
    fw, fh = 32, 32
    img = Image.new("RGBA", (fw * 4, fh), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    for i in range(4):
        draw.rectangle(
            [i * fw + 4, 4, i * fw + fw - 4, fh - 4],
            fill=(255 - 50 * i, 50, 50, 255),
        )
    p_path = tmp_path / "pack/grid.png"
    p_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(p_path)

    p, store = _make_poller(tmp_path)
    asset = MagicMock(id=6, path="pack/grid.png")
    p._persist_spritesheet_payload(asset, {
        "category": "character", "style": "pixel_art",
        "animation_hint": ["run"], "description": "grid", "confidence": 0.7,
    })
    saved_labels = store.save_asset_labels.call_args.args[1]
    anim = {l.label for l in saved_labels if l.axis == "animation"}
    # grid-only 라 frameTags 는 비어 있지만 Gemma 의 'run' 은 살아남아야
    assert "run" in anim


def test_handle_succeeded_dispatches_chat_spritesheet_to_persist(tmp_path):
    """_handle_succeeded 의 modality switch 에 chat_spritesheet 분기 존재."""
    _aseprite_sheet(tmp_path, "pack/h", count=2, tags=[("idle", 0, 1)])
    p, store = _make_poller(tmp_path)

    asset = MagicMock(id=10, path="pack/h.png")
    store.list_assets_in_batch.return_value = [asset]
    job = MagicMock()
    job.id = 999
    job.modality = "chat_spritesheet"

    resp = MagicMock()
    resp.error = None
    resp.response.text = json.dumps({
        "category": "character", "style": "pixel_art",
        "animation_hint": ["idle"], "description": "h", "confidence": 0.5,
    })

    status = MagicMock()
    status.inlined_responses = [resp]
    status.file_name = None

    p._handle_succeeded(job, status, MagicMock())

    # backend_used 에 image 로 마킹
    store.mark_asset_backends.assert_called_with(10, image="gemini")
    # sprite_meta 저장됨 → spritesheet handler 분기 작동 확인
    store.save_sprite_meta.assert_called_once()
