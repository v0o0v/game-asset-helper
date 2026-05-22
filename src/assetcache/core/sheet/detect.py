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


def _ratio_fallback_detect(width: int, height: int) -> "SheetDetection | None":
    """M11.10 — width/height 또는 height/width 가 정수 (≥2) 이면 단일 row/column strip.

    LIVE 검증에서 `Cat-1-Walk.png` 400×50 (8 frame), `Flying eye/Attack1.png`
    1200×150 (8 frame), `Goblin/Run.png` 등 가로 strip 들이 alpha valley
    임계 미달로 grid_detect 가 None 반환.  파일이 정수배수 사이즈이면 정사각
    frame 가정으로 sheet 로 promote.

    frame_w = frame_h = min(width, height).  cols/rows 결정.
    """
    if width <= 0 or height <= 0:
        return None
    if width == height:
        return None
    if width > height:
        if width % height != 0:
            return None
        cols = width // height
        if cols < 2:
            return None
        stride = height
        frames = [
            FrameSpec(x=i * stride, y=0, w=stride, h=stride,
                      duration_ms=0, name=str(i))
            for i in range(cols)
        ]
        return SheetDetection(frames=frames, tags=[], source="ratio_fallback")
    # height > width
    if height % width != 0:
        return None
    rows = height // width
    if rows < 2:
        return None
    stride = width
    frames = [
        FrameSpec(x=0, y=i * stride, w=stride, h=stride,
                  duration_ms=0, name=str(i))
        for i in range(rows)
    ]
    return SheetDetection(frames=frames, tags=[], source="ratio_fallback")


def detect_sheet(
    image_path: Path, *, alpha_color_weight: float = 0.5,
) -> "SheetDetection | None":
    """M6 + M11.4 + M11.10 — JSON 사이드카 → grid_detect → ratio_fallback.

    ``alpha_color_weight`` 는 grid_detect 에 그대로 전달 — Config 의 동명
    필드 값이 BatchManager / BatchPoller / SpritesheetAnalyzer 를 통해
    전파된다 (M11.4 cleanup #1).  0 이면 alpha valley 만 사용 (M6 호환).

    M11.10 — grid_detect 가 None 반환해도 width/height aspect ratio 가
    정수배수 (≥2) 이면 strip 으로 fallback promote.
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
            total_w, total_h = img.size
            layout = grid_detect(img, alpha_color_weight=alpha_color_weight)
    except (OSError, ValueError) as e:
        log.warning("sheet open failed: %s — %s", image_path, e)
        return None

    if layout is None:
        # 3) M11.10 — aspect ratio 정수배수 fallback.  alpha_color_weight=0 일
        # 때는 비활성 (M6 호환 — color-edge fallback 명시 비활성 정책 존중).
        if alpha_color_weight > 0:
            return _ratio_fallback_detect(total_w, total_h)
        return None

    # GridLayout 을 FrameSpec 시퀀스로 풀어쓴다 (균일 간격 가정)
    # M11.3 patch D-2 — FrameSpec.w/h 는 slot 크기 (stride) 사용.
    frames: list[FrameSpec] = []
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
