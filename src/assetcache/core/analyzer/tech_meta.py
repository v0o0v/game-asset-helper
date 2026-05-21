"""Free functions for computing per-asset technical metadata.

Extracted from SpriteAnalyzer / SoundAnalyzer so the batch poller can
fill the same ``sprite_meta`` / ``sound_meta`` columns without depending
on the LLM-bound sync analyzer.

* :func:`compute_sprite_meta` — Pillow + numpy: width / height / alpha /
  pixel-art heuristic / 5 dominant colors.  Returns a fresh
  :class:`SpriteMeta` with ``frame_*``/``animation_*`` left as ``None``
  (those are populated separately by the spritesheet analyzer).
* :func:`compute_sound_meta` — librosa + soundfile: duration / sample
  rate / channels / loudness / BPM.  Optionally merges in payload-derived
  fields (category / loopable / tempo / etc.) so callers get a complete
  :class:`SoundMeta` in one call.

These helpers are pure I/O + numeric — no logging, no state.  Callers
wrap them in try/except where graceful degradation matters (e.g., batch
poller skips meta if the file is unreadable).
"""

from __future__ import annotations

import math
from pathlib import Path

from ..store import SoundMeta, SpriteMeta


# === Image (sprite) ====================================================


def compute_sprite_meta(abs_path: Path) -> SpriteMeta:
    """Open ``abs_path`` and compute the basic sprite tech meta.

    Returns a :class:`SpriteMeta` with frame/animation fields set to
    ``None`` — those belong to the spritesheet analyzer's domain.
    """
    import numpy as np
    from PIL import Image

    img = Image.open(abs_path)
    width, height = img.size
    has_alpha = _has_alpha(img)
    rgb = img.convert("RGB")
    arr = np.asarray(rgb, dtype=np.uint8)
    is_pixel_art = _is_pixel_art(arr)
    dominant = _dominant_colors(arr, k=5)
    return SpriteMeta(
        width=width, height=height,
        has_alpha=has_alpha, is_pixel_art=is_pixel_art,
        dominant_colors=dominant,
    )


def _has_alpha(img) -> bool:
    if img.mode in ("RGBA", "LA"):
        return True
    return img.info.get("transparency") is not None


def _is_pixel_art(arr) -> bool:
    """Heuristic: very few unique colors AND low neighbour variance.

    Very low color counts (≤ 16) skip the variance check entirely —
    a 4-colour 32×32 sprite is unmistakably pixel art even when the
    randomly-placed palette produces high inter-pixel differences.
    """
    import numpy as np

    h, w, _ = arr.shape
    step = max(1, max(h, w) // 64)
    sampled = arr[::step, ::step]
    flat = sampled.reshape(-1, 3)
    packed = (flat[:, 0].astype(np.int64) * 65536
              + flat[:, 1].astype(np.int64) * 256
              + flat[:, 2].astype(np.int64))
    unique_colors = len(np.unique(packed))
    if unique_colors <= 16:
        return True
    if unique_colors > 96:
        return False
    d = np.abs(np.diff(sampled.astype(np.int16), axis=1)).mean()
    return d < 60.0


def _dominant_colors(arr, *, k: int = 5) -> list[str]:
    """Tiny k-means++ on a downsampled image — returns hex colors."""
    import numpy as np

    h, w, _ = arr.shape
    step = max(1, max(h, w) // 96)
    flat = arr[::step, ::step].reshape(-1, 3).astype(np.float32)
    if len(flat) <= k:
        unique = np.unique(flat, axis=0)
        picks = unique[:k]
        return [_rgb_to_hex(c) for c in picks] + [
            "#000000"
        ] * (k - len(picks))

    rng = np.random.default_rng(seed=0)
    centers = [flat[rng.integers(0, len(flat))]]
    for _ in range(k - 1):
        dists = np.min(
            np.linalg.norm(flat[:, None, :] - np.stack(centers)[None],
                           axis=2),
            axis=1,
        )
        total = float(dists.sum())
        if total <= 0:
            centers.append(flat[rng.integers(0, len(flat))])
            continue
        probs = (dists.astype(np.float64) / total)
        probs = probs / probs.sum()
        idx = int(rng.choice(len(flat), p=probs))
        centers.append(flat[idx])
    c = np.stack(centers)
    for _ in range(8):
        d = np.linalg.norm(flat[:, None, :] - c[None], axis=2)
        assign = d.argmin(axis=1)
        for ki in range(k):
            pts = flat[assign == ki]
            if len(pts) > 0:
                c[ki] = pts.mean(axis=0)
    return [_rgb_to_hex(ci) for ci in c]


def _rgb_to_hex(c) -> str:
    r, g, b = (int(max(0, min(255, x))) for x in c)
    return f"#{r:02x}{g:02x}{b:02x}"


# === Audio (sound) ====================================================


def compute_sound_meta(
    abs_path: Path,
    *,
    payload: dict | None = None,
    audio_path_used: str = "batch",
) -> SoundMeta:
    """Compute sound tech meta + merge optional payload-derived fields.

    Tech fields (``duration_ms``, ``sample_rate``, ``channels``,
    ``loudness_db``, ``bpm``) come from soundfile + librosa.  Payload
    fields (``category``, ``loopable``, ``instruments``, ``tempo``,
    ``intensity``, ``genre``, ``voice_type``) come from ``payload`` when
    provided — otherwise they stay ``None``/empty.

    ``audio_path_used`` is the provenance tag stored alongside the meta;
    sync analyzer passes ``native``/``spectrogram``/``heuristic`` while
    the batch poller defaults to ``batch``.
    """
    import librosa
    import soundfile as sf

    info = sf.info(str(abs_path))
    channels = int(info.channels)
    sr_native = int(info.samplerate)

    samples_mono, _ = librosa.load(str(abs_path), sr=16000, mono=True)
    duration_ms = int(len(samples_mono) / 16000 * 1000)
    rms = float(((samples_mono ** 2).mean()) ** 0.5)
    loudness_db = 20.0 * math.log10(max(rms, 1e-9))
    try:
        bpm, _ = librosa.beat.beat_track(y=samples_mono, sr=16000)
        bpm_val: float | None = float(bpm) if bpm > 0 else None
    except Exception:
        bpm_val = None

    p = payload or {}
    instruments = p.get("instruments")
    return SoundMeta(
        duration_ms=duration_ms,
        sample_rate=sr_native,
        channels=channels,
        loudness_db=loudness_db,
        bpm=bpm_val,
        category=p.get("category"),
        loopable=p.get("loopable"),
        instruments=instruments or None,
        tempo=p.get("tempo"),
        intensity=p.get("intensity"),
        genre=p.get("genre"),
        voice_type=p.get("voice_type"),
        audio_path_used=audio_path_used,
    )
