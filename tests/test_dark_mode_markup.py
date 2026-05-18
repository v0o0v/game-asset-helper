"""M8 — 다크모드 토글 헤더 마크업 + theme.js 로드 확인."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


def test_nav_has_theme_toggle_button(client):
    r = client.get("/library")
    assert r.status_code == 200
    body = r.text
    assert 'themeToggle()' in body
    assert "theme-toggle-btn" in body


def test_theme_js_loaded_in_base(client):
    r = client.get("/library")
    assert "/static/js/theme.js" in r.text


def test_anti_flash_inline_script_present(client):
    r = client.get("/library")
    # localStorage 즉시 적용 인라인 스크립트
    assert "gah_theme" in r.text
    # documentElement.setAttribute 또는 data-theme 적용
    assert "documentElement.setAttribute" in r.text or "data-theme" in r.text
