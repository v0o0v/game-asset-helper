"""Batch poller — sprite_meta / sound_meta filling via tech_meta helpers.

Patch (post-v0.2.1, second commit): when ``library_dir`` is injected,
BatchPoller computes the same SpriteMeta / SoundMeta as the sync
analyzer path and saves them to the DB.  ``library_dir=None`` still
works (legacy stub behaviour) — covered in test_batch_poller.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

from assetcache.core.batch.poller import BatchPoller
from assetcache.core.store import SoundMeta, SpriteMeta


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
        "mood": ["heroic"],
        "palette": ["warm"],
        "animation": ["idle"],
    })


def _audio_registry() -> _StubRegistry:
    return _StubRegistry({
        "sound_category": ["sfx", "bgm", "voice"],
        "sound_mood": ["calm"],
        "sound_timbre": [],
        "sound_environment": [],
        "sound_instrument": ["piano"],
        "sound_use": [],
        "sound_tempo": ["slow", "medium"],
        "sound_intensity": ["soft"],
        "sound_genre": ["orchestral"],
        "sound_voice_type": ["male"],
    })


def _make_poller(*, registry, library_dir: Path | None):
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
        library_dir=library_dir,
    ), store


def _write_png(library: Path, rel: str, *, size=(32, 32), fill=(100, 50, 50)) -> None:
    p = library / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, fill).save(p)


def _write_wav(library: Path, rel: str, *, sr=16000, seconds=0.5) -> None:
    import soundfile as sf
    p = library / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0.0, seconds, int(sr * seconds), endpoint=False)
    samples = (0.5 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    sf.write(p, samples, sr, subtype="PCM_16")


# === sprite ============================================================


def test_persist_image_payload_with_library_dir_saves_sprite_meta(tmp_path):
    _write_png(tmp_path, "pack/hero.png", size=(48, 16))
    p, store = _make_poller(registry=_image_registry(), library_dir=tmp_path)
    asset = MagicMock(id=100, path="pack/hero.png")
    payload = {
        "category": "character", "style": "pixel_art",
        "mood": ["heroic"], "palette": ["warm"], "animation_hint": ["idle"],
        "description": "Hero",
    }
    p._persist_image_payload(asset, payload)

    store.save_sprite_meta.assert_called_once()
    aid, meta = store.save_sprite_meta.call_args.args
    assert aid == 100
    assert isinstance(meta, SpriteMeta)
    assert meta.width == 48 and meta.height == 16
    # FTS 에 width/height 토큰이 포함돼야
    _, fts_text = store.update_fts.call_args.args
    assert "width:48" in fts_text
    assert "height:16" in fts_text


def test_persist_image_payload_skips_meta_when_file_missing(tmp_path):
    # 파일을 만들지 않음 → meta 계산 fail → graceful skip
    p, store = _make_poller(registry=_image_registry(), library_dir=tmp_path)
    asset = MagicMock(id=101, path="missing/sprite.png")
    payload = {"category": "character", "style": "pixel_art", "description": "x"}
    p._persist_image_payload(asset, payload)

    # meta 저장은 호출 안 됨
    store.save_sprite_meta.assert_not_called()
    # 그래도 labels 와 FTS, state 는 정상 저장
    store.save_asset_labels.assert_called_once()
    store.update_fts.assert_called_once()
    store.mark_asset_state.assert_called_once()
    assert store.mark_asset_state.call_args.args[:2] == (101, "ok")


def test_persist_image_payload_without_library_dir_skips_meta(tmp_path):
    _write_png(tmp_path, "pack/x.png")  # 파일은 있지만 library_dir 미주입
    p, store = _make_poller(registry=_image_registry(), library_dir=None)
    asset = MagicMock(id=102, path="pack/x.png")
    payload = {"category": "character", "style": "pixel_art", "description": "x"}
    p._persist_image_payload(asset, payload)

    store.save_sprite_meta.assert_not_called()
    # labels / FTS 는 여전히 저장
    store.save_asset_labels.assert_called_once()


# === sound =============================================================


def test_persist_audio_payload_with_library_dir_saves_sound_meta(tmp_path):
    _write_wav(tmp_path, "bgm/menu.wav", sr=22050, seconds=1.0)
    p, store = _make_poller(registry=_audio_registry(), library_dir=tmp_path)
    asset = MagicMock(id=200, path="bgm/menu.wav")
    payload = {
        "category": "bgm", "mood": ["calm"], "instruments": ["piano"],
        "tempo": "slow", "intensity": "soft", "loopable": True,
        "genre": "orchestral",
        "description": "Menu BGM",
    }
    p._persist_audio_payload(asset, payload)

    store.save_sound_meta.assert_called_once()
    aid, meta = store.save_sound_meta.call_args.args
    assert aid == 200
    assert isinstance(meta, SoundMeta)
    assert meta.duration_ms == 1000
    assert meta.sample_rate == 22050
    assert meta.channels == 1
    assert meta.category == "bgm"
    assert meta.loopable is True
    assert meta.tempo == "slow"
    assert meta.audio_path_used == "batch"
    # FTS 에 duration / tempo 토큰
    _, fts_text = store.update_fts.call_args.args
    assert "duration_ms:1000" in fts_text
    assert "tempo:slow" in fts_text


def test_persist_audio_payload_skips_meta_when_file_corrupt(tmp_path):
    # 빈 파일 (soundfile/librosa 가 실패) → graceful skip
    p_corrupt = tmp_path / "bad.wav"
    p_corrupt.write_bytes(b"")
    p, store = _make_poller(registry=_audio_registry(), library_dir=tmp_path)
    asset = MagicMock(id=201, path="bad.wav")
    payload = {"category": "sfx", "description": "broken"}
    p._persist_audio_payload(asset, payload)

    store.save_sound_meta.assert_not_called()
    store.save_asset_labels.assert_called_once()
    store.mark_asset_state.assert_called_once()
    assert store.mark_asset_state.call_args.args[:2] == (201, "ok")


def test_persist_audio_payload_without_library_dir_skips_meta(tmp_path):
    _write_wav(tmp_path, "x.wav")
    p, store = _make_poller(registry=_audio_registry(), library_dir=None)
    asset = MagicMock(id=202, path="x.wav")
    payload = {"category": "sfx", "description": "x"}
    p._persist_audio_payload(asset, payload)

    store.save_sound_meta.assert_not_called()
    store.save_asset_labels.assert_called_once()
