"""Unit tests for the shared payload parser (analyzer.payload_parser).

These functions back both the sync analyzer path and the batch poller
path, so the contract here is the single source of truth for
Gemma-payload → LabelScore conversion.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from assetcache.core.analyzer.payload_parser import (
    AUDIO_MULTI_AXES,
    AUDIO_SINGLE_AXES,
    audio_payload_to_labels,
    collect_label_descriptions,
    image_payload_to_labels,
    validate_audio_payload,
    validate_image_payload,
)
from assetcache.core.store import LabelScore


@dataclass(frozen=True)
class _LabelRow:
    """Minimal stand-in for ``store.LabelRow`` (only attrs we touch)."""

    label: str
    description: str | None = None


class _StubRegistry:
    """LabelRegistry replacement for unit tests — pure in-memory."""

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


# === Image (sprite) ====================================================


@pytest.fixture
def image_registry() -> _StubRegistry:
    return _StubRegistry({
        "category": ["character", "tile", "ui", "other"],
        "style": ["pixel_art", "cartoon", "other"],
        "mood": ["heroic", "dark", "playful"],
        "palette": ["warm", "cool", "monochrome"],
        "animation": ["idle", "walk", "run", "attack"],
    })


def test_validate_image_payload_pass(image_registry):
    payload = {
        "category": "character", "style": "pixel_art",
        "mood": ["heroic"], "palette": ["warm"],
        "animation_hint": ["idle", "walk"],
    }
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is True
    assert err is None
    assert fixed["category"] == "character"
    assert fixed["mood"] == ["heroic"]


def test_validate_image_payload_invalid_category_demoted(image_registry):
    payload = {"category": "spaceship", "style": "pixel_art"}
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is False
    assert "category=" in err
    # 'other' is in the registry → falls back to it
    assert fixed["category"] == "other"


def test_validate_image_payload_category_as_list_squashed(image_registry):
    payload = {"category": ["character"], "style": "pixel_art"}
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is False
    assert "category_was_list" in err
    assert fixed["category"] == "character"  # 첫 요소가 valid → 통과


def test_validate_image_payload_style_invalid_demoted(image_registry):
    payload = {"category": "tile", "style": "watercolor"}
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is False
    assert fixed["style"] == "other"


def test_validate_image_payload_mood_array_filtered(image_registry):
    payload = {
        "category": "character", "style": "cartoon",
        "mood": ["heroic", "epic", "dark"],  # 'epic' not in whitelist
    }
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is False
    assert fixed["mood"] == ["heroic", "dark"]


def test_validate_image_payload_mood_as_str_coerced(image_registry):
    payload = {
        "category": "character", "style": "cartoon",
        "mood": "heroic",  # str instead of list
    }
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is False
    assert "mood_not_list" in err
    assert fixed["mood"] == ["heroic"]


def test_validate_image_payload_no_other_fallback_picks_first():
    """category fallback when 'other' is not in the registry."""
    reg = _StubRegistry({
        "category": ["a", "b"],
        "style": ["x", "y"],
        "mood": [], "palette": [], "animation": [],
    })
    payload = {"category": "z", "style": "x"}
    ok, err, fixed = validate_image_payload(payload, reg)
    assert ok is False
    assert fixed["category"] in {"a", "b"}


def test_image_payload_to_labels_single_axes():
    payload = {
        "category": "character", "style": "pixel_art",
        "mood": [], "palette": [], "animation_hint": [],
        "confidence": 0.8,
    }
    labels = image_payload_to_labels(payload)
    by_axis = {(l.axis, l.label): l for l in labels}
    assert by_axis[("category", "character")].weight == "primary"
    assert by_axis[("category", "character")].score == pytest.approx(0.8)
    assert by_axis[("style", "pixel_art")].weight == "primary"
    assert all(l.source == "gemma" for l in labels)


def test_image_payload_to_labels_multi_axes_weights():
    payload = {
        "category": "character", "style": "cartoon",
        "mood": ["heroic", "playful", "dark", "epic"],  # 4개
        "palette": ["warm"],
        "animation_hint": [],
        "confidence": 0.6,
    }
    labels = image_payload_to_labels(payload)
    moods = [l for l in labels if l.axis == "mood"]
    assert [l.weight for l in moods] == ["primary", "secondary", "tertiary", "tertiary"]
    assert [l.label for l in moods] == ["heroic", "playful", "dark", "epic"]


def test_image_payload_to_labels_missing_confidence_uses_default():
    payload = {"category": "character"}
    labels = image_payload_to_labels(payload)
    assert labels[0].score == pytest.approx(0.5)


def test_image_payload_to_labels_skips_empty_values():
    payload = {
        "category": "", "style": None,
        "mood": ["", "heroic", None],
        "palette": [], "animation_hint": [],
    }
    labels = image_payload_to_labels(payload)
    assert [l.label for l in labels] == ["heroic"]


# === Audio (sound) ====================================================


@pytest.fixture
def audio_registry() -> _StubRegistry:
    return _StubRegistry({
        "sound_category": ["sfx", "bgm", "voice", "jingle", "ui_sound"],
        "sound_mood": ["calm", "tense", "playful"],
        "sound_timbre": ["bright", "warm"],
        "sound_environment": ["indoor", "outdoor"],
        "sound_instrument": ["piano", "drums", "guitar"],
        "sound_use": ["loop", "stinger"],
        "sound_tempo": ["slow", "medium", "fast"],
        "sound_intensity": ["soft", "medium", "loud"],
        "sound_genre": ["orchestral", "electronic", "jazz"],
        "sound_voice_type": ["male", "female", "child"],
    })


def test_validate_audio_payload_pass(audio_registry):
    payload = {
        "category": "sfx",
        "mood": ["tense"], "timbre": ["bright"], "environment": [],
        "instruments": ["piano"], "use": ["stinger"],
        "tempo": "fast", "intensity": "loud",
        "genre": None, "voice_type": None,
        "loopable": False, "confidence": 0.7,
    }
    ok, fixed, err = validate_audio_payload(payload, audio_registry)
    assert ok is True
    assert err is None
    assert fixed["category"] == "sfx"


def test_validate_audio_payload_invalid_category_demoted_to_sfx(audio_registry):
    payload = {"category": "explosion"}
    ok, fixed, err = validate_audio_payload(payload, audio_registry)
    assert ok is False
    assert fixed["category"] == "sfx"


def test_validate_audio_payload_genre_null_when_not_music(audio_registry):
    payload = {"category": "sfx", "genre": "orchestral"}
    ok, fixed, err = validate_audio_payload(payload, audio_registry)
    assert ok is False
    assert "genre when category=sfx" in err
    assert fixed["genre"] is None


def test_validate_audio_payload_genre_kept_when_music(audio_registry):
    payload = {"category": "bgm", "genre": "orchestral"}
    ok, fixed, err = validate_audio_payload(payload, audio_registry)
    # only category/genre/voice — tempo/intensity 미설정 → still ok
    assert ok is True
    assert fixed["genre"] == "orchestral"


def test_validate_audio_payload_voice_type_kept_when_voice(audio_registry):
    payload = {"category": "voice", "voice_type": "male"}
    ok, fixed, err = validate_audio_payload(payload, audio_registry)
    assert ok is True
    assert fixed["voice_type"] == "male"


def test_validate_audio_payload_voice_type_null_when_not_voice(audio_registry):
    payload = {"category": "sfx", "voice_type": "male"}
    ok, fixed, err = validate_audio_payload(payload, audio_registry)
    assert ok is False
    assert fixed["voice_type"] is None


def test_validate_audio_payload_multi_axes_filtered(audio_registry):
    payload = {
        "category": "bgm",
        "mood": ["calm", "epic"],  # 'epic' not allowed
        "instruments": ["piano", "synth"],  # 'synth' not allowed
    }
    ok, fixed, err = validate_audio_payload(payload, audio_registry)
    assert ok is False
    assert fixed["mood"] == ["calm"]
    assert fixed["instruments"] == ["piano"]


def test_validate_audio_payload_tempo_invalid_nulled(audio_registry):
    payload = {"category": "sfx", "tempo": "blazing"}
    ok, fixed, err = validate_audio_payload(payload, audio_registry)
    assert ok is False
    assert fixed["tempo"] is None


def test_audio_payload_to_labels_single_and_multi():
    payload = {
        "category": "bgm",
        "mood": ["calm", "tense"],
        "timbre": [], "environment": [],
        "instruments": ["piano", "drums", "guitar", "extra"],
        "use": [],
        "tempo": "slow", "intensity": "soft",
        "genre": "orchestral", "voice_type": None,
        "confidence": 0.9,
    }
    labels = audio_payload_to_labels(payload)
    by_axis = {(l.axis, l.label): l for l in labels}
    assert by_axis[("sound_category", "bgm")].weight == "primary"
    assert by_axis[("sound_mood", "calm")].weight == "primary"
    assert by_axis[("sound_mood", "tense")].weight == "secondary"
    instrs = [l for l in labels if l.axis == "sound_instrument"]
    assert [l.weight for l in instrs] == ["primary", "secondary", "tertiary", "tertiary"]
    assert all(l.source == "gemma" for l in labels)
    assert by_axis[("sound_genre", "orchestral")].weight == "primary"


def test_audio_payload_to_labels_missing_voice_type_omits_label():
    payload = {"category": "bgm", "voice_type": None}
    labels = audio_payload_to_labels(payload)
    assert all(l.axis != "sound_voice_type" for l in labels)


def test_audio_constants_cover_all_axes():
    """Guard against silent drift: every (axis, payload_key) is unique."""
    all_axes = [a for a, _ in AUDIO_SINGLE_AXES] + [a for a, _ in AUDIO_MULTI_AXES]
    assert len(all_axes) == len(set(all_axes))


# === collect_label_descriptions ========================================


def test_collect_label_descriptions_basic():
    reg = _StubRegistry(
        axis_labels={
            "category": ["hero", "monster"],
            "style": ["pixel_art"],
        },
        descriptions={
            ("category", "hero"): "Protagonist sprite",
            ("style", "pixel_art"): "Low-res grid",
        },
    )
    labels = [
        LabelScore(axis="category", label="hero", score=0.9,
                   source="gemma", weight="primary"),
        LabelScore(axis="style", label="pixel_art", score=0.9,
                   source="gemma", weight="primary"),
    ]
    out = collect_label_descriptions(labels, reg)
    assert out == {
        ("category", "hero"): "Protagonist sprite",
        ("style", "pixel_art"): "Low-res grid",
    }


def test_collect_label_descriptions_omits_missing():
    reg = _StubRegistry(
        axis_labels={"category": ["hero"]},
        descriptions={},
    )
    labels = [
        LabelScore(axis="category", label="hero", score=0.9,
                   source="gemma", weight="primary"),
    ]
    assert collect_label_descriptions(labels, reg) == {}


def test_collect_label_descriptions_deduplicates_keys():
    reg = _StubRegistry(
        axis_labels={"mood": ["calm"]},
        descriptions={("mood", "calm"): "low-energy"},
    )
    labels = [
        LabelScore(axis="mood", label="calm", score=0.9,
                   source="gemma", weight="primary"),
        LabelScore(axis="mood", label="calm", score=0.8,
                   source="clip", weight=None),
    ]
    out = collect_label_descriptions(labels, reg)
    assert out == {("mood", "calm"): "low-energy"}
