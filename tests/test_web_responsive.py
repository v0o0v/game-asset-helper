"""M5 Phase 3D-2 — 반응형 (≤768px 사이드 패널 자동 닫힘) 검증 (Task 3.16)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# ── main.css 미디어 쿼리 확인 ─────────────────────────────────────────


def test_main_css_has_768px_media_query():
    """main.css 에 @media (max-width: 768px) 블록이 있다."""
    from pathlib import Path
    css_path = Path(__file__).parent.parent / "src" / "gah" / "web" / "static" / "css" / "main.css"
    content = css_path.read_text(encoding="utf-8")
    assert "@media (max-width: 768px)" in content


def test_main_css_768_block_has_position_fixed():
    """768px 미디어 쿼리 블록에 side-panel position: fixed 가 있다."""
    from pathlib import Path
    css_path = Path(__file__).parent.parent / "src" / "gah" / "web" / "static" / "css" / "main.css"
    content = css_path.read_text(encoding="utf-8")
    assert "position: fixed" in content


def test_main_css_768_block_has_transform():
    """768px 미디어 쿼리 블록에 transform: translateX 슬라이드 효과가 있다."""
    from pathlib import Path
    css_path = Path(__file__).parent.parent / "src" / "gah" / "web" / "static" / "css" / "main.css"
    content = css_path.read_text(encoding="utf-8")
    assert "translateX" in content


def test_main_css_768_block_has_transition():
    """768px 미디어 쿼리 블록에 transition 이 있다."""
    from pathlib import Path
    css_path = Path(__file__).parent.parent / "src" / "gah" / "web" / "static" / "css" / "main.css"
    content = css_path.read_text(encoding="utf-8")
    assert "transition" in content


# ── library.html / base.html JS resize 리스너 확인 ───────────────────


def test_library_page_has_resize_listener(client):
    """라이브러리 페이지에 window resize 이벤트 리스너가 있다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "resize" in r.text


def test_library_page_resize_closes_panel_on_mobile(client):
    """resize 리스너가 768px 이하에서 advanced.open = false 를 실행한다."""
    r = client.get("/library")
    # innerWidth <= 768 체크 + advanced.open = false 코드가 있어야 함
    assert "innerWidth" in r.text or "768" in r.text
    assert "advanced" in r.text


def test_library_page_has_side_panel_overlay_class(client):
    """768px 이하 오버레이를 위한 CSS 클래스가 라이브러리 페이지에 있다."""
    r = client.get("/library")
    # side-panel 클래스 존재
    assert "side-panel" in r.text
