"""M8 — Config 신규 필드 (ui_language, ui_theme) 회귀 테스트."""
from __future__ import annotations
from pathlib import Path

from gah.config import Config, load_config, save_config


def test_config_defaults_include_ui_language_and_theme():
    cfg = Config()
    assert cfg.ui_language == "auto"
    assert cfg.ui_theme == "auto"


def test_config_serialize_and_load_roundtrip(tmp_path: Path):
    cfg = Config(ui_language="en", ui_theme="dark")
    path = tmp_path / "config.toml"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.ui_language == "en"
    assert loaded.ui_theme == "dark"


def test_config_invalid_ui_language_falls_back_to_default(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('ui_language = "klingon"\nui_theme = "dark"\n', encoding="utf-8")
    cfg = load_config(path)
    assert cfg.ui_language == "auto"  # 폴백
    assert cfg.ui_theme == "dark"  # 유효한 값은 유지


def test_config_invalid_ui_theme_falls_back_to_default(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('ui_theme = "neon"\n', encoding="utf-8")
    cfg = load_config(path)
    assert cfg.ui_theme == "auto"  # 폴백


def test_config_autostart_field_still_exists():
    # M0 부터 있는 필드 — M8 가 활용함을 회귀로 고정
    cfg = Config()
    assert cfg.autostart is False
