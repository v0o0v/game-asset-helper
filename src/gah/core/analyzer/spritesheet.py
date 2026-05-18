"""M6 — SpritesheetAnalyzer.

sheet.detect 가 성공하면 spritesheet 으로 promote 하고 8칸 합성을
Gemma 에 보내 animation_hint 를 받는다. 실패 시 일반 SpriteAnalyzer 로
위임. M6 spec §4.4.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import TYPE_CHECKING

from ..ollama_client import ChatMessage, OllamaError
from ..searchable import build_searchable
from ..sheet.detect import detect_sheet
from ..sheet.preview import make_preview_composite
from ..store import LabelScore, SpriteMeta
from .base import AnalyzerInput, AnalyzerResult

if TYPE_CHECKING:
    from ..embedding import EmbeddingEncoder
    from ..labels import LabelRegistry
    from ..ollama_client import OllamaClient
    from .sprite import SpriteAnalyzer

log = logging.getLogger(__name__)

_PREVIEW_MAX = 768


class SpritesheetAnalyzer:
    def __init__(
        self,
        *,
        sprite: "SpriteAnalyzer",
        ollama: "OllamaClient",
        registry: "LabelRegistry",
        embedder: "EmbeddingEncoder",
        clip=None,
    ) -> None:
        self.sprite = sprite
        self.ollama = ollama
        self.registry = registry
        self.embedder = embedder
        self.clip = clip

    def analyze(self, inp: AnalyzerInput) -> AnalyzerResult:
        detection = detect_sheet(inp.abs_path)
        if detection is None:
            # 폴백 — 일반 SpriteAnalyzer
            return self.sprite.analyze(inp)

        from PIL import Image as _PILImage

        try:
            with _PILImage.open(inp.abs_path) as src:
                src.load()
                composite = make_preview_composite(
                    src, list(detection.frames), max_size=_PREVIEW_MAX
                )
        except (OSError, ValueError):  # 파일 I/O / 이미지 포맷 오류 — SpriteAnalyzer 폴백
            log.exception("preview composite failed: %s", inp.abs_path)
            return self.sprite.analyze(inp)

        buf = io.BytesIO()
        composite.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        gemma_payload, state, error = self._call_gemma(
            img_b64=img_b64, language=inp.language,
        )

        # frame_w/h 추정 — 첫 프레임 박스 사용
        first = detection.frames[0]
        frame_w, frame_h = first.w, first.h

        # animations_json 조립: JSON frameTags 우선, Gemma 추론 라벨은 시트 전체 범위
        animations_json: dict = {}
        for tag in detection.tags:
            animations_json[tag.name] = {
                "start_frame": tag.start_frame,
                "end_frame": tag.end_frame,
                "fps_hint": tag.fps_hint,
                "source": tag.source,
            }
        hints = gemma_payload.get("animation_hint") or []
        for label in hints:
            if not isinstance(label, str) or not label:
                continue
            if label in animations_json:
                continue  # frameTags 가 이미 정의 — 우선
            animations_json[label] = {
                "start_frame": 0,
                "end_frame": len(detection.frames) - 1,
                "fps_hint": 12,
                "source": "gemma_inferred",
            }

        animation_tags = list(animations_json.keys()) if animations_json else None  # backward compat

        # 기본 sprite meta 측정 (원본 이미지)
        try:
            import numpy as np
            with _PILImage.open(inp.abs_path) as orig:
                rgba = orig.convert("RGBA")
                w, h = rgba.size
                arr = np.asarray(rgba)
                has_alpha = bool((arr[:, :, 3] < 255).any())
        except (OSError, ValueError):  # numpy/Pillow 알파 측정 실패 — 합성 이미지 크기로 폴백
            w, h, has_alpha = composite.size[0], composite.size[1], True

        sprite_meta = SpriteMeta(
            width=w, height=h,
            has_alpha=has_alpha, is_pixel_art=True,  # 시트는 보통 픽셀 아트 — v1 단순화 (개별 측정은 v2)
            dominant_colors=[],
            frame_w=frame_w, frame_h=frame_h, frame_count=len(detection.frames),
            animation_tags=animation_tags,
            animations_json=animations_json,
        )

        labels: list[LabelScore] = []
        for label in hints:
            if isinstance(label, str) and label:
                labels.append(LabelScore(
                    axis="animation", label=label,
                    score=float(gemma_payload.get("confidence") or 0.5),
                    source="gemma", weight="primary",
                ))

        searchable = build_searchable(
            meta=sprite_meta, labels=labels, label_descriptions={},
            description=gemma_payload.get("description", "") or "",
            rel_path=inp.rel_path,
        )

        try:
            blob, dim = self.embedder.encode_text(searchable.for_embed)
        except OllamaError:
            blob, dim = b"", 0
            if state == "ok":
                state = "partial"

        return AnalyzerResult(
            kind="spritesheet", state=state, error=error,
            sprite_meta=sprite_meta, sound_meta=None,
            labels=labels, searchable=searchable,
            embedding_vector=blob, embedding_dim=dim,
            embedding_model=self.embedder.model,
            description=gemma_payload.get("description", "") or "",
        )

    def _call_gemma(
        self, *, img_b64: str, language: str,
    ) -> tuple[dict, str, str | None]:
        anim_enum = ", ".join(self.registry.list_labels("animation"))
        system = (
            "You are a game animation labeler. Respond ONLY with valid JSON.\n\n"
            "Input is a horizontal strip of sprite frames.\n"
            "Schema:\n"
            f"- animation_hint: array (1..4) from [{anim_enum}]\n"
            "- description: one sentence in {lang}\n"
            "- subject: short noun phrase in {lang}\n"
            "- category: 'character'\n"
            "- style: 'pixel_art'\n"
            "- mood: []\n"
            "- palette: []\n"
            "- confidence: float 0..1\n"
        ).replace("{lang}", language)
        messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content="Identify the animation in this strip.",
                       images_b64=[img_b64]),
        ]
        try:
            payload = self.ollama.chat(messages, force_json=True, num_ctx=4000)
            return payload, "ok", None
        except OllamaError as e:
            return ({"animation_hint": [], "description": "",
                    "subject": "", "category": "other",
                    "style": "other", "mood": [], "palette": [],
                    "confidence": 0.0}, "partial", f"ollama: {e}")
