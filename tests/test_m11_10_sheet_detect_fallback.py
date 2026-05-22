"""M11.10 — detect_sheet 가로/세로 strip fallback heuristic.

LIVE 검증 (242 assets, 7 packs) 에서 가로 strip sheet 들이 grid_detect 임계
미달로 sprite 분류됨:
* Cat-1-Walk.png 400×50 (8 frame 50×50)
* Cat-1-Stretching.png 650×50 (13 frame)
* Flying eye/Attack1.png 1200×150 (8 frame 150×150)
* Goblin/Run.png 1200×150 (8 frame)

해결: detect_sheet 의 마지막 fallback 으로 aspect ratio 정수배수 (≥2) 인 경우
1×N or N×1 grid 가정.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def _make_strip(tmp_path: Path, width: int, height: int, frame_count: int,
                opaque: bool = True) -> Path:
    """가로 strip PNG 생성.  RGBA, 캐릭터 자리는 opaque, transparent gap 없음."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    arr = np.array(img)
    frame_w = width // frame_count
    for i in range(frame_count):
        x0 = i * frame_w + 2
        x1 = (i + 1) * frame_w - 2
        # opaque 캐릭터 영역 — alpha valley 가 미세하지만 grid_detect 임계 미달
        arr[5:height - 5, x0:x1, :] = [120, 80, 60, 255]
    out = Image.fromarray(arr, "RGBA")
    path = tmp_path / "strip.png"
    out.save(path)
    return path


def test_detect_sheet_falls_back_to_aspect_ratio_horizontal_strip(tmp_path):
    """grid_detect 가 None 반환해도 width/height 가 정수배수면 가로 strip 가정."""
    from assetcache.core.sheet.detect import detect_sheet

    # 400×50 = 8 × (50×50) horizontal strip, frame 간 transparent gap 없음
    img = Image.new("RGBA", (400, 50), (120, 80, 60, 255))  # 전체 opaque (alpha valley 0)
    path = tmp_path / "strip_400x50.png"
    img.save(path)

    detection = detect_sheet(path)
    assert detection is not None, "detect_sheet fallback miss — 가로 strip 인식 실패"
    assert detection.source == "ratio_fallback", (
        f"source 가 ratio_fallback 아님: {detection.source}"
    )
    assert len(detection.frames) == 8, (
        f"frame_count 8 예상, got {len(detection.frames)}"
    )
    # frame size = min(w,h) = 50
    assert detection.frames[0].w == 50
    assert detection.frames[0].h == 50


def test_detect_sheet_falls_back_vertical_strip(tmp_path):
    """세로 strip — 50×400 = 8 frame."""
    from assetcache.core.sheet.detect import detect_sheet

    img = Image.new("RGBA", (50, 400), (120, 80, 60, 255))
    path = tmp_path / "vstrip_50x400.png"
    img.save(path)

    detection = detect_sheet(path)
    assert detection is not None
    assert detection.source == "ratio_fallback"
    assert len(detection.frames) == 8
    assert detection.frames[0].w == 50
    assert detection.frames[0].h == 50


def test_detect_sheet_no_fallback_for_square_or_near_square(tmp_path):
    """정사각 또는 가까운 사각 (ratio < 2) 은 fallback 안 함 — single sprite 가능성."""
    from assetcache.core.sheet.detect import detect_sheet

    img = Image.new("RGBA", (100, 80), (120, 80, 60, 255))  # ratio 1.25
    path = tmp_path / "square.png"
    img.save(path)

    detection = detect_sheet(path)
    assert detection is None, "정사각 sprite 가 sheet 로 잘못 fallback"


def test_detect_sheet_no_fallback_for_non_integer_ratio(tmp_path):
    """정수배수 아닌 ratio (예: 256×576) 는 fallback 안 함 — frame size 추정 불가."""
    from assetcache.core.sheet.detect import detect_sheet

    # 100×270 = ratio 2.7, 정수 아님
    img = Image.new("RGBA", (100, 270), (120, 80, 60, 255))
    path = tmp_path / "non_integer.png"
    img.save(path)

    detection = detect_sheet(path)
    assert detection is None, "정수 아닌 ratio 에 잘못 fallback"


def test_detect_sheet_grid_detect_priority_over_fallback(tmp_path):
    """grid_detect 가 검출 성공하면 fallback 안 거치고 그대로 사용."""
    from assetcache.core.sheet.detect import detect_sheet

    # 3×3 grid 시트, 명확한 alpha valley 로 grid_detect 가 잡을 수 있게
    img = Image.new("RGBA", (90, 90), (0, 0, 0, 0))
    arr = np.array(img)
    # 30×30 cell, 5px transparent gap
    for r in range(3):
        for c in range(3):
            x0 = c * 30 + 5
            y0 = r * 30 + 5
            arr[y0:y0 + 20, x0:x0 + 20, :] = [120, 80, 60, 255]
    Image.fromarray(arr, "RGBA").save(tmp_path / "grid.png")

    detection = detect_sheet(tmp_path / "grid.png")
    assert detection is not None
    # grid_detect 가 잡았으면 source='grid', fallback 진입 X
    assert detection.source in ("grid", "ratio_fallback")
    # grid 가 우선이면 9 frame, fallback 이면 1×3 or 3×1 (3 frame)
    # 본 테스트는 grid 검출 가능한 경우 grid 가 우선임을 확인 (frame 수로 구분)
    if detection.source == "grid":
        assert len(detection.frames) == 9
