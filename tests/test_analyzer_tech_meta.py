"""Unit tests for analyzer.tech_meta — shared sprite/sound meta helpers.

These free functions back both the sync analyzer path and the batch
poller path, so the contract here is the single source of truth for
on-disk asset → SpriteMeta/SoundMeta.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from assetcache.core.analyzer.tech_meta import (
    _is_pixel_art,
    compute_sound_meta,
    compute_sprite_meta,
)
from assetcache.core.store import SoundMeta, SpriteMeta


# === Sprite ============================================================


def _save_png(path: Path, *, size: tuple[int, int], mode: str, fill) -> Path:
    img = Image.new(mode, size, fill)
    img.save(path)
    return path


def test_compute_sprite_meta_basic_rgb(tmp_path):
    p = _save_png(tmp_path / "a.png", size=(64, 32), mode="RGB", fill=(120, 30, 30))
    meta = compute_sprite_meta(p)
    assert isinstance(meta, SpriteMeta)
    assert meta.width == 64 and meta.height == 32
    assert meta.has_alpha is False
    assert len(meta.dominant_colors) == 5
    assert all(c.startswith("#") and len(c) == 7 for c in meta.dominant_colors)
    # spritesheet 전용 필드는 비어 있어야
    assert meta.frame_w is None
    assert meta.frame_h is None
    assert meta.frame_count is None
    assert meta.animation_tags is None


def test_compute_sprite_meta_rgba_alpha(tmp_path):
    p = _save_png(tmp_path / "alpha.png", size=(16, 16), mode="RGBA",
                  fill=(0, 0, 0, 0))
    meta = compute_sprite_meta(p)
    assert meta.has_alpha is True


def test_compute_sprite_meta_pixel_art_low_color_count(tmp_path):
    """4-색 32x32 = unmistakably pixel art (variance check 우회 분기)."""
    arr = np.zeros((32, 32, 3), dtype=np.uint8)
    arr[:16, :16] = (255, 0, 0)
    arr[:16, 16:] = (0, 255, 0)
    arr[16:, :16] = (0, 0, 255)
    arr[16:, 16:] = (255, 255, 0)
    p = tmp_path / "pixel.png"
    Image.fromarray(arr, mode="RGB").save(p)
    meta = compute_sprite_meta(p)
    assert meta.is_pixel_art is True


def test_compute_sprite_meta_photo_not_pixel_art(tmp_path):
    """64x64 random noise — 색상 매우 많음 (>96) → pixel art 아님."""
    rng = np.random.default_rng(seed=42)
    arr = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
    p = tmp_path / "noise.png"
    Image.fromarray(arr, mode="RGB").save(p)
    meta = compute_sprite_meta(p)
    assert meta.is_pixel_art is False


def test_is_pixel_art_unit_low_palette():
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    arr[..., 0] = 200  # 단색
    assert _is_pixel_art(arr) is True


def test_compute_sprite_meta_dominant_colors_deterministic(tmp_path):
    """같은 입력 → 같은 색 (seed=0 보장)."""
    arr = np.zeros((48, 48, 3), dtype=np.uint8)
    arr[:24] = (200, 50, 50)
    arr[24:] = (50, 50, 200)
    p = tmp_path / "two.png"
    Image.fromarray(arr, mode="RGB").save(p)
    m1 = compute_sprite_meta(p)
    m2 = compute_sprite_meta(p)
    assert m1.dominant_colors == m2.dominant_colors


# === Sound =============================================================


def _save_wav(path: Path, *, sr: int, samples) -> Path:
    import soundfile as sf
    sf.write(path, samples, sr, subtype="PCM_16")
    return path


def _sine(sr: int, freq: float, seconds: float) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(sr * seconds), endpoint=False)
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_compute_sound_meta_basic_mono(tmp_path):
    p = _save_wav(tmp_path / "sine.wav", sr=22050, samples=_sine(22050, 440.0, 1.0))
    meta = compute_sound_meta(p)
    assert isinstance(meta, SoundMeta)
    assert meta.duration_ms == 1000
    assert meta.sample_rate == 22050
    assert meta.channels == 1
    # 진폭 0.5 → loudness_db ≈ -6dB 근처. 정확값 X, 음수 sane range 만 검증.
    assert meta.loudness_db is not None
    assert -60.0 < meta.loudness_db < 0.0
    # default audio_path_used
    assert meta.audio_path_used == "batch"
    # payload 미전달 → payload 필드 모두 None/empty
    assert meta.category is None
    assert meta.loopable is None
    assert meta.instruments is None
    assert meta.tempo is None
    assert meta.genre is None
    assert meta.voice_type is None


def test_compute_sound_meta_stereo_channels(tmp_path):
    import soundfile as sf
    sr = 16000
    mono = _sine(sr, 220.0, 0.5)
    stereo = np.stack([mono, mono], axis=1)
    p = tmp_path / "stereo.wav"
    sf.write(p, stereo, sr, subtype="PCM_16")
    meta = compute_sound_meta(p)
    assert meta.channels == 2
    assert meta.sample_rate == sr
    # librosa.load mono=True 로 다운믹스 → duration 동일
    assert 450 < meta.duration_ms < 550


def test_compute_sound_meta_payload_merged(tmp_path):
    p = _save_wav(tmp_path / "bgm.wav", sr=16000, samples=_sine(16000, 110.0, 0.3))
    payload = {
        "category": "bgm",
        "loopable": True,
        "instruments": ["piano", "drums"],
        "tempo": "slow",
        "intensity": "soft",
        "genre": "orchestral",
        "voice_type": None,
    }
    meta = compute_sound_meta(p, payload=payload, audio_path_used="batch")
    assert meta.category == "bgm"
    assert meta.loopable is True
    assert meta.instruments == ["piano", "drums"]
    assert meta.tempo == "slow"
    assert meta.intensity == "soft"
    assert meta.genre == "orchestral"
    assert meta.voice_type is None
    assert meta.audio_path_used == "batch"


def test_compute_sound_meta_empty_instruments_becomes_none(tmp_path):
    """[] 빈 리스트는 None 으로 정규화 (sync 동작과 동일)."""
    p = _save_wav(tmp_path / "x.wav", sr=16000, samples=_sine(16000, 440.0, 0.2))
    meta = compute_sound_meta(p, payload={"instruments": []})
    assert meta.instruments is None


def test_compute_sound_meta_audio_path_used_custom(tmp_path):
    p = _save_wav(tmp_path / "y.wav", sr=16000, samples=_sine(16000, 440.0, 0.2))
    meta = compute_sound_meta(p, audio_path_used="native")
    assert meta.audio_path_used == "native"
