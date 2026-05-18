"""M6 — sheet 검출 오케스트레이션.

3단계: <basename>.json → grid_detect → None.
M6 spec §4.2 / §4.8 / §4.9.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .grid_detect import grid_detect
from .json_parser import parse as parse_json
from .types import AnimationSpec, AsepriteAtlas, FrameSpec

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SheetDetection:
    frames: list[FrameSpec]
    tags: list[AnimationSpec]
    source: str  # 'json' | 'grid'


def detect_sheet(image_path: Path) -> "SheetDetection | None":
    image_path = Path(image_path)
    json_path = image_path.with_suffix(".json")

    # 1) JSON 사이드카
    if json_path.exists():
        atlas = parse_json(json_path)
        if atlas is not None and atlas.frames:
            tags = atlas.tags if isinstance(atlas, AsepriteAtlas) else []
            return SheetDetection(frames=list(atlas.frames),
                                  tags=list(tags),
                                  source="json")

    # 2) Pillow alpha 격자 추정
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(image_path) as img:
            img.load()
            layout = grid_detect(img)
    except (OSError, ValueError) as e:
        log.warning("sheet open failed: %s — %s", image_path, e)
        return None

    if layout is None:
        return None

    # GridLayout 을 FrameSpec 시퀀스로 풀어쓴다 (균일 간격 가정)
    frames: list[FrameSpec] = []
    with _PILImage.open(image_path) as img:
        total_w, total_h = img.size
    # grid_detect 가 rows ≥ 1, cols ≥ 1 보장 (단일 프레임은 None 반환).
    # 방어적 if 는 lint 안심용. v1.
    stride_x = total_w // layout.cols if layout.cols > 0 else layout.frame_w
    stride_y = total_h // layout.rows if layout.rows > 0 else layout.frame_h
    idx = 0
    for r in range(layout.rows):
        for c in range(layout.cols):
            frames.append(FrameSpec(
                x=c * stride_x, y=r * stride_y,
                w=layout.frame_w, h=layout.frame_h,
                duration_ms=0, name=str(idx),
            ))
            idx += 1
    return SheetDetection(frames=frames, tags=[], source="grid")
