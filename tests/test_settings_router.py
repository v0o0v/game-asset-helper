"""M8 — /settings 페이지 + POST /api/settings 통합 테스트."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def web_deps(deps_fixture):
    """conftest.py 의 deps_fixture 를 재사용 (이름 별칭)."""
    return deps_fixture


@pytest.fixture
def web_app(web_deps):
    """web_deps 를 이용해 FastAPI 앱 생성."""
    from assetcache.web.app import build_app

    return build_app(web_deps)


@pytest.fixture
def client(web_app):
    return TestClient(web_app)


def test_settings_page_renders_200(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert b"<form" in r.content


def test_settings_post_updates_ui_language(client, web_deps):
    r = client.post("/api/settings", json={"ui_language": "en"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert web_deps.config.ui_language == "en"
    assert "assetcache_locale=en" in r.headers.get("set-cookie", "")


def test_settings_post_updates_ui_theme(client, web_deps):
    r = client.post("/api/settings", json={"ui_theme": "dark"})
    assert r.status_code == 200
    assert web_deps.config.ui_theme == "dark"


def test_settings_post_updates_autostart(client, web_deps, monkeypatch):
    """Task 11 에서 winreg 동기화 — 본 task 는 Config + 호출만 검증."""
    from assetcache.platform import autostart as autostart_mod
    calls = []
    monkeypatch.setattr(autostart_mod, "set_autostart",
                       lambda enabled, exe_path=None: calls.append(enabled))
    r = client.post("/api/settings", json={"autostart": True})
    assert r.status_code == 200
    assert web_deps.config.autostart is True
    assert calls == [True]


def test_settings_post_invalid_language_rejected(client):
    r = client.post("/api/settings", json={"ui_language": "klingon"})
    assert r.status_code == 422


def test_settings_get_includes_current_locale(client, web_deps):
    web_deps.config.ui_language = "ko"
    r = client.get("/settings")
    body = r.text
    assert "ui_language" in body
    # 라디오 ko 가 선택됨
    assert 'value="ko"' in body


def test_settings_post_auto_clears_cookie(client, web_deps):
    """ui_language='auto' 저장 시 기존 assetcache_locale 쿠키 삭제.

    잔존 쿠키가 LocaleMiddleware 2단계 (쿠키) 에서 Config.ui_language 3단계보다
    우선이라, 쿠키를 명시 delete 안 하면 "자동 감지" 가 실제로 동작 안 함.
    """
    r = client.post("/api/settings", json={"ui_language": "auto"})
    assert r.status_code == 200
    assert web_deps.config.ui_language == "auto"
    set_cookie = r.headers.get("set-cookie", "")
    assert "assetcache_locale" in set_cookie
    # delete_cookie 는 Max-Age=0 으로 만료 set
    assert "max-age=0" in set_cookie.lower()


def test_settings_post_autostart_failure_returns_500(client, web_deps, monkeypatch):
    """권한 거부 (GPO) 또는 OSError 시 500 + ok=False 응답."""
    from assetcache.platform import autostart as autostart_mod

    def _boom(enabled, exe_path=None):
        raise OSError("Permission denied")

    monkeypatch.setattr(autostart_mod, "set_autostart", _boom)
    r = client.post("/api/settings", json={"autostart": True})
    assert r.status_code == 500
    assert r.json()["ok"] is False
    assert "Permission denied" in r.json()["error"]
