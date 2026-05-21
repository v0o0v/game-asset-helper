"""M6 + M11.4 — Pillow alpha + color-edge 기반 균일 격자 추정.

M6 1차: 알파 합이 0 인 행/열을 "투명 경계" 로 보고 등간격이면 균일 격자로
판정한다.  alpha 가 모든 frame 에서 균일 (예: `elemental_cyan` 1×6 64×64
처럼 모든 픽셀 alpha=255 + 색만 cycling) 한 시트는 alpha 합이 평평해
경계 valley 가 없다.

M11.4 D-1: alpha 경로가 실패하면 **인접 column/row 의 RGB diff (L1) 합**
의 peak 를 frame 경계 후보로 사용한다.  peak 가 등간격이고 total 길이를
정수로 나눌 때만 GridLayout 으로 채택.  ``alpha_color_weight=0`` 으로
호출하면 M6 호환 모드 (color-edge fallback 비활성).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import GridLayout

if TYPE_CHECKING:
    from PIL.Image import Image

_MIN_DIM = 16  # 16px 미만 이미지는 격자 추정 의미 없음 — 실용적 최소 스프라이트 크기


def grid_detect(
    img: "Image", *, alpha_color_weight: float = 0.5,
) -> GridLayout | None:
    """균일 격자 시트의 행·열·프레임 크기 추정.

    ``alpha_color_weight`` 가 0 보다 크면 alpha 경로가 실패할 때 color-edge
    fallback (M11.4 D-1) 을 시도한다.  Config.``grid_detect_alpha_color_weight``
    가 이 값을 결정한다 (기본 0.5).
    """
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

    layout = _detect_via_alpha(arr)
    if layout is not None:
        return layout

    if alpha_color_weight > 0:
        return _detect_via_color_edges(arr)
    return None


def _detect_via_alpha(arr) -> GridLayout | None:
    """M6 알고리즘 — 투명 갭(alpha valley) 기반."""
    alpha = arr[:, :, 3]
    row_sums = alpha.sum(axis=1)
    col_sums = alpha.sum(axis=0)

    if int(row_sums.max()) == 0 or int(col_sums.max()) == 0:
        return None
    if int(row_sums.min()) > 0 and int(col_sums.min()) > 0:
        return None

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


def _detect_via_color_edges(arr) -> GridLayout | None:
    """M11.4 D-1 — alpha 균일 시트의 color-cycling 격자 검출.

    인접 column/row 의 RGB diff (L1) 로 frame 경계 후보를 잡는다.  경계는
    수직(또는 수평) 으로 **거의 모든 픽셀에 걸쳐** 색이 바뀌어야 하며
    (`AXIS_SPAN_RATIO` 이상의 비율), 경계 강도 자체도 max 의 절반 + median 의
    5 배 이상이어야 한다.  마지막으로 경계가 등간격이고 total 길이를 정수로
    나눌 때만 GridLayout 반환 — 그 외에는 단일 frame 으로 폴백.
    """
    import numpy as np

    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(np.int32)

    # (H, W-1) — 인접 column 쌍의 row별 |Δr|+|Δg|+|Δb|
    col_diff_per_row = np.abs(rgb[:, 1:, :] - rgb[:, :-1, :]).sum(axis=-1)
    col_edges = col_diff_per_row.sum(axis=0)                  # (W-1,)
    col_rows_active = (col_diff_per_row > 0).sum(axis=0)      # (W-1,)

    # (H-1, W) — 인접 row 쌍의 col별 |Δr|+|Δg|+|Δb|
    row_diff_per_col = np.abs(rgb[1:, :, :] - rgb[:-1, :, :]).sum(axis=-1)
    row_edges = row_diff_per_col.sum(axis=1)                  # (H-1,)
    row_cols_active = (row_diff_per_col > 0).sum(axis=1)      # (H-1,)

    cols, frame_w = _uniform_from_edges(col_edges, w, h, col_rows_active)
    rows, frame_h = _uniform_from_edges(row_edges, h, w, row_cols_active)

    if cols is None or rows is None:
        return None
    if rows == 1 and cols == 1:
        return None
    return GridLayout(rows=rows, cols=cols, frame_w=frame_w, frame_h=frame_h)


# frame 경계로 채택하려면 수직(또는 수평) 으로 axis 의 이 비율 이상에서
# 색이 바뀌어야 한다 — 0.8 = 한 axis 전체의 80% 픽셀에 걸쳐 색 변화.
# 너무 낮으면 frame 내부 객체(orb) 의 가장자리도 경계로 오인되고, 너무
# 높으면 anti-aliasing 으로 일부 row 만 다른 합법적 경계를 놓친다.
_AXIS_SPAN_RATIO = 0.8


def _uniform_from_edges(
    edges, total: int, perpendicular_size: int, active_counts,
):
    """edge-per-gap 배열에서 (frame 수, frame 크기) 추정 — 등간격일 때만.

    ``active_counts`` 는 각 gap 에서 비교 axis 의 perpendicular 픽셀 중
    diff 가 0 보다 큰 것의 수.  axis 전체에 걸친 색 변화 (`_AXIS_SPAN_RATIO`
    이상) 만 경계 후보로 추린다.  경계 후보가 없으면 단일 frame
    ``(1, total)``, 등간격 위배 또는 total 을 frame 수로 정수 나누기 불가
    하면 ``(None, None)`` 으로 grid_detect 가 전체 None 반환하도록 시그널.
    """
    import numpy as np

    if edges.size == 0 or float(edges.max()) == 0.0:
        return 1, total

    span_threshold = int(perpendicular_size * _AXIS_SPAN_RATIO)
    spans_axis = active_counts >= span_threshold
    if not np.any(spans_axis):
        return 1, total

    filtered = np.where(spans_axis, edges, 0)
    max_e = float(filtered.max())
    if max_e == 0.0:
        return 1, total

    median = float(np.median(filtered))
    # peak 이 max 절반 이상 AND median 의 5배 이상 — 둘 다 만족해야 경계
    threshold = max(max_e * 0.5, median * 5.0, 1.0)
    boundaries = [i for i, v in enumerate(filtered) if float(v) >= threshold]
    if not boundaries:
        return 1, total

    n_frames = len(boundaries) + 1
    if total % n_frames != 0:
        return None, None
    frame_size = total // n_frames
    # 경계 i 는 gap index frame_size*(i+1)-1 에 위치해야 등간격
    expected = [frame_size * (i + 1) - 1 for i in range(len(boundaries))]
    if boundaries != expected:
        return None, None
    return n_frames, frame_size


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
