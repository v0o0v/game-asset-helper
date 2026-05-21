"""M11.4 cleanup #1 — Config.grid_detect_alpha_color_weight 전파 wiring.

verification doc 가 한계로 표시했던 'Config 필드는 있지만 detect_sheet →
3 callers (BatchPoller / sheet_classifier / SpritesheetAnalyzer) 까지
wiring 안 됨' 을 해소한다.  각 caller 가 ``alpha_color_weight`` kwarg 를
받아 ``detect_sheet`` → ``grid_detect`` 까지 흘려보낸다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from assetcache.core.sheet import detect as detect_module
from assetcache.core.sheet.detect import detect_sheet


def _make_alpha_uniform_color_strip(path: Path) -> None:
    """alpha 균일 + 6 색 cycling — D-1 fallback 만 잡을 수 있는 시트."""
    colors = [
        (0, 255, 255), (255, 0, 255), (255, 255, 0),
        (255, 0, 0), (0, 0, 255), (0, 255, 0),
    ]
    img = Image.new("RGBA", (6 * 64, 64), (0, 0, 0, 255))
    for i, c in enumerate(colors):
        img.paste(Image.new("RGBA", (64, 64), c + (255,)), (i * 64, 0))
    img.save(path)


def test_detect_sheet_default_weight_detects_color_cycle(tmp_path: Path) -> None:
    """default weight (0.5) 에서 alpha-uniform color cycle 시트가 spritesheet 로 잡힘."""
    png = tmp_path / "elemental_cyan.png"
    _make_alpha_uniform_color_strip(png)
    detection = detect_sheet(png)
    assert detection is not None
    assert detection.source == "grid"
    assert len(detection.frames) == 6


def test_detect_sheet_weight_zero_disables_color_edge_fallback(
    tmp_path: Path,
) -> None:
    """weight=0 으로 호출하면 color-edge fallback 비활성 → None (M6 호환)."""
    png = tmp_path / "elemental_cyan.png"
    _make_alpha_uniform_color_strip(png)
    assert detect_sheet(png, alpha_color_weight=0.0) is None


def test_detect_sheet_passes_weight_to_grid_detect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """detect_sheet 의 alpha_color_weight 가 grid_detect 까지 전달된다."""
    captured: dict = {}

    def fake_grid_detect(img, *, alpha_color_weight=0.5):
        captured["weight"] = alpha_color_weight
        return None

    monkeypatch.setattr(detect_module, "grid_detect", fake_grid_detect)
    png = tmp_path / "x.png"
    _make_alpha_uniform_color_strip(png)
    detect_sheet(png, alpha_color_weight=0.25)
    assert captured["weight"] == 0.25


def test_classify_image_assets_passes_weight_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """classify_image_assets 의 alpha_color_weight 가 detect_sheet 까지 전달된다."""
    from assetcache.core.batch import sheet_classifier
    from assetcache.core.store import AssetRow

    captured: dict = {}

    def fake_detect_sheet(path, *, alpha_color_weight=0.5):
        captured["weight"] = alpha_color_weight
        return None  # sprite_rows 로만 분류, store 미호출

    monkeypatch.setattr(sheet_classifier, "detect_sheet", fake_detect_sheet)

    png = tmp_path / "x.png"
    _make_alpha_uniform_color_strip(png)
    row = AssetRow(
        id=1, pack_id=1, path="x.png", kind="sprite",
        file_hash="x" * 64, file_size=1, added_at=0,
        analyzed_at=None, analysis_state="pending",
    )
    sheet_classifier.classify_image_assets(
        [row], library_dir=tmp_path, store=None,
        alpha_color_weight=0.75,
    )
    assert captured["weight"] == 0.75


def test_spritesheet_analyzer_passes_weight_to_detect_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SpritesheetAnalyzer.analyze 의 alpha_color_weight 가 detect_sheet 까지 전달된다."""
    from assetcache.core.analyzer import spritesheet as spritesheet_module
    from assetcache.core.analyzer.base import AnalyzerInput

    captured: dict = {}

    def fake_detect_sheet(path, *, alpha_color_weight=0.5):
        captured["weight"] = alpha_color_weight
        return None  # sprite analyzer 폴백 경로로 진입

    monkeypatch.setattr(spritesheet_module, "detect_sheet", fake_detect_sheet)

    class _FakeSprite:
        def analyze(self, inp):
            return None

    analyzer = spritesheet_module.SpritesheetAnalyzer(
        sprite=_FakeSprite(),
        ollama=None,
        registry=None,
        embedder=None,
        alpha_color_weight=0.0,
    )
    png = tmp_path / "x.png"
    _make_alpha_uniform_color_strip(png)
    analyzer.analyze(AnalyzerInput(
        asset_id=1, pack_id=1, abs_path=png, rel_path="x.png", language="en",
    ))
    assert captured["weight"] == 0.0
