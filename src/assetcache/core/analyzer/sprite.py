"""Sprite analyzer.

Pipeline:
  1. Technical specs via Pillow + numpy (alpha / pixel-art heuristic /
     5 dominant colors via tiny k-means).
  2. Resample longest edge to 768 px and base64-encode → Gemma 4 chat
     with a JSON-strict system prompt populated from the live
     :class:`LabelRegistry`.
  3. Optionally collect per-label CLIP cosine scores for the 14 visual
     axes (when ``clip`` is enabled).
  4. Build the dual searchable text + embedding via
     :class:`EmbeddingEncoder`.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..llm import unwrap_chat_result
from ..llm.base import BackendError
from ..ollama_client import ChatMessage, OllamaError
from ..searchable import build_searchable
from ..store import LabelScore, SpriteMeta
from .base import AnalyzerInput, AnalyzerResult

if TYPE_CHECKING:
    from ..clip_labeler import ClipLabeler
    from ..embedding import EmbeddingEncoder
    from ..labels import LabelRegistry
    from ..ollama_client import OllamaClient

log = logging.getLogger(__name__)


_CATEGORY_FALLBACK = "other"
_STYLE_FALLBACK = "other"  # 시드 'style' 에 'other' 가 없을 수 있어 안전망 — 추후 보정


class SpriteAnalyzer:
    def __init__(
        self,
        *,
        ollama: "OllamaClient",
        clip: "ClipLabeler | None",
        embedder: "EmbeddingEncoder",
        registry: "LabelRegistry",
        max_long_edge: int = 768,
    ) -> None:
        self.ollama = ollama
        self.clip = clip
        self.embedder = embedder
        self.registry = registry
        self.max_long_edge = max_long_edge

    # -- public API ---------------------------------------------------

    def analyze(self, inp: AnalyzerInput) -> AnalyzerResult:
        import numpy as np
        from PIL import Image

        # ── 1. 기술 특성 ─────────────────────────────────────────────
        img = Image.open(inp.abs_path)
        width, height = img.size
        has_alpha = self._has_alpha(img)
        rgb = img.convert("RGB")
        arr = np.asarray(rgb, dtype=np.uint8)
        is_pixel_art = self._is_pixel_art(arr)
        dominant = self._dominant_colors(arr, k=5)

        # ── 2. 리샘플 + base64 ───────────────────────────────────────
        resampled = self._resample(img, self.max_long_edge)
        buf = io.BytesIO()
        resampled.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        # ── 3. Gemma 호출 + 검증 + (위반 시) 재시도 ──────────────────
        gemma_payload, state, error, image_backend = self._call_gemma_with_validation(
            img_b64=img_b64, language=inp.language,
        )

        # ── 4. 라벨 통합 (Gemma + CLIP) ──────────────────────────────
        labels = self._gemma_to_labels(gemma_payload)
        if self.clip is not None and self.clip.enabled:
            try:
                clip_scores = self.clip.score_image(inp.abs_path)
                for label_name, score in clip_scores.items():
                    # axis 는 registry 의 가장 첫 등장 축 — 단순화
                    axis = self._lookup_axis_for_label(label_name)
                    if axis is None:
                        continue
                    labels.append(LabelScore(
                        axis=axis, label=label_name,
                        score=float(score), source="clip", weight=None,
                    ))
            except Exception:  # pragma: no cover - CLIP 실패는 분석 자체를 막지 않음
                log.exception("CLIP scoring failed for %s", inp.abs_path)

        # ── 5. searchable 텍스트 + 임베딩 ───────────────────────────
        sprite_meta = SpriteMeta(
            width=width, height=height,
            has_alpha=has_alpha, is_pixel_art=is_pixel_art,
            dominant_colors=dominant,
        )
        label_descs = self._collect_label_descriptions(labels)
        searchable = build_searchable(
            meta=sprite_meta, labels=labels, label_descriptions=label_descs,
            description=gemma_payload.get("description", "") or "",
            rel_path=inp.rel_path,
        )
        embed_backend: str | None = None
        try:
            blob, dim = self.embedder.encode_text(searchable.for_embed)
            embed_backend = self.embedder.last_backend_name
        except OllamaError:
            blob, dim = b"", 0
            if state == "ok":
                state = "partial"

        backend_used: dict = {}
        if image_backend:
            backend_used["image"] = image_backend
        if embed_backend:
            backend_used["embed"] = embed_backend

        return AnalyzerResult(
            kind="sprite", state=state, error=error,
            sprite_meta=sprite_meta, sound_meta=None,
            labels=labels, searchable=searchable,
            embedding_vector=blob, embedding_dim=dim,
            embedding_model=self.embedder.model,
            description=gemma_payload.get("description", "") or "",
            backend_used=backend_used,
        )

    # -- technical helpers ------------------------------------------

    @staticmethod
    def _has_alpha(img) -> bool:
        if img.mode in ("RGBA", "LA"):
            return True
        return img.info.get("transparency") is not None

    @staticmethod
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

    @staticmethod
    def _dominant_colors(arr, *, k: int = 5) -> list[str]:
        """Tiny k-means++ on a downsampled image — returns hex colors."""
        import numpy as np

        h, w, _ = arr.shape
        step = max(1, max(h, w) // 96)
        flat = arr[::step, ::step].reshape(-1, 3).astype(np.float32)
        if len(flat) <= k:
            # 픽셀이 너무 적으면 단순 unique 로 채움
            unique = np.unique(flat, axis=0)
            picks = unique[:k]
            return [_rgb_to_hex(c) for c in picks] + [
                "#000000"
            ] * (k - len(picks))

        rng = np.random.default_rng(seed=0)
        # k-means++ 초기화 (한 점에서 시작 → 거리 비례로 다음 중심)
        centers = [flat[rng.integers(0, len(flat))]]
        for _ in range(k - 1):
            dists = np.min(
                np.linalg.norm(flat[:, None, :] - np.stack(centers)[None],
                               axis=2),
                axis=1,
            )
            total = float(dists.sum())
            if total <= 0:
                # 모든 점이 기존 중심과 정확히 일치 — 임의 점으로 진행
                centers.append(flat[rng.integers(0, len(flat))])
                continue
            probs = (dists.astype(np.float64) / total)
            # 부동소수 합이 정확히 1 이 되도록 한 번 더 정규화 (numpy.choice 의 까다로운 합 검사용)
            probs = probs / probs.sum()
            idx = int(rng.choice(len(flat), p=probs))
            centers.append(flat[idx])
        c = np.stack(centers)
        # 8 iter Lloyd
        for _ in range(8):
            d = np.linalg.norm(flat[:, None, :] - c[None], axis=2)
            assign = d.argmin(axis=1)
            for ki in range(k):
                pts = flat[assign == ki]
                if len(pts) > 0:
                    c[ki] = pts.mean(axis=0)
        return [_rgb_to_hex(ci) for ci in c]

    @staticmethod
    def _resample(img, max_edge: int):
        from PIL import Image

        w, h = img.size
        longest = max(w, h)
        if longest <= max_edge:
            return img.convert("RGB")
        scale = max_edge / longest
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        return img.convert("RGB").resize(new_size, Image.LANCZOS)

    # -- Gemma orchestration ----------------------------------------

    def _call_gemma_with_validation(
        self, *, img_b64: str, language: str
    ) -> tuple[dict, str, str | None, str | None]:
        """Call Gemma + validate the enum payload, retrying on violations.

        ``OllamaClient`` already retries 200-but-bad-JSON internally, so
        the loop here covers the analyzer-specific failure mode:
        whitelist violations.  We try up to 3 times before demoting the
        offending fields to ``other`` and returning ``partial``.

        Returns ``(payload, state, error, backend_name_used)``.
        M11.1 Task 1.5 — 4번째 반환값으로 실제 호출된 backend 이름 노출.
        """
        system_prompt = self._build_system_prompt(language=language)
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content="Analyse this sprite.",
                        images_b64=[img_b64]),
        ]
        last_fixed: dict | None = None
        last_err: str | None = None
        last_backend: str | None = None
        for _ in range(3):
            try:
                raw = self.ollama.chat(messages, force_json=True, num_ctx=8000)
                # BackendChain → (dict, str), OllamaClient → dict
                if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], str):
                    payload, last_backend = raw[0], raw[1]
                else:
                    payload, last_backend = raw, None
            except (OllamaError, BackendError) as e:
                # M11 — backend 이름을 명시 (이전 "ollama:" hardcoded prefix 는 chain 시대
                # 에 misleading — 실제 호출된 backend 가 gemini/claude/openai 등일 수 있음).
                backend_name = getattr(e, "backend", None) or "chat"
                return ({"description": "", "subject": "",
                         "category": _CATEGORY_FALLBACK,
                         "style": _STYLE_FALLBACK, "mood": [], "palette": [],
                         "animation_hint": [], "confidence": 0.0},
                        "partial", f"chat backend ({backend_name}): {e}", None)
            ok, err, fixed = self._validate_payload(payload)
            if ok:
                return payload, "ok", None, last_backend
            last_fixed = fixed
            last_err = err
        # M11 — 3회 retry 모두 enum validation 실패. backend 응답 자체는 받음.
        # 메시지에 "validation:" prefix 로 backend error 와 구분.
        return last_fixed or {}, "partial", f"validation (3 retries failed): {last_err}", last_backend

    def _build_system_prompt(self, *, language: str) -> str:
        # 라벨 enum 동적 주입
        slots = {
            "category_enum": ", ".join(self.registry.list_labels("category")),
            "style_enum": ", ".join(self.registry.list_labels("style")),
            "mood_enum": ", ".join(self.registry.list_labels("mood")),
            "palette_enum": ", ".join(self.registry.list_labels("palette")),
            "animation_enum": ", ".join(self.registry.list_labels("animation")),
            "language": language,
        }
        return (
            "You are a game asset metadata generator. Respond ONLY with valid"
            " JSON, no prose.\n\n"
            "JSON schema (strict):\n"
            "- category: one of [{category_enum}]\n"
            "- style: one of [{style_enum}]\n"
            "- mood: array (1..3) from [{mood_enum}]\n"
            "- palette: array (1..2) from [{palette_enum}]\n"
            "- animation_hint: array (0..4) from [{animation_enum}]\n"
            "- subject: short noun phrase in {language}\n"
            "- description: one sentence (<= 30 words) in {language}\n"
            "- confidence: float 0..1\n\n"
            "If unsure of an enum, pick \"other\"."
        ).format(**slots)

    def _validate_payload(self, payload: dict) -> tuple[bool, str | None, dict]:
        """Whitelist-check enums. Demote violators to 'other'/drop, return fixed copy.

        Gemma 가 종종 단일 enum 필드를 list 로 돌려주거나 다중 필드를 단일
        문자열로 보내는 경우가 있어 type-coerce 후 검증한다.
        """
        fixed = dict(payload)
        violations: list[str] = []

        def _squash_single(key: str) -> object:
            value = fixed.get(key)
            if isinstance(value, list):
                violations.append(f"{key}_was_list={value!r}")
                value = value[0] if value else None
                fixed[key] = value
            return value

        category_allowed = set(self.registry.list_labels("category"))
        cat = _squash_single("category")
        if cat not in category_allowed:
            violations.append(f"category={cat!r}")
            fixed["category"] = (
                _CATEGORY_FALLBACK
                if _CATEGORY_FALLBACK in category_allowed
                else next(iter(category_allowed), _CATEGORY_FALLBACK)
            )

        style_allowed = set(self.registry.list_labels("style"))
        st = _squash_single("style")
        if st not in style_allowed:
            violations.append(f"style={st!r}")
            fixed["style"] = (
                _STYLE_FALLBACK
                if _STYLE_FALLBACK in style_allowed
                else next(iter(style_allowed), _STYLE_FALLBACK)
            )

        for axis_key, payload_key in (
            ("mood", "mood"),
            ("palette", "palette"),
            ("animation", "animation_hint"),
        ):
            allowed = set(self.registry.list_labels(axis_key))
            arr = fixed.get(payload_key) or []
            if not isinstance(arr, list):
                violations.append(f"{payload_key}_not_list={arr!r}")
                arr = [arr] if isinstance(arr, str) else []
            cleaned = [t for t in arr if isinstance(t, str) and t in allowed]
            if len(cleaned) != len(arr):
                violations.append(f"{payload_key}={arr!r}")
            fixed[payload_key] = cleaned

        if violations:
            return False, "whitelist violations: " + ", ".join(violations), fixed
        return True, None, fixed

    # -- label assembly ---------------------------------------------

    def _gemma_to_labels(self, payload: dict) -> list[LabelScore]:
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

    def _lookup_axis_for_label(self, label: str) -> str | None:
        visual_axes = (
            "category", "style", "mood", "palette", "color", "view",
            "material", "lighting", "time_of_day", "weather", "theme",
            "size_hint", "domain", "animation",
        )
        for axis in visual_axes:
            if label in self.registry.list_labels(axis):
                return axis
        return None

    def _collect_label_descriptions(
        self, labels: list[LabelScore]
    ) -> dict[tuple[str, str], str]:
        wanted: dict[tuple[str, str], str] = {}
        for lbl in labels:
            key = (lbl.axis, lbl.label)
            if key in wanted:
                continue
            rows = self.registry.list_labels(
                axis=lbl.axis, with_description=True
            )
            for row in rows:
                if row.label == lbl.label and row.description:
                    wanted[key] = row.description
                    break
        return wanted


def _rgb_to_hex(c) -> str:
    r, g, b = (int(max(0, min(255, x))) for x in c)
    return f"#{r:02x}{g:02x}{b:02x}"
