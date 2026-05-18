"""M7 — Unity Asset Store 캐시 경로 검출 (D3).

우선순위:
  1. Config.unity_asset_store_cache_path (사용자가 설정에서 입력)
  2. env ASSETSTORE_CACHE_PATH
  3. Unity Editor Preferences (assetStoreCacheLocation) — v1 minimal: None
  4. %APPDATA%/Unity/Asset Store-5.x/ (Windows 기본)

각 단계에서 존재하지 않는 경로는 폴백.
"""

from __future__ import annotations

import os
from pathlib import Path

from gah.config import Config


def detect_cache_path(config: Config) -> Path | None:
    """우선순위대로 캐시 경로 검출. 모두 실패하면 None."""
    candidates = [
        _from_config(config),
        _from_env(),
        _unity_pref_cache_path(),
        _default_cache_path(),
    ]
    for p in candidates:
        if p is not None and p.is_dir():
            return p
    return None


def _from_config(config: Config) -> Path | None:
    if not config.unity_asset_store_cache_path:
        return None
    return Path(config.unity_asset_store_cache_path)


def _from_env() -> Path | None:
    v = os.environ.get("ASSETSTORE_CACHE_PATH")
    return Path(v) if v else None


def _unity_pref_cache_path() -> Path | None:
    """Unity Editor Preferences 의 assetStoreCacheLocation. v1 minimal: None.

    v2 에서 Unity Pref 파일 포맷 파싱 추가. 본 plan 의 회귀 테스트는 mocking 으로 검증.
    """
    return None


def _default_cache_path() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Unity" / "Asset Store-5.x"
