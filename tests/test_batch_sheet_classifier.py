"""M11.2 — classify_image_assets: detect_sheet → sheet/sprite 분리 + kind promote."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from assetcache.core.batch.sheet_classifier import classify_image_assets
from assetcache.core.sheet.detect import SheetDetection


def _png(library: Path, rel: str, *, size=(64, 32)) -> Path:
    p = library / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (0, 0, 0, 0)).save(p)
    return p


def _aseprite_sidecar(library: Path, rel: str, *, frame_w, frame_h, count, tags):
    frames = {
        f"f_{i}": {
            "frame": {"x": i * frame_w, "y": 0, "w": frame_w, "h": frame_h},
            "duration": 83,
        }
        for i in range(count)
    }
    frame_tags = [
        {"name": n, "from": s, "to": e, "direction": "forward"}
        for n, s, e in tags
    ]
    (library / rel).write_text(
        json.dumps({"frames": frames, "meta": {"frameTags": frame_tags}}),
        encoding="utf-8",
    )


def _row(*, id: int, path: str, kind: str = "sprite"):
    r = MagicMock()
    r.id = id
    r.path = path
    r.kind = kind
    return r


def test_classify_aseprite_sheet_returns_sheet_result_and_promotes(tmp_path):
    _png(tmp_path, "pack/hero.png", size=(128, 32))
    _aseprite_sidecar(
        tmp_path, "pack/hero.json",
        frame_w=32, frame_h=32, count=4, tags=[("idle", 0, 3)],
    )
    rows = [_row(id=1, path="pack/hero.png")]
    store = MagicMock()
    sheet_results, sprite_rows = classify_image_assets(
        rows, library_dir=tmp_path, store=store,
    )
    assert len(sheet_results) == 1
    assert len(sprite_rows) == 0
    row, det = sheet_results[0]
    assert row.id == 1
    assert isinstance(det, SheetDetection)
    assert det.source == "json"
    store.update_asset_kind.assert_called_once_with(1, "spritesheet")


def test_classify_grid_only_sheet_promotes_without_frame_tags(tmp_path):
    """JSON 사이드카 없는 격자 시트 — grid_detect hit → promote, tags 비어 있음."""
    fw, fh = 32, 32
    img = Image.new("RGBA", (fw * 4, fh), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    for i in range(4):
        draw.rectangle(
            [i * fw + 4, 4, i * fw + fw - 4, fh - 4],
            fill=(255, 0, 0, 255),
        )
    p = tmp_path / "pack/grid.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)

    rows = [_row(id=10, path="pack/grid.png")]
    store = MagicMock()
    sheet_results, sprite_rows = classify_image_assets(
        rows, library_dir=tmp_path, store=store,
    )
    # grid_detect hit 면 sheet, miss 면 sprite — 양쪽 모두 valid
    if sheet_results:
        assert sprite_rows == []
        store.update_asset_kind.assert_called_once_with(10, "spritesheet")
        _, det = sheet_results[0]
        assert det.source == "grid"
        assert det.tags == []
    else:
        assert len(sprite_rows) == 1
        store.update_asset_kind.assert_not_called()


def test_classify_non_sheet_returns_sprite_only(tmp_path):
    """단일 sprite (시트 아님) → sprite_rows 만, promote 호출 안 함."""
    _png(tmp_path, "pack/single.png", size=(32, 32))
    rows = [_row(id=20, path="pack/single.png")]
    store = MagicMock()
    sheet_results, sprite_rows = classify_image_assets(
        rows, library_dir=tmp_path, store=store,
    )
    assert sheet_results == []
    assert len(sprite_rows) == 1
    assert sprite_rows[0].id == 20
    store.update_asset_kind.assert_not_called()


def test_classify_io_error_falls_through_as_sprite(tmp_path):
    """파일이 없는 row → 예외 삼키고 sprite 로 분류."""
    rows = [_row(id=30, path="pack/missing.png")]
    store = MagicMock()
    sheet_results, sprite_rows = classify_image_assets(
        rows, library_dir=tmp_path, store=store,
    )
    assert sheet_results == []
    assert len(sprite_rows) == 1
    store.update_asset_kind.assert_not_called()


def test_classify_mixed_batch_separates_correctly(tmp_path):
    """시트 + sprite 혼합 입력 → 각각 올바르게 분리."""
    _png(tmp_path, "pack/sheet.png", size=(128, 32))
    _aseprite_sidecar(
        tmp_path, "pack/sheet.json",
        frame_w=32, frame_h=32, count=4, tags=[("walk", 0, 3)],
    )
    _png(tmp_path, "pack/single.png", size=(32, 32))
    rows = [
        _row(id=1, path="pack/sheet.png"),
        _row(id=2, path="pack/single.png"),
    ]
    store = MagicMock()
    sheet_results, sprite_rows = classify_image_assets(
        rows, library_dir=tmp_path, store=store,
    )
    assert len(sheet_results) == 1 and sheet_results[0][0].id == 1
    assert len(sprite_rows) == 1 and sprite_rows[0].id == 2
    store.update_asset_kind.assert_called_once_with(1, "spritesheet")


def test_classify_preserves_input_order_per_bucket(tmp_path):
    """입력 순서가 각 버킷 내에서 보존돼야."""
    for i in range(3):
        _png(tmp_path, f"pack/s{i}.png", size=(32, 32))
    rows = [_row(id=i, path=f"pack/s{i}.png") for i in range(3)]
    store = MagicMock()
    sheet_results, sprite_rows = classify_image_assets(
        rows, library_dir=tmp_path, store=store,
    )
    assert [r.id for r in sprite_rows] == [0, 1, 2]


def test_classify_library_dir_none_returns_all_as_sprite(tmp_path):
    """library_dir=None 이면 분류 skip — 모두 sprite_rows 로 반환."""
    rows = [_row(id=i, path=f"x{i}.png") for i in range(3)]
    store = MagicMock()
    sheet_results, sprite_rows = classify_image_assets(
        rows, library_dir=None, store=store,
    )
    assert sheet_results == []
    assert [r.id for r in sprite_rows] == [0, 1, 2]
    store.update_asset_kind.assert_not_called()
