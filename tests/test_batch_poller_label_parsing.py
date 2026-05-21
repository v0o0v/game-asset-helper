"""Batch poller — real Gemini batch result → labels persisting.

Patch A (post-M11.1): BatchPoller now uses the shared payload_parser to
convert Gemini batch JSON into LabelScore lists, save them to the DB and
update assets_fts.

These tests exercise the registry-injected path; the legacy stub path
(``registry=None``) is still covered by the original test_batch_poller.py
fixture.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.poller import BatchPoller
from assetcache.core.batch.types import GeminiBatchStatus


@dataclass(frozen=True)
class _LabelRow:
    label: str
    description: str | None = None


class _StubRegistry:
    """In-memory LabelRegistry stand-in for poller tests."""

    def __init__(
        self,
        axis_labels: dict[str, list[str]],
        descriptions: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self._axis_labels = axis_labels
        self._descriptions = descriptions or {}

    def list_labels(
        self,
        axis: str | None = None,
        *,
        enabled_only: bool = True,
        with_description: bool = False,
    ):
        labels = self._axis_labels.get(axis, []) if axis else []
        if with_description:
            return [
                _LabelRow(
                    label=l,
                    description=self._descriptions.get((axis, l)),
                )
                for l in labels
            ]
        return labels


def _image_registry() -> _StubRegistry:
    return _StubRegistry({
        "category": ["character", "tile", "ui", "other"],
        "style": ["pixel_art", "cartoon", "other"],
        "mood": ["heroic", "dark"],
        "palette": ["warm", "cool"],
        "animation": ["idle", "walk"],
    }, descriptions={
        ("category", "character"): "protagonist sprite",
        ("style", "pixel_art"): "low-res grid",
    })


def _audio_registry() -> _StubRegistry:
    return _StubRegistry({
        "sound_category": ["sfx", "bgm", "voice", "ui_sound"],
        "sound_mood": ["calm", "tense"],
        "sound_timbre": ["bright", "warm"],
        "sound_environment": ["indoor"],
        "sound_instrument": ["piano", "drums"],
        "sound_use": ["loop"],
        "sound_tempo": ["slow", "fast"],
        "sound_intensity": ["soft", "loud"],
        "sound_genre": ["orchestral"],
        "sound_voice_type": ["male", "female"],
    })


def _make_poller(*, registry):
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
        registry=registry,
    ), store


# === image (chat_image) ================================================


def test_persist_image_payload_saves_validated_labels():
    p, store = _make_poller(registry=_image_registry())
    asset = MagicMock(id=10, path="kenney/hero_idle.png")
    payload = {
        "category": "character", "style": "pixel_art",
        "mood": ["heroic"], "palette": ["warm"],
        "animation_hint": ["idle"],
        "description": "Hero idle pose", "confidence": 0.8,
    }
    p._persist_image_payload(asset, payload)

    store.save_asset_labels.assert_called_once()
    args = store.save_asset_labels.call_args.args
    assert args[0] == 10
    labels = args[1]
    label_pairs = {(l.axis, l.label) for l in labels}
    assert ("category", "character") in label_pairs
    assert ("style", "pixel_art") in label_pairs
    assert ("mood", "heroic") in label_pairs
    assert ("palette", "warm") in label_pairs
    assert ("animation", "idle") in label_pairs


def test_persist_image_payload_demotes_invalid_to_other():
    p, store = _make_poller(registry=_image_registry())
    asset = MagicMock(id=11, path="random/asset.png")
    payload = {
        "category": "spaceship",   # not in whitelist
        "style": "watercolor",     # not in whitelist
        "mood": ["epic"],          # not in whitelist
        "description": "Some asset",
    }
    p._persist_image_payload(asset, payload)

    labels = store.save_asset_labels.call_args.args[1]
    by_axis = {l.axis: l.label for l in labels if l.axis in ("category", "style")}
    # both demoted to "other" since both fallbacks present
    assert by_axis["category"] == "other"
    assert by_axis["style"] == "other"
    # invalid mood dropped entirely
    assert all(l.axis != "mood" for l in labels)
    # state still 'ok' (partial labels but recoverable for search)
    store.mark_asset_state.assert_called_once()
    call = store.mark_asset_state.call_args
    assert call.args[0] == 11
    assert call.args[1] == "ok"


def test_persist_image_payload_updates_fts_with_path_and_labels():
    p, store = _make_poller(registry=_image_registry())
    asset = MagicMock(id=12, path="kenney/hero_walk.png")
    payload = {
        "category": "character", "style": "pixel_art",
        "mood": ["heroic"], "palette": [], "animation_hint": [],
        "description": "Walking hero",
    }
    p._persist_image_payload(asset, payload)

    store.update_fts.assert_called_once()
    asset_id, text = store.update_fts.call_args.args
    assert asset_id == 12
    # path is tokenized as `path:...` and segments are emitted as bare tokens
    assert "path:kenney/hero_walk.png" in text
    assert "kenney" in text
    assert "hero_walk.png" in text
    # label tokens emitted in FTS
    assert "category:character" in text
    assert "label:character" in text
    # description appended verbatim
    assert "Walking hero" in text
    # label description ('protagonist sprite') joined as quoted segment
    assert "protagonist sprite" in text


def test_persist_image_payload_without_registry_uses_legacy_stub():
    p, store = _make_poller(registry=None)
    asset = MagicMock(id=20, path="x.png")
    p._persist_image_payload(asset, {"category": "anything"})
    # legacy path saves empty labels, no FTS update
    store.save_asset_labels.assert_called_once_with(20, [])
    store.update_fts.assert_not_called()
    store.mark_asset_state.assert_called_once()
    assert store.mark_asset_state.call_args.args[:2] == (20, "ok")


# === audio (chat_audio) ================================================


def test_persist_audio_payload_saves_validated_labels():
    p, store = _make_poller(registry=_audio_registry())
    asset = MagicMock(id=30, path="bgm/forest.ogg")
    payload = {
        "category": "bgm",
        "mood": ["calm"], "timbre": ["warm"], "environment": [],
        "instruments": ["piano"], "use": ["loop"],
        "tempo": "slow", "intensity": "soft",
        "genre": "orchestral", "voice_type": None,
        "loopable": True, "description": "Calm forest BGM",
        "confidence": 0.9,
    }
    p._persist_audio_payload(asset, payload)

    labels = store.save_asset_labels.call_args.args[1]
    pairs = {(l.axis, l.label) for l in labels}
    assert ("sound_category", "bgm") in pairs
    assert ("sound_mood", "calm") in pairs
    assert ("sound_timbre", "warm") in pairs
    assert ("sound_instrument", "piano") in pairs
    assert ("sound_tempo", "slow") in pairs
    assert ("sound_genre", "orchestral") in pairs


def test_persist_audio_payload_demotes_invalid_category_to_sfx():
    p, store = _make_poller(registry=_audio_registry())
    asset = MagicMock(id=31, path="fx/explosion.wav")
    payload = {
        "category": "explosion",  # not in whitelist
        "mood": [], "instruments": [],
        "description": "Big boom",
    }
    p._persist_audio_payload(asset, payload)
    labels = store.save_asset_labels.call_args.args[1]
    cats = [l.label for l in labels if l.axis == "sound_category"]
    assert cats == ["sfx"]
    store.mark_asset_state.assert_called_once()
    assert store.mark_asset_state.call_args.args[:2] == (31, "ok")


def test_persist_audio_payload_genre_nulled_when_category_not_music():
    p, store = _make_poller(registry=_audio_registry())
    asset = MagicMock(id=32, path="fx/swoosh.wav")
    payload = {
        "category": "sfx",
        "genre": "orchestral",  # disallowed for non-music category
    }
    p._persist_audio_payload(asset, payload)
    labels = store.save_asset_labels.call_args.args[1]
    # genre is nulled by validator → no genre label emitted
    assert all(l.axis != "sound_genre" for l in labels)


def test_persist_audio_payload_updates_fts():
    p, store = _make_poller(registry=_audio_registry())
    asset = MagicMock(id=33, path="bgm/menu.ogg")
    payload = {
        "category": "bgm", "mood": ["calm"], "instruments": ["piano"],
        "description": "Menu theme",
    }
    p._persist_audio_payload(asset, payload)
    store.update_fts.assert_called_once()
    _, text = store.update_fts.call_args.args
    assert "sound_category:bgm" in text
    assert "Menu theme" in text


# === end-to-end through _handle_succeeded ==============================


def test_handle_succeeded_image_with_registry_passes_asset_object():
    """When the registry is wired up, _handle_succeeded passes the AssetRow
    (not just asset_id) so that _persist_image_payload can read .path."""
    p, store = _make_poller(registry=_image_registry())
    asset = MagicMock(id=40, path="dir/sprite.png")
    store.list_assets_in_batch.return_value = [asset]
    resp = MagicMock()
    resp.response.text = (
        '{"category": "character", "style": "pixel_art",'
        ' "mood": ["heroic"], "palette": ["warm"], "animation_hint": ["idle"],'
        ' "description": "test"}'
    )
    resp.error = None
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=[resp],
        file_name=None, error=None,
    )
    job = MagicMock(id=100, modality="chat_image", asset_count=1)
    p._handle_succeeded(job, status, MagicMock())

    # validated labels saved (not empty)
    saved_labels = store.save_asset_labels.call_args.args[1]
    assert len(saved_labels) > 0
    # FTS row updated with path
    store.update_fts.assert_called_once()
    assert store.update_fts.call_args.args[0] == 40
    # marked complete + backend gemini
    store.mark_asset_backends.assert_called_with(40, image="gemini")
    completed = [
        c for c in store.mark_asset_batch_state.call_args_list
        if c.args[1] == "completed"
    ]
    assert (40, "completed") in [tuple(c.args) for c in completed]


def test_handle_succeeded_audio_with_registry_saves_labels():
    p, store = _make_poller(registry=_audio_registry())
    asset = MagicMock(id=50, path="bgm/x.ogg")
    store.list_assets_in_batch.return_value = [asset]
    resp = MagicMock()
    resp.response.text = (
        '{"category": "bgm", "mood": ["calm"], "instruments": ["piano"],'
        ' "description": "Calm bgm"}'
    )
    resp.error = None
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=[resp],
        file_name=None, error=None,
    )
    job = MagicMock(id=101, modality="chat_audio", asset_count=1)
    p._handle_succeeded(job, status, MagicMock())
    saved_labels = store.save_asset_labels.call_args.args[1]
    assert any(l.axis == "sound_category" for l in saved_labels)
    store.mark_asset_backends.assert_called_with(50, audio="gemini")
