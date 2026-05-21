"""Free functions for validating Gemma JSON payloads and converting to LabelScore lists.

Extracted from SpriteAnalyzer / SoundAnalyzer so both paths share identical logic:

* **Sync path** — :class:`SpriteAnalyzer` / :class:`SoundAnalyzer` wrap these
  inside retry loops with native-audio / spectrogram fallback.
* **Batch path** — :class:`BatchPoller` calls these directly on per-asset
  Gemini batch JSON results to convert the response into rows the search
  backends can use.

Behaviour is bit-identical to the previous private methods to keep the
existing sync analyzer test suite green.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..store import LabelScore

if TYPE_CHECKING:
    from ..labels import LabelRegistry


# === Image (sprite) ====================================================

IMAGE_CATEGORY_FALLBACK = "other"
# 시드 'style' 에 'other' 가 없을 수 있어 안전망 — 추후 보정
IMAGE_STYLE_FALLBACK = "other"

# M11.4 Phase 3 — palette 에 들어온 hex (`#FDD835`) 토큰을 일반 whitelist
# 위반과 분리해 별도 violation 으로 추적한다.  LLM (sync Gemma / batch
# Gemini 양쪽) 이 prompt 의 tone-group enum 가이드 (`warm`/`cool`/
# `monochrome`/`high_contrast`/`pastel`/`neutral`) 를 무시하고 hex 를 뱉을
# 때 monitoring 용 시그널.
_PALETTE_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _coerce_to_dict(payload: object) -> dict:
    """LLM 응답이 dict 가 아닌 경우 graceful fallback.

    M11.3 patch B — Gemini batch 응답이 가끔 ``list`` 또는 scalar 로 와서
    ``dict(payload)`` 가 ValueError/TypeError 를 던지는 경우가 있다.  이
    helper 는:

    * ``dict`` → 그대로 dict copy
    * ``list`` + 첫 element 가 dict → 첫 element copy
    * 기타 (list of non-dict, str, None, int…) → 빈 dict

    빈 dict 가 반환되면 후속 violation 검사가 모든 enum 필드를 fallback
    으로 채워 ``ok=False`` 로 응답하므로 caller 의 기존 흐름 그대로 동작.
    """
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return dict(payload[0])
    return {}


def validate_image_payload(
    payload: object, registry: "LabelRegistry",
) -> tuple[bool, str | None, dict]:
    """Whitelist-check sprite enums against the registry.

    Returns ``(ok, error, fixed)`` — matches the legacy
    ``SpriteAnalyzer._validate_payload`` tuple order so callers can drop in
    without changes.

    M11.3 patch B — payload 가 dict 가 아닌 경우 (list, str, None…) 도 안전.
    """
    fixed = _coerce_to_dict(payload)
    violations: list[str] = []
    if not isinstance(payload, dict) and not (
        isinstance(payload, list) and payload and isinstance(payload[0], dict)
    ):
        violations.append(f"payload_not_dict={type(payload).__name__}")

    def _squash_single(key: str) -> object:
        value = fixed.get(key)
        if isinstance(value, list):
            violations.append(f"{key}_was_list={value!r}")
            value = value[0] if value else None
            fixed[key] = value
        return value

    category_allowed = set(registry.list_labels("category"))
    cat = _squash_single("category")
    if cat not in category_allowed:
        violations.append(f"category={cat!r}")
        fixed["category"] = (
            IMAGE_CATEGORY_FALLBACK
            if IMAGE_CATEGORY_FALLBACK in category_allowed
            else next(iter(category_allowed), IMAGE_CATEGORY_FALLBACK)
        )

    style_allowed = set(registry.list_labels("style"))
    st = _squash_single("style")
    if st not in style_allowed:
        violations.append(f"style={st!r}")
        fixed["style"] = (
            IMAGE_STYLE_FALLBACK
            if IMAGE_STYLE_FALLBACK in style_allowed
            else next(iter(style_allowed), IMAGE_STYLE_FALLBACK)
        )

    for axis_key, payload_key in (
        ("mood", "mood"),
        ("palette", "palette"),
        ("animation", "animation_hint"),
    ):
        allowed = set(registry.list_labels(axis_key))
        arr = fixed.get(payload_key) or []
        if not isinstance(arr, list):
            violations.append(f"{payload_key}_not_list={arr!r}")
            arr = [arr] if isinstance(arr, str) else []
        # M11.4 Phase 3 — palette 의 hex 토큰은 일반 whitelist 위반과 별도로
        # 'palette_hex={value}' 형태로 명시 (prompt 가이드 위반 monitoring).
        if payload_key == "palette":
            for t in arr:
                if isinstance(t, str) and _PALETTE_HEX_RE.fullmatch(t):
                    violations.append(f"palette_hex={t}")
        cleaned = [t for t in arr if isinstance(t, str) and t in allowed]
        if len(cleaned) != len(arr):
            violations.append(f"{payload_key}={arr!r}")
        fixed[payload_key] = cleaned

    if violations:
        return False, "whitelist violations: " + ", ".join(violations), fixed
    return True, None, fixed


def image_payload_to_labels(payload: dict) -> list[LabelScore]:
    """Convert validated sprite payload to a list of :class:`LabelScore`.

    Multi-value axes (mood/palette/animation_hint) get
    ``primary``/``secondary``/``tertiary`` weights by ordinal position;
    single-value axes (category/style) always get ``primary``.
    Missing keys produce no labels (silently dropped).
    """
    labels: list[LabelScore] = []
    confidence = float(payload.get("confidence") or 0.5)

    def _emit_single(axis: str, payload_key: str) -> None:
        value = payload.get(payload_key)
        if value:
            labels.append(LabelScore(
                axis=axis, label=value, score=confidence,
                source="gemma", weight="primary",
            ))

    def _emit_multi(axis: str, payload_key: str) -> None:
        for i, value in enumerate(payload.get(payload_key) or []):
            if not value:
                continue
            weight = (
                "primary" if i == 0
                else "secondary" if i == 1
                else "tertiary"
            )
            labels.append(LabelScore(
                axis=axis, label=value, score=confidence,
                source="gemma", weight=weight,
            ))

    _emit_single("category", "category")
    _emit_single("style", "style")
    _emit_multi("mood", "mood")
    _emit_multi("palette", "palette")
    _emit_multi("animation", "animation_hint")
    return labels


# === Audio (sound) ====================================================

AUDIO_MUSIC_CATEGORIES = frozenset({"bgm", "jingle", "cinematic"})
AUDIO_MULTI_AXES: tuple[tuple[str, str], ...] = (
    ("sound_mood", "mood"),
    ("sound_timbre", "timbre"),
    ("sound_environment", "environment"),
    ("sound_instrument", "instruments"),
    ("sound_use", "use"),
)
AUDIO_SINGLE_AXES: tuple[tuple[str, str], ...] = (
    ("sound_category", "category"),
    ("sound_tempo", "tempo"),
    ("sound_intensity", "intensity"),
    ("sound_genre", "genre"),
    ("sound_voice_type", "voice_type"),
)


def validate_audio_payload(
    payload: object, registry: "LabelRegistry",
) -> tuple[bool, dict, str | None]:
    """Whitelist-check sound enums against the registry.

    Returns ``(ok, fixed, error)`` — matches the legacy
    ``SoundAnalyzer._validate`` tuple order (note: arg order differs from
    :func:`validate_image_payload` to preserve back-compat).

    M11.3 patch B — payload 가 dict 가 아닌 경우 (list, None…) 도 안전.
    """
    fixed = _coerce_to_dict(payload)
    violations: list[str] = []
    if not isinstance(payload, dict) and not (
        isinstance(payload, list) and payload and isinstance(payload[0], dict)
    ):
        violations.append(f"payload_not_dict={type(payload).__name__}")

    def _squash_single(key: str) -> object:
        value = fixed.get(key)
        if isinstance(value, list):
            violations.append(f"{key}_was_list={value!r}")
            value = value[0] if value else None
            fixed[key] = value
        return value

    cat_allowed = set(registry.list_labels("sound_category"))
    cat = _squash_single("category")
    if cat not in cat_allowed:
        violations.append(f"category={cat!r}")
        fixed["category"] = "sfx" if "sfx" in cat_allowed else next(iter(cat_allowed), None)

    for axis_key, payload_key in AUDIO_MULTI_AXES:
        allowed = set(registry.list_labels(axis_key))
        arr = fixed.get(payload_key) or []
        if not isinstance(arr, list):
            violations.append(f"{payload_key}_not_list={arr!r}")
            arr = [arr]
        cleaned = [t for t in arr if isinstance(t, str) and t in allowed]
        if len(cleaned) != len(arr):
            violations.append(f"{payload_key}={arr!r}")
        fixed[payload_key] = cleaned

    for axis_key, payload_key in (
        ("sound_tempo", "tempo"),
        ("sound_intensity", "intensity"),
    ):
        allowed = set(registry.list_labels(axis_key))
        val = _squash_single(payload_key)
        if val is not None and val not in allowed:
            violations.append(f"{payload_key}={val!r}")
            fixed[payload_key] = None

    # 조건부 단일 필드: genre / voice_type
    genre_allowed = set(registry.list_labels("sound_genre"))
    genre = _squash_single("genre")
    if fixed.get("category") in AUDIO_MUSIC_CATEGORIES:
        if genre is not None and genre not in genre_allowed:
            violations.append(f"genre={genre!r}")
            fixed["genre"] = None
    else:
        # 음악 카테고리 아닌데 genre 채워졌으면 위반 — null 강제
        if genre is not None:
            violations.append(f"genre when category={fixed.get('category')}")
            fixed["genre"] = None

    voice_allowed = set(registry.list_labels("sound_voice_type"))
    vt = _squash_single("voice_type")
    if fixed.get("category") == "voice":
        if vt is not None and vt not in voice_allowed:
            violations.append(f"voice_type={vt!r}")
            fixed["voice_type"] = None
    else:
        if vt is not None:
            violations.append("voice_type when category not voice")
            fixed["voice_type"] = None

    return (not violations), fixed, ("violations: " + ", ".join(violations)
                                      if violations else None)


def audio_payload_to_labels(payload: dict) -> list[LabelScore]:
    """Convert validated sound payload to a list of :class:`LabelScore`."""
    labels: list[LabelScore] = []
    confidence = float(payload.get("confidence") or 0.5)

    for axis, payload_key in AUDIO_SINGLE_AXES:
        value = payload.get(payload_key)
        if value:
            labels.append(LabelScore(
                axis=axis, label=value, score=confidence,
                source="gemma", weight="primary",
            ))

    for axis, payload_key in AUDIO_MULTI_AXES:
        for i, value in enumerate(payload.get(payload_key) or []):
            if not value:
                continue
            weight = (
                "primary" if i == 0
                else "secondary" if i == 1
                else "tertiary"
            )
            labels.append(LabelScore(
                axis=axis, label=value, score=confidence,
                source="gemma", weight=weight,
            ))
    return labels


def collect_label_descriptions(
    labels: list[LabelScore], registry: "LabelRegistry",
) -> dict[tuple[str, str], str]:
    """Look up the human-readable description for each unique (axis, label).

    Used by both the sync analyzer path and the batch poller path when
    building :func:`build_searchable` input.  Missing descriptions are
    silently omitted.
    """
    wanted: dict[tuple[str, str], str] = {}
    for lbl in labels:
        key = (lbl.axis, lbl.label)
        if key in wanted:
            continue
        rows = registry.list_labels(
            axis=lbl.axis, with_description=True,
        )
        for row in rows:
            if row.label == lbl.label and row.description:
                wanted[key] = row.description
                break
    return wanted
