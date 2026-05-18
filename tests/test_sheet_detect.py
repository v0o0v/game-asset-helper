"""M6 — sheet detection 오케스트레이션 (JSON 사이드카 → grid → None)."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from gah.core.sheet.detect import SheetDetection, detect_sheet

FIXTURES = Path(__file__).parent / "fixtures" / "sheets"


def _save_sheet_png(path: Path, frame_count: int, fw: int = 32, fh: int = 32,
                    gap: int = 2) -> None:
    total_w = frame_count * fw + (frame_count - 1) * gap
    img = Image.new("RGBA", (total_w, fh), (0, 0, 0, 0))
    for i in range(frame_count):
        tile = Image.new("RGBA", (fw, fh), (200, 100, 50, 255))
        img.paste(tile, (i * (fw + gap), 0))
    img.save(path)


def test_json_sidecar_preferred(tmp_path):
    # PNG + JSON 모두 있으면 JSON 사용 (frames 가 JSON 기준)
    png = tmp_path / "hero_walk_aseprite_array.png"
    json_src = FIXTURES / "hero_walk_aseprite_array.json"
    _save_sheet_png(png, frame_count=8)
    shutil.copy(json_src, tmp_path / "hero_walk_aseprite_array.json")

    detection = detect_sheet(png)
    assert detection is not None
    assert detection.source == "json"
    assert len(detection.frames) == 8
    assert len(detection.tags) == 1


def test_grid_fallback_when_no_json(tmp_path):
    png = tmp_path / "slime.png"
    _save_sheet_png(png, frame_count=4)
    detection = detect_sheet(png)
    assert detection is not None
    assert detection.source == "grid"
    assert len(detection.frames) == 4
    assert detection.tags == []


def test_returns_none_when_no_json_and_no_grid(tmp_path):
    # 단일 프레임 — JSON 없음, grid 검출 불가
    png = tmp_path / "sword.png"
    Image.new("RGBA", (32, 32), (200, 100, 50, 255)).save(png)
    assert detect_sheet(png) is None


def test_sidecar_path_naming(tmp_path):
    # png 와 같은 이름의 .json
    png = tmp_path / "abc.png"
    json_path = tmp_path / "abc.json"
    _save_sheet_png(png, frame_count=8)
    shutil.copy(FIXTURES / "hero_walk_aseprite_array.json", json_path)
    detection = detect_sheet(png)
    assert detection is not None
    assert detection.source == "json"


def test_invalid_image_returns_none(tmp_path):
    # PNG 아닌 파일 — Pillow open 실패
    p = tmp_path / "junk.bin"
    p.write_bytes(b"not a real image")
    assert detect_sheet(p) is None


def test_sheet_detection_dataclass_fields():
    sd = SheetDetection(frames=[], tags=[], source="grid")
    assert sd.frames == []
    assert sd.tags == []
    assert sd.source == "grid"
