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


def detect_sheet(
    image_path: Path, *, alpha_color_weight: float = 0.5,
) -> "SheetDetection | None":
    """M6 + M11.4 — JSON 사이드카 우선, 없으면 grid_detect.

    ``alpha_color_weight`` 는 grid_detect 에 그대로 전달 — Config 의 동명
    필드 값이 BatchManager / BatchPoller / SpritesheetAnalyzer 를 통해
    전파된다 (M11.4 cleanup #1).  0 이면 alpha valley 만 사용 (M6 호환).
    """
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

    # 2) Pillow alpha 격자 추정 + M11.4 color-edge 폴백
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(image_path) as img:
            img.load()
            layout = grid_detect(img, alpha_color_weight=alpha_color_weight)
    except (OSError, ValueError) as e:
        log.warning("sheet open failed: %s — %s", image_path, e)
        return None

    if layout is None:
        return None

    # GridLayout 을 FrameSpec 시퀀스로 풀어쓴다 (균일 간격 가정)
    # M11.3 patch D-2 — FrameSpec.w/h 는 slot 크기 (stride) 사용.  grid_detect
    # 의 ``layout.frame_w`` 는 alpha-tight 경계라 content 가 작은 시트에서
    # 실제 frame slot 보다 작게 (예: 32 slot 에 17 content) 보고됨.  사용자의
    # sprite_meta.frame_w 는 애니메이션 재생 슬롯 크기를 기대하므로 stride 가
    # 일반적으로 더 정확.
    frames: list[FrameSpec] = []
    with _PILImage.open(image_path) as img:
        total_w, total_h = img.size
    # grid_detect 가 rows ≥ 1, cols ≥ 1 보장 (단일 프레임은 None 반환).
    stride_x = total_w // layout.cols if layout.cols > 0 else layout.frame_w
    stride_y = total_h // layout.rows if layout.rows > 0 else layout.frame_h
    idx = 0
    for r in range(layout.rows):
        for c in range(layout.cols):
            frames.append(FrameSpec(
                x=c * stride_x, y=r * stride_y,
                w=stride_x, h=stride_y,
                duration_ms=0, name=str(idx),
            ))
            idx += 1
    return SheetDetection(frames=frames, tags=[], source="grid")
