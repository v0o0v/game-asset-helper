"""M6 — Pillow alpha 채널 격자 추정."""
from __future__ import annotations

from PIL import Image

from gah.core.sheet.grid_detect import grid_detect
from gah.core.sheet.types import GridLayout


def _make_grid(rows: int, cols: int, frame_w: int, frame_h: int,
               gap_w: int = 2, gap_h: int = 2) -> Image.Image:
    """프레임 사이에 투명 행/열 갭을 둔 합성 이미지를 만든다."""
    total_w = cols * frame_w + (cols - 1) * gap_w
    total_h = rows * frame_h + (rows - 1) * gap_h
    img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    for r in range(rows):
        for c in range(cols):
            x = c * (frame_w + gap_w)
            y = r * (frame_h + gap_h)
            tile = Image.new("RGBA", (frame_w, frame_h), (200, 100, 50, 255))
            img.paste(tile, (x, y))
    return img


def test_horizontal_8_frames():
    img = _make_grid(rows=1, cols=8, frame_w=32, frame_h=32)
    layout = grid_detect(img)
    assert isinstance(layout, GridLayout)
    assert layout.rows == 1
    assert layout.cols == 8
    assert layout.frame_w == 32
    assert layout.frame_h == 32


def test_vertical_4_frames():
    img = _make_grid(rows=4, cols=1, frame_w=64, frame_h=32)
    layout = grid_detect(img)
    assert layout.rows == 4
    assert layout.cols == 1


def test_no_alpha_returns_none():
    img = Image.new("RGB", (128, 32), (255, 255, 255))
    assert grid_detect(img) is None


def test_nonuniform_gaps_returns_none():
    # 갭이 일관되지 않은 인공 이미지
    img = Image.new("RGBA", (100, 32), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (32, 32), (200, 100, 50, 255)), (0, 0))
    img.paste(Image.new("RGBA", (32, 32), (200, 100, 50, 255)), (35, 0))  # gap=3
    img.paste(Image.new("RGBA", (32, 32), (200, 100, 50, 255)), (75, 0))  # gap=8
    assert grid_detect(img) is None


def test_single_frame_returns_none():
    img = Image.new("RGBA", (32, 32), (200, 100, 50, 255))
    assert grid_detect(img) is None


def test_2_rows_4_cols():
    img = _make_grid(rows=2, cols=4, frame_w=16, frame_h=16)
    layout = grid_detect(img)
    assert layout.rows == 2
    assert layout.cols == 4
    assert layout.frame_w == 16
    assert layout.frame_h == 16


def test_all_transparent_returns_none():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    assert grid_detect(img) is None


def test_tiny_image_returns_none():
    img = Image.new("RGBA", (8, 8), (200, 100, 50, 255))
    assert grid_detect(img) is None


def test_padded_horizontal_2_frames():
    # 가장 작은 가로 격자
    img = _make_grid(rows=1, cols=2, frame_w=16, frame_h=16)
    layout = grid_detect(img)
    assert layout.rows == 1
    assert layout.cols == 2


def test_boundary_no_gap_works():
    # 갭 0 (프레임이 딱 붙은 경우) — alpha 가 항상 채워져서 검출 불가 → None
    img = Image.new("RGBA", (64, 32), (200, 100, 50, 255))
    assert grid_detect(img) is None
