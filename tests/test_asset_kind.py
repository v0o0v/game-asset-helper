"""Tests for gah.core.asset_kind — extension-based classification."""

from __future__ import annotations

from pathlib import Path


def test_png_jpg_webp_classified_as_sprite() -> None:
    from gah.core.asset_kind import classify

    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        assert classify(Path(f"hero{ext}")) == "sprite", ext


def test_wav_ogg_mp3_classified_as_sound() -> None:
    from gah.core.asset_kind import classify

    for ext in (".wav", ".ogg", ".mp3"):
        assert classify(Path(f"jump{ext}")) == "sound", ext


def test_unknown_extension_returns_none() -> None:
    from gah.core.asset_kind import classify

    assert classify(Path("readme.txt")) is None
    assert classify(Path("script.gd")) is None
    assert classify(Path("hero.meta")) is None
    assert classify(Path("no_extension")) is None


def test_case_insensitive_extension() -> None:
    from gah.core.asset_kind import classify

    assert classify(Path("HERO.PNG")) == "sprite"
    assert classify(Path("Jump.WAV")) == "sound"
    assert classify(Path("icon.WebP")) == "sprite"
