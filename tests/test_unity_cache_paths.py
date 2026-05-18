"""M7 — Unity Asset Store 캐시 경로 검출 우선순위 회귀."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from gah.config import Config
from gah.core.unity_import.cache_paths import detect_cache_path


def make_dir(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.mkdir()
    return p


def test_config_path_takes_priority(tmp_path, monkeypatch):
    cfg_dir = make_dir(tmp_path, "cfg-cache")
    env_dir = make_dir(tmp_path, "env-cache")
    monkeypatch.setenv("ASSETSTORE_CACHE_PATH", str(env_dir))
    cfg = Config(unity_asset_store_cache_path=str(cfg_dir))
    assert detect_cache_path(cfg) == cfg_dir


def test_env_var_used_when_no_config(tmp_path, monkeypatch):
    env_dir = make_dir(tmp_path, "env-cache")
    monkeypatch.setenv("ASSETSTORE_CACHE_PATH", str(env_dir))
    cfg = Config(unity_asset_store_cache_path=None)
    assert detect_cache_path(cfg) == env_dir


def test_default_path_when_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSETSTORE_CACHE_PATH", raising=False)
    cfg = Config(unity_asset_store_cache_path=None)
    # 기본 경로가 존재하지 않으면 None
    with patch(
        "gah.core.unity_import.cache_paths._default_cache_path",
        return_value=tmp_path / "nonexistent",
    ):
        assert detect_cache_path(cfg) is None


def test_default_path_when_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSETSTORE_CACHE_PATH", raising=False)
    default = make_dir(tmp_path, "default-cache")
    cfg = Config(unity_asset_store_cache_path=None)
    with patch(
        "gah.core.unity_import.cache_paths._default_cache_path",
        return_value=default,
    ):
        assert detect_cache_path(cfg) == default


def test_config_path_nonexistent_falls_through(tmp_path, monkeypatch):
    env_dir = make_dir(tmp_path, "env-cache")
    monkeypatch.setenv("ASSETSTORE_CACHE_PATH", str(env_dir))
    cfg = Config(unity_asset_store_cache_path=str(tmp_path / "nope"))
    assert detect_cache_path(cfg) == env_dir


def test_all_paths_invalid_returns_none(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSETSTORE_CACHE_PATH", raising=False)
    cfg = Config(unity_asset_store_cache_path=None)
    with patch(
        "gah.core.unity_import.cache_paths._default_cache_path",
        return_value=tmp_path / "nope",
    ):
        with patch(
            "gah.core.unity_import.cache_paths._unity_pref_cache_path",
            return_value=None,
        ):
            assert detect_cache_path(cfg) is None
