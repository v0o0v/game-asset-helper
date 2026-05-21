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


# === M11.3 patch B — non-dict / list payload graceful handling ============


def test_validate_image_payload_list_with_dict_first_uses_it(image_registry):
    """Gemma 가 list 로 응답한 경우 첫 element 가 dict 면 그걸로 처리."""
    payload = [
        {"category": "character", "style": "pixel_art", "mood": ["heroic"]},
        {"category": "ignored"},
    ]
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is True
    assert err is None
    assert fixed["category"] == "character"
    assert fixed["style"] == "pixel_art"


def test_validate_image_payload_empty_list_falls_back_to_defaults(image_registry):
    """빈 list payload → 빈 dict 처리 + violation 보고 + 라벨 'other' fallback."""
    ok, err, fixed = validate_image_payload([], image_registry)
    assert ok is False
    assert err is not None
    assert fixed["category"] == "other"  # fallback
    assert fixed["style"] == "other"


def test_validate_image_payload_non_dict_scalar_falls_back(image_registry):
    """payload 가 str/None/숫자 등 dict 도 list 도 아닌 경우 → 빈 dict."""
    for bad in ("just a string", None, 42, ["only_a_string"]):
        ok, err, fixed = validate_image_payload(bad, image_registry)
        assert ok is False
        assert err is not None
        assert isinstance(fixed, dict)
        # category fallback 적용됨
        assert fixed["category"] == "other"


# === M11.4 Phase 3 — palette tone group whitelist (hex 거부) ===========


def test_validate_image_payload_palette_hex_rejected_with_named_violation(
    image_registry,
):
    """hex 값 (#FDD835) 은 palette 에서 거부 + violation 메시지에 'palette_hex' 마커 명시."""
    payload = {
        "category": "character", "style": "pixel_art",
        "palette": ["#FDD835", "#33B5E5"],
    }
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is False
    assert fixed["palette"] == []
    # M11.4: hex 는 일반 whitelist 위반과 별도 명시
    assert "palette_hex" in err


def test_validate_image_payload_palette_tone_groups_accepted():
    """tone group set (warm / cool / monochrome / high_contrast / pastel / neutral) 통과."""
    reg = _StubRegistry({
        "category": ["character", "other"],
        "style": ["pixel_art", "other"],
        "mood": [],
        "palette": ["warm", "cool", "monochrome", "high_contrast", "pastel", "neutral"],
        "animation": [],
    })
    for tone in ("warm", "cool", "monochrome", "high_contrast", "pastel", "neutral"):
        payload = {
            "category": "character", "style": "pixel_art", "palette": [tone],
        }
        ok, err, fixed = validate_image_payload(payload, reg)
        assert ok is True, f"{tone!r} should pass (err={err})"
        assert fixed["palette"] == [tone]


def test_validate_image_payload_palette_mixed_hex_and_tone_group_keeps_tone():
    """hex + tone group 섞이면 hex 만 제거, tone group 은 유지."""
    reg = _StubRegistry({
        "category": ["character", "other"],
        "style": ["pixel_art", "other"],
        "mood": [],
        "palette": ["warm", "cool", "neutral"],
        "animation": [],
    })
    payload = {
        "category": "character", "style": "pixel_art",
        "palette": ["warm", "#FDD835", "cool"],
    }
    ok, err, fixed = validate_image_payload(payload, reg)
    assert ok is False  # hex 가 있어서 violation 발생
    assert fixed["palette"] == ["warm", "cool"]
    assert "palette_hex" in err


def test_validate_image_payload_palette_non_hex_invalid_dropped_generically(
    image_registry,
):
    """hex 아닌 unknown 토큰 (super_warm) 은 기존 일반 violation 으로 drop."""
    payload = {
        "category": "character", "style": "pixel_art",
        "palette": ["super_warm", "warm"],
    }
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is False
    assert fixed["palette"] == ["warm"]
    # hex 가 아닌 invalid 토큰은 'palette_hex' 가 아닌 일반 'palette=' 위반만 발생
    assert "palette_hex" not in err


def test_seed_palette_has_high_contrast():
    """tone group whitelist 의 high_contrast 가 시드에 등록됐는지."""
    from assetcache.core.labels import SEED_LABELS

    tokens = {t for t, _ in SEED_LABELS["palette"]}
    assert "high_contrast" in tokens


def test_validate_image_payload_mood_hex_rejected_with_named_violation(
    image_registry,
):
    """mood 에 hex 가 들어와도 palette 와 동일하게 명시 violation (M11.4 cleanup #8)."""
    payload = {
        "category": "character", "style": "pixel_art",
        "mood": ["#FF0000", "heroic"],
    }
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is False
    assert fixed["mood"] == ["heroic"]
    assert "mood_hex" in err


def test_validate_image_payload_animation_hex_rejected_with_named_violation(
    image_registry,
):
    """animation_hint 에 hex 가 들어와도 명시 violation (M11.4 cleanup #8)."""
    payload = {
        "category": "character", "style": "pixel_art",
        "animation_hint": ["#00FF00", "idle"],
    }
    ok, err, fixed = validate_image_payload(payload, image_registry)
    assert ok is False
    assert fixed["animation_hint"] == ["idle"]
    assert "animation_hint_hex" in err


def test_validate_audio_payload_list_with_dict_first_uses_it(audio_registry):
    """audio 도 list 첫 dict 사용."""
    payload = [
        {"category": "sfx", "mood": ["calm"], "tempo": "medium"},
        {"category": "ignored"},
    ]
    ok, fixed, err = validate_audio_payload(payload, audio_registry)
    assert ok is True
    assert err is None
    assert fixed["category"] == "sfx"


def test_validate_audio_payload_non_dict_falls_back(audio_registry):
    """audio 도 비-dict 입력 → 빈 dict fallback."""
    for bad in ([], None, "x", 99):
        ok, fixed, err = validate_audio_payload(bad, audio_registry)
        assert ok is False
        assert isinstance(fixed, dict)


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
