"""M11.4 D-1 — alpha 균일 + color-cycling 시트의 격자 검출.

M11.3 LIVE 검증 v2 에서 `elemental_cyan` (1×6 64×64) 가 alpha 모든 픽셀
255 + 색만 frame 마다 cycling 이라 ``grid_detect`` alpha-valley 알고리즘이
경계를 찾지 못해 sprite 로 오분류된 한계를 잡는다.  M11.4 는 인접
column/row 의 RGB diff (= color edge) 의 peak 를 frame 경계 후보로
사용해 alpha-uniform 시트도 spritesheet 로 인식한다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from assetcache.core.sheet.grid_detect import grid_detect
from assetcache.core.sheet.types import GridLayout


def _make_color_strip(
    colors: list[tuple[int, int, int]], frame_w: int, frame_h: int,
) -> Image.Image:
    """1행 N열의 단색 frame strip — alpha 모든 픽셀 255, 색만 cycling."""
    total_w = len(colors) * frame_w
    img = Image.new("RGBA", (total_w, frame_h), (0, 0, 0, 255))
    for i, color in enumerate(colors):
        tile = Image.new("RGBA", (frame_w, frame_h), color + (255,))
        img.paste(tile, (i * frame_w, 0))
    return img


def _make_color_grid(
    colors_2d: list[list[tuple[int, int, int]]], frame_w: int, frame_h: int,
) -> Image.Image:
    """rows × cols color grid — alpha 모든 픽셀 255, 색만 cycling."""
    rows = len(colors_2d)
    cols = len(colors_2d[0])
    img = Image.new("RGBA", (cols * frame_w, rows * frame_h), (0, 0, 0, 255))
    for r, row in enumerate(colors_2d):
        for c, color in enumerate(row):
            tile = Image.new("RGBA", (frame_w, frame_h), color + (255,))
            img.paste(tile, (c * frame_w, r * frame_h))
    return img


def test_elemental_cyan_like_1x6_64px() -> None:
    """alpha 균일 + 6 색 cycling — M11.3 D-1 한계 재현."""
    colors = [
        (0, 255, 255), (255, 0, 255), (255, 255, 0),
        (255, 0, 0), (0, 0, 255), (0, 255, 0),
    ]
    img = _make_color_strip(colors, frame_w=64, frame_h=64)
    layout = grid_detect(img)
    assert isinstance(layout, GridLayout)
    assert layout.rows == 1
    assert layout.cols == 6
    assert layout.frame_w == 64
    assert layout.frame_h == 64


def test_color_cycling_2x3_grid() -> None:
    """2 × 3 color-cycling grid — 양축 color-edge 검출."""
    colors_2d = [
        [(255, 0, 0), (0, 255, 0), (0, 0, 255)],
        [(255, 255, 0), (0, 255, 255), (255, 0, 255)],
    ]
    img = _make_color_grid(colors_2d, frame_w=32, frame_h=32)
    layout = grid_detect(img)
    assert isinstance(layout, GridLayout)
    assert layout.rows == 2
    assert layout.cols == 3
    assert layout.frame_w == 32
    assert layout.frame_h == 32


def test_color_cycling_with_centered_orb() -> None:
    """frame 중앙에 동일 위치 orb + 배경 색 cycling — elemental_cyan 실 구조."""
    colors = [
        (0, 200, 200), (200, 0, 200), (200, 200, 0),
        (200, 0, 0), (0, 0, 200), (0, 200, 0),
    ]
    frame_w, frame_h = 64, 64
    img = Image.new("RGBA", (len(colors) * frame_w, frame_h), (0, 0, 0, 255))
    for i, bg in enumerate(colors):
        tile = Image.new("RGBA", (frame_w, frame_h), bg + (255,))
        draw = ImageDraw.Draw(tile)
        draw.ellipse((22, 22, 42, 42), fill=(255, 255, 255, 255))
        img.paste(tile, (i * frame_w, 0))
    layout = grid_detect(img)
    assert isinstance(layout, GridLayout)
    assert layout.rows == 1
    assert layout.cols == 6
    assert layout.frame_w == 64


def test_weight_zero_disables_color_edge() -> None:
    """alpha_color_weight=0 이면 color-edge 비활성 — M6 호환 모드."""
    colors = [
        (0, 255, 255), (255, 0, 255), (255, 255, 0),
        (255, 0, 0), (0, 0, 255), (0, 255, 0),
    ]
    img = _make_color_strip(colors, frame_w=64, frame_h=64)
    assert grid_detect(img, alpha_color_weight=0.0) is None


def test_solid_color_no_false_positive() -> None:
    """단색 단일 frame — color edge 도 없음 → None 유지."""
    img = Image.new("RGBA", (128, 64), (100, 150, 200, 255))
    assert grid_detect(img) is None


def test_uniform_noise_no_false_positive() -> None:
    """alpha 균일 + 랜덤 RGB noise (단일 frame 복잡 art) — 등간격 peak 없음."""
    import random
    rng = random.Random(42)
    img = Image.new("RGBA", (128, 64), (0, 0, 0, 255))
    pixels = img.load()
    for y in range(64):
        for x in range(128):
            pixels[x, y] = (
                rng.randint(0, 255),
                rng.randint(0, 255),
                rng.randint(0, 255),
                255,
            )
    assert grid_detect(img) is None


def test_alpha_path_still_works_unchanged() -> None:
    """기존 alpha-gutter 시트 — alpha 경로가 우선이라 동일 결과 보장."""
    total_w = 4 * 32 + 3 * 2  # 4 frames 32px + 3 gaps 2px
    img = Image.new("RGBA", (total_w, 32), (0, 0, 0, 0))
    for i in range(4):
        tile = Image.new("RGBA", (32, 32), (200, 100, 50, 255))
        img.paste(tile, (i * (32 + 2), 0))
    layout = grid_detect(img)
    assert isinstance(layout, GridLayout)
    assert layout.rows == 1
    assert layout.cols == 4
    assert layout.frame_w == 32


def test_config_has_grid_detect_alpha_color_weight() -> None:
    """Config 에 신규 D-1 toggle 필드가 default 0.5 로 존재 + round-trip."""
    from assetcache.config import Config

    cfg = Config()
    assert cfg.grid_detect_alpha_color_weight == 0.5


def test_config_round_trip_alpha_color_weight(tmp_path) -> None:
    """config.toml 저장/로드 사이에 D-1 toggle 값이 유지된다."""
    from assetcache.config import Config, load_config, save_config

    path = tmp_path / "c.toml"
    cfg = Config()
    cfg.grid_detect_alpha_color_weight = 0.0
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.grid_detect_alpha_color_weight == 0.0
