"""Tests for gah.config — paths and TOML configuration."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_default_app_paths_uses_env_override(tmp_appdata: Path) -> None:
    """When GAH_DATA_DIR is set, every AppPath should live underneath it."""
    from gah.config import default_app_paths

    paths = default_app_paths()
    assert paths.data_dir == tmp_appdata
    assert paths.library_dir == tmp_appdata / "library"
    assert paths.cache_dir == tmp_appdata / "cache"
    assert paths.db_path == tmp_appdata / "metadata.db"
    assert paths.config_path == tmp_appdata / "config.toml"
    assert paths.log_path == tmp_appdata / "logs" / "gah.log"


def test_paths_are_created_idempotently(tmp_appdata: Path) -> None:
    """ensure_dirs must be idempotent and create the expected hierarchy."""
    from gah.config import default_app_paths

    paths = default_app_paths()
    paths.ensure_dirs()
    paths.ensure_dirs()  # second call must not raise

    assert paths.data_dir.is_dir()
    assert paths.library_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.log_path.parent.is_dir()


def test_load_config_creates_file_when_missing(tmp_appdata: Path) -> None:
    """Missing config.toml should be created with defaults."""
    from gah.config import default_app_paths, load_config

    paths = default_app_paths()
    paths.ensure_dirs()
    assert not paths.config_path.exists()

    cfg = load_config(paths.config_path)
    assert paths.config_path.exists()
    # default sentinel values from the spec
    assert cfg.ollama_url == "http://127.0.0.1:11434"
    assert cfg.model_image == "gemma4:e4b"
    assert cfg.mcp_port == 9874
    assert 0.0 <= cfg.consistency_weight <= 1.0


def test_load_config_reads_existing_values(tmp_appdata: Path) -> None:
    """Existing TOML must override defaults precisely."""
    from gah.config import default_app_paths, load_config

    paths = default_app_paths()
    paths.ensure_dirs()
    paths.config_path.write_text(
        '\n'.join([
            'ollama_url = "http://10.0.0.5:11434"',
            'model_image = "gemma4:e2b"',
            'mcp_port = 12345',
            'consistency_weight = 0.42',
            'autostart = true',
        ]),
        encoding="utf-8",
    )

    cfg = load_config(paths.config_path)
    assert cfg.ollama_url == "http://10.0.0.5:11434"
    assert cfg.model_image == "gemma4:e2b"
    assert cfg.mcp_port == 12345
    assert cfg.consistency_weight == pytest.approx(0.42)
    assert cfg.autostart is True


def test_save_and_reload_roundtrip(tmp_appdata: Path) -> None:
    from gah.config import Config, default_app_paths, load_config, save_config

    paths = default_app_paths()
    paths.ensure_dirs()

    cfg = Config(
        ollama_url="http://localhost:11434",
        model_image="gemma4:e4b",
        model_audio="gemma4:e4b",
        model_embed="nomic-embed-text",
        mcp_port=9999,
        consistency_weight=0.25,
        autostart=False,
    )
    save_config(cfg, paths.config_path)
    reloaded = load_config(paths.config_path)
    assert reloaded == cfg


def test_corrupt_toml_is_backed_up_and_defaults_used(tmp_appdata: Path) -> None:
    from gah.config import default_app_paths, load_config

    paths = default_app_paths()
    paths.ensure_dirs()
    paths.config_path.write_text("this is = not valid !! toml ===", encoding="utf-8")

    cfg = load_config(paths.config_path)
    backup = paths.config_path.with_suffix(".toml.bak")
    assert backup.exists(), "corrupt config should be moved aside as .bak"
    # a fresh config.toml should now exist with default values
    assert cfg.ollama_url == "http://127.0.0.1:11434"
