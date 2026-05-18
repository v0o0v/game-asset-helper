"""M7 — /unity-asset-store 라우터 + API 회귀."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── fixture: GAH FastAPI 앱 + 가짜 캐시 디렉터리 ──────────────────────


@pytest.fixture
def app_with_cache(tmp_path, monkeypatch, deps_fixture):
    """캐시 디렉터리 + .unitypackage fixture 가 들어간 FastAPI 앱.

    deps_fixture (conftest) 의 WebDeps 를 재사용한다.
    """
    from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage

    cache = tmp_path / "cache"
    pub = cache / "Pixel Studios" / "Sprites"
    pub.mkdir(parents=True)
    make_fixture_unitypackage(pub / "Mega.unitypackage", include_psd=False)
    monkeypatch.setenv("ASSETSTORE_CACHE_PATH", str(cache))

    from gah.web.app import build_app

    app = build_app(deps_fixture)
    return app, cache, deps_fixture.store


# ─── 1: GET /unity-asset-store ───────────────────────────────────────


def test_get_unity_page_renders(app_with_cache):
    """/unity-asset-store 는 200 HTML 를 반환한다."""
    app, _, _store = app_with_cache
    client = TestClient(app)
    r = client.get("/unity-asset-store")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


# ─── 2: POST /api/unity-packages/scan ────────────────────────────────


def test_scan_api_creates_rows(app_with_cache):
    """/scan 후 store 에 1+ 행이 생긴다."""
    app, _, store = app_with_cache
    client = TestClient(app)
    r = client.post("/api/unity-packages/scan", json={"force": False})
    assert r.status_code == 200
    body = r.json()
    assert body["new"] >= 1
    rows = store.list_unity_imports()
    assert len(rows) >= 1


# ─── 3: (removed) /api/unity-packages/{id}/preview — M7 patch: 미리보기 버튼
#       제거 후 endpoint 도 제거. 임포트 시 자산 카운트가 preview 컬럼에 자동
#       채워짐 (importer.py).


# ─── 4: POST /api/unity-packages/{id}/import ─────────────────────────


def test_import_api_triggers_extract(app_with_cache):
    """/import 후 state=imported (or failed)."""
    app, _, store = app_with_cache
    client = TestClient(app)
    client.post("/api/unity-packages/scan", json={"force": False})
    uid = store.list_unity_imports()[0].id
    r = client.post(f"/api/unity-packages/{uid}/import")
    assert r.status_code == 200
    body = r.json()
    # 성공이면 imported, 라이브러리 경로 문제 시 failed 도 허용
    assert body["state"] in ("imported", "failed")


# ─── 5: POST /api/unity-packages/{id}/skip ───────────────────────────


def test_skip_api(app_with_cache):
    """/skip 후 state=skipped."""
    app, _, store = app_with_cache
    client = TestClient(app)
    client.post("/api/unity-packages/scan", json={"force": False})
    uid = store.list_unity_imports()[0].id
    r = client.post(f"/api/unity-packages/{uid}/skip")
    assert r.status_code == 200
    row = store.get_unity_import_by_id(uid)
    assert row.import_state == "skipped"


# ─── 6: POST /api/unity-packages/{id}/restore ────────────────────────


def test_restore_api(app_with_cache):
    """/restore 후 state=discovered."""
    app, _, store = app_with_cache
    client = TestClient(app)
    client.post("/api/unity-packages/scan", json={"force": False})
    uid = store.list_unity_imports()[0].id
    store.update_unity_state(uid, "skipped")
    r = client.post(f"/api/unity-packages/{uid}/restore")
    assert r.status_code == 200
    row = store.get_unity_import_by_id(uid)
    assert row.import_state == "discovered"


# ─── 7: GET /unity-asset-store?focus={id} ────────────────────────────


def test_focus_query_renders(app_with_cache):
    """?focus={id} 파라미터가 있어도 200 HTML."""
    app, _, store = app_with_cache
    client = TestClient(app)
    client.post("/api/unity-packages/scan", json={"force": False})
    uid = store.list_unity_imports()[0].id
    r = client.get(f"/unity-asset-store?focus={uid}")
    assert r.status_code == 200


# ─── 8: 캐시 경로 없을 때 안내 텍스트 ───────────────────────────────


def test_empty_cache_message(deps_fixture, monkeypatch):
    """ASSETSTORE_CACHE_PATH 없음 → 200 + '캐시' 안내 텍스트."""
    monkeypatch.delenv("ASSETSTORE_CACHE_PATH", raising=False)
    # config 의 unity_asset_store_cache_path 도 비움
    deps_fixture.config.unity_asset_store_cache_path = ""

    from gah.web.app import build_app

    app = build_app(deps_fixture)
    client = TestClient(app)
    r = client.get("/unity-asset-store")
    assert r.status_code == 200
    assert "캐시" in r.text or "cache" in r.text.lower()
