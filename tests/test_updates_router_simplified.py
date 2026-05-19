"""단순화된 /api/updates/check 라우터."""
from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response


@pytest.fixture
def client(monkeypatch, deps_fixture):
    from assetcache.web.app import build_app
    from assetcache.core.updater.version import Version

    monkeypatch.setattr(
        "assetcache.web.routers.updates.get_current_version",
        lambda: Version.parse("0.1.0"),
    )
    return TestClient(build_app(deps_fixture))


@respx.mock
def test_check_returns_payload_with_command(client):
    respx.get("https://pypi.org/pypi/assetcache-mcp/json").mock(
        return_value=Response(200, json={"info": {"version": "0.2.0"}})
    )
    resp = client.get("/api/updates/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current"] == "0.1.0"
    assert data["latest"] == "0.2.0"
    assert data["available"] is True
    assert data["command"].endswith("assetcache-mcp")


@respx.mock
def test_check_returns_not_available_when_same_version(client):
    respx.get("https://pypi.org/pypi/assetcache-mcp/json").mock(
        return_value=Response(200, json={"info": {"version": "0.1.0"}})
    )
    resp = client.get("/api/updates/check")
    data = resp.json()
    assert data["available"] is False
