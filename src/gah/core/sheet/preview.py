"""M6 — 8칸 1행 합성 미리보기.

≤8 프레임은 그대로, >8 은 선형 stride 샘플링 8개로 합성. max_size 로
긴 변 다운스케일. M6 spec §4.4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image
    from .types import FrameSpec

_PREVIEW_FRAME_COUNT = 8


def sample_indices(total: int, k: int = _PREVIEW_FRAME_COUNT) -> list[int]:
    """0..total-1 에서 균등 간격 k 개 인덱스.

    total ≤ k 이면 0..total-1 모두 반환. 그렇지 않으면 선형 stride
    ``round(i * (total - 1) / (k - 1))`` 로 k 개 선택.
    """
    if total <= 0 or k <= 0:
        return []
    if total <= k:
        return list(range(total))
    if k == 1:
        # Sentinel — 단일 샘플은 항상 첫 프레임 (formula 가 0 나눗셈)
        return [0]
    return [round(i * (total - 1) / (k - 1)) for i in range(k)]


def make_preview_composite(
    img: "Image",
    frames: "list[FrameSpec]",
    *,
    max_size: int = 768,
) -> "Image":
    """frames 의 일부(또는 전부) 를 가로 1행으로 합성한 미리보기."""
    from PIL import Image as _PILImage

    if not frames:
        return img.copy()

    idxs = sample_indices(len(frames), _PREVIEW_FRAME_COUNT)
    selected = [frames[i] for i in idxs]
    fw, fh = selected[0].w, selected[0].h
    total_w = fw * len(selected)
    composite = _PILImage.new("RGBA", (total_w, fh), (0, 0, 0, 0))
    rgba = img.convert("RGBA") if img.mode != "RGBA" else img
    for i, f in enumerate(selected):
        tile = rgba.crop((f.x, f.y, f.x + f.w, f.y + f.h))
        if tile.size != (fw, fh):
            tile = tile.resize((fw, fh), _PILImage.LANCZOS)
        composite.paste(tile, (i * fw, 0))

    if max(composite.size) > max_size:
        scale = max_size / max(composite.size)
        new_size = (max(1, int(composite.size[0] * scale)),
                    max(1, int(composite.size[1] * scale)))
        composite = composite.resize(new_size, _PILImage.LANCZOS)
    return composite
