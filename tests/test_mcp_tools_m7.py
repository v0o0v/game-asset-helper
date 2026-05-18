"""M7 — MCP scan_unity_asset_store_cache + list_unity_packages 도구."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from gah.mcp.tools import McpToolError


def test_scan_normal(cache_dir_with_pkgs, mcp_tool_deps):
    from gah.mcp.tools import tool_scan_unity_asset_store_cache
    from gah.mcp.models import ScanUnityAssetStoreCacheRequest

    deps = mcp_tool_deps()
    req = ScanUnityAssetStoreCacheRequest(force=False, filter=None)
    result = tool_scan_unity_asset_store_cache(deps, req)
    assert result.scanned >= 1
    assert result.cache_path
    assert result.new >= 1


def test_scan_cache_not_found(mcp_tool_deps, monkeypatch, tmp_path):
    from gah.mcp.tools import tool_scan_unity_asset_store_cache, McpToolError
    from gah.mcp.models import ScanUnityAssetStoreCacheRequest

    # 모든 캐시 경로 후보를 차단: env, config, APPDATA 기본 경로
    monkeypatch.delenv("ASSETSTORE_CACHE_PATH", raising=False)
    # APPDATA 를 비존재 경로로 돌려 기본 Unity 캐시 경로 검출 실패
    monkeypatch.setenv("APPDATA", str(tmp_path / "nonexistent_appdata"))
    deps = mcp_tool_deps()
    deps.config.unity_asset_store_cache_path = None
    req = ScanUnityAssetStoreCacheRequest(force=False, filter=None)
    with pytest.raises(McpToolError) as exc:
        tool_scan_unity_asset_store_cache(deps, req)
    assert "503" in exc.value.code or "cache_not_found" in exc.value.code


def test_scan_with_filter(cache_dir_with_pkgs, mcp_tool_deps):
    from gah.mcp.tools import tool_scan_unity_asset_store_cache
    from gah.mcp.models import ScanUnityAssetStoreCacheRequest, ScanFilter

    deps = mcp_tool_deps()
    req = ScanUnityAssetStoreCacheRequest(
        force=False, filter=ScanFilter(publisher_glob="Pixel*"),
    )
    result = tool_scan_unity_asset_store_cache(deps, req)
    assert result.scanned >= 1


def test_list_returns_all(cache_dir_with_pkgs, mcp_tool_deps):
    from gah.mcp.tools import tool_scan_unity_asset_store_cache, tool_list_unity_packages
    from gah.mcp.models import ScanUnityAssetStoreCacheRequest, ListUnityPackagesRequest

    deps = mcp_tool_deps()
    tool_scan_unity_asset_store_cache(deps, ScanUnityAssetStoreCacheRequest())
    req = ListUnityPackagesRequest()
    result = tool_list_unity_packages(deps, req)
    assert result.total >= 1
    assert len(result.items) >= 1


def test_list_filter_state(cache_dir_with_pkgs, mcp_tool_deps):
    from gah.mcp.tools import tool_scan_unity_asset_store_cache, tool_list_unity_packages
    from gah.mcp.models import ScanUnityAssetStoreCacheRequest, ListUnityPackagesRequest

    deps = mcp_tool_deps()
    tool_scan_unity_asset_store_cache(deps, ScanUnityAssetStoreCacheRequest())
    req = ListUnityPackagesRequest(state="discovered")
    result = tool_list_unity_packages(deps, req)
    assert all(item.import_state == "discovered" for item in result.items)


def test_list_publisher_glob(cache_dir_with_pkgs, mcp_tool_deps):
    from gah.mcp.tools import tool_scan_unity_asset_store_cache, tool_list_unity_packages
    from gah.mcp.models import ScanUnityAssetStoreCacheRequest, ListUnityPackagesRequest, ScanFilter

    deps = mcp_tool_deps()
    tool_scan_unity_asset_store_cache(deps, ScanUnityAssetStoreCacheRequest())
    req = ListUnityPackagesRequest(filter=ScanFilter(publisher_glob="Pixel*"))
    result = tool_list_unity_packages(deps, req)
    assert all(
        item.publisher and item.publisher.startswith("Pixel")
        for item in result.items
    )


def test_list_include_preview_populates(cache_dir_with_pkgs, mcp_tool_deps):
    from gah.mcp.tools import tool_scan_unity_asset_store_cache, tool_list_unity_packages
    from gah.mcp.models import ScanUnityAssetStoreCacheRequest, ListUnityPackagesRequest

    deps = mcp_tool_deps()
    tool_scan_unity_asset_store_cache(deps, ScanUnityAssetStoreCacheRequest())
    req = ListUnityPackagesRequest(include_preview=True)
    result = tool_list_unity_packages(deps, req)
    assert any(item.preview_asset_count is not None for item in result.items)


def test_list_offset_limit(cache_dir_with_pkgs, mcp_tool_deps):
    from gah.mcp.tools import tool_scan_unity_asset_store_cache, tool_list_unity_packages
    from gah.mcp.models import ScanUnityAssetStoreCacheRequest, ListUnityPackagesRequest

    deps = mcp_tool_deps()
    tool_scan_unity_asset_store_cache(deps, ScanUnityAssetStoreCacheRequest())
    req = ListUnityPackagesRequest(offset=0, limit=5)
    result = tool_list_unity_packages(deps, req)
    assert len(result.items) <= 5


def test_list_import_url_format(cache_dir_with_pkgs, mcp_tool_deps):
    from gah.mcp.tools import tool_scan_unity_asset_store_cache, tool_list_unity_packages
    from gah.mcp.models import ScanUnityAssetStoreCacheRequest, ListUnityPackagesRequest

    deps = mcp_tool_deps()
    tool_scan_unity_asset_store_cache(deps, ScanUnityAssetStoreCacheRequest())
    req = ListUnityPackagesRequest()
    result = tool_list_unity_packages(deps, req)
    for item in result.items:
        assert item.import_url.startswith("http")
        assert "/unity-asset-store" in item.import_url
        assert f"focus={item.id}" in item.import_url


def test_list_empty_when_no_imports(mcp_tool_deps):
    from gah.mcp.tools import tool_list_unity_packages
    from gah.mcp.models import ListUnityPackagesRequest

    deps = mcp_tool_deps()
    req = ListUnityPackagesRequest()
    result = tool_list_unity_packages(deps, req)
    assert result.total == 0
    assert result.items == []


# ── fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def cache_dir_with_pkgs(tmp_path, monkeypatch):
    pub = tmp_path / "Pixel Studios" / "Sprites"
    pub.mkdir(parents=True)
    from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage
    make_fixture_unitypackage(pub / "Mega.unitypackage", include_psd=False)
    monkeypatch.setenv("ASSETSTORE_CACHE_PATH", str(tmp_path))
    return tmp_path
