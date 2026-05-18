"""M7 — Config 신규 5 필드 + backward compat 회귀."""
from __future__ import annotations

from pathlib import Path

from gah.config import Config, load_config, save_config


def test_config_defaults_for_new_fields():
    cfg = Config()
    assert cfg.unity_asset_store_cache_path is None
    assert cfg.unity_remote_optin_enabled is False
    assert cfg.unity_remote_optin_session is None
    assert cfg.active_project_id is None
    assert cfg.preference_usage_weight == 0.1


def test_config_round_trip(tmp_path: Path):
    cfg = Config(
        unity_asset_store_cache_path="C:/U/A",
        unity_remote_optin_enabled=True,
        unity_remote_optin_session="abc",
        active_project_id=42,
        preference_usage_weight=0.25,
    )
    p = tmp_path / "config.toml"
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.unity_asset_store_cache_path == "C:/U/A"
    assert loaded.unity_remote_optin_enabled is True
    assert loaded.active_project_id == 42
    assert loaded.preference_usage_weight == 0.25


def test_config_backward_compat_legacy_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text("# legacy config from M6\nlog_level = \"INFO\"\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.active_project_id is None
    assert cfg.preference_usage_weight == 0.1


def test_config_active_project_optional(tmp_path: Path):
    cfg = Config(active_project_id=None)
    save_config(cfg, tmp_path / "c.toml")
    loaded = load_config(tmp_path / "c.toml")
    assert loaded.active_project_id is None


def test_config_partial_load(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(
        '[unity]\nunity_remote_optin_enabled = true\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    # 부분 로드 = 알 수 없는 섹션/키는 무시. 신규 필드는 기본값 fallback.
    assert cfg.active_project_id is None
