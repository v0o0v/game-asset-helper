"""Phase 3 task 3.7 — BatchConfig + TOML migration."""

from pathlib import Path

import pytest


def test_batch_config_default():
    from assetcache.config import Config
    cfg = Config()
    assert cfg.batch.threshold == 30
    assert cfg.batch.poll_interval_seconds == 1800
    assert cfg.batch.expiry_grace_seconds == 172800
    assert cfg.batch.toggle == "auto"


def test_batch_config_round_trip(tmp_path):
    from assetcache.config import load_config, save_config, Config, BatchConfig
    path = tmp_path / "config.toml"
    cfg = Config()
    cfg.batch = BatchConfig(
        threshold=50, poll_interval_seconds=600,
        expiry_grace_seconds=100000, toggle="forced_on",
    )
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.batch.threshold == 50
    assert loaded.batch.poll_interval_seconds == 600
    assert loaded.batch.expiry_grace_seconds == 100000
    assert loaded.batch.toggle == "forced_on"


def test_batch_config_missing_section_uses_default(tmp_path):
    """기존 config.toml 에 [batch] 없으면 default 적용."""
    from assetcache.config import load_config
    path = tmp_path / "c.toml"
    path.write_text("[backends.ollama]\nenabled = true\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.batch.threshold == 30
    assert cfg.batch.toggle == "auto"
