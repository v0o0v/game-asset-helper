"""M6 — Pillow alpha 채널 행/열 합으로 균일 격자 추정.

알파 합이 0 인 행/열을 "투명 경계" 로 보고, 경계 사이의 간격이 모두
같으면 균일 격자로 판정한다. 알파 없거나 비균일·단일 프레임·작은
이미지는 None. M6 spec §4.8.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import GridLayout

if TYPE_CHECKING:
    from PIL.Image import Image

_MIN_DIM = 16  # 16px 미만 이미지는 격자 추정 의미 없음 — 실용적 최소 스프라이트 크기


def grid_detect(img: "Image") -> GridLayout | None:
    import numpy as np

    if img.size[0] < _MIN_DIM or img.size[1] < _MIN_DIM:
        return None
    if img.mode != "RGBA":
        try:
            rgba = img.convert("RGBA")
        except (ValueError, OSError):
            return None
    else:
        rgba = img

    arr = np.asarray(rgba)
    if arr.shape[-1] != 4:
        return None
    alpha = arr[:, :, 3]

    # 알파가 전부 0 또는 전부 양수면 격자 검출 불가
    row_sums = alpha.sum(axis=1)
    col_sums = alpha.sum(axis=0)
    if int(row_sums.max()) == 0 or int(col_sums.max()) == 0:
        return None
    if int(row_sums.min()) > 0 and int(col_sums.min()) > 0:
        return None

    # 행/열 격자 추정
    cols = _split_count_from_axis(col_sums)
    rows = _split_count_from_axis(row_sums)
    if cols < 1 or rows < 1:
        return None
    if rows == 1 and cols == 1:
        return None

    frame_w = _uniform_frame_size(col_sums, cols)
    frame_h = _uniform_frame_size(row_sums, rows)
    if frame_w is None or frame_h is None:
        return None

    return GridLayout(rows=rows, cols=cols, frame_w=frame_w, frame_h=frame_h)


def _split_count_from_axis(sums) -> int:
    """투명 경계로 분리된 프레임 수를 센다.

    경계 = 합이 0 인 연속 구간. 프레임 = 합이 > 0 인 연속 구간.
    """
    in_frame = False
    count = 0
    for v in sums:
        if int(v) > 0:
            if not in_frame:
                count += 1
                in_frame = True
        else:
            in_frame = False
    return count


def _uniform_frame_size(sums, count: int) -> int | None:
    """프레임 길이가 모두 같으면 그 길이를, 아니면 None."""
    lengths: list[int] = []
    current = 0
    for v in sums:
        if int(v) > 0:
            current += 1
        else:
            if current > 0:
                lengths.append(current)
            current = 0
    if current > 0:
        lengths.append(current)
    if len(lengths) != count:
        return None
    if not lengths:
        return None
    first = lengths[0]
    if all(l == first for l in lengths):
        return int(first)
    return None
