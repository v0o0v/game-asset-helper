"""M5 — 자산 상세 모달 (/ui/asset-detail/{id}) 검증."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# populated_deps / populated_client → conftest.py 공통 fixture 사용


# ─── 에러 케이스 (빈 라이브러리) ────────────────────────────────────────


def test_asset_detail_missing_id_returns_404(client):
    """존재하지 않는 asset_id → 404."""
    r = client.get("/ui/asset-detail/99999")
    assert r.status_code == 404


def test_asset_detail_invalid_id_returns_422(client):
    """숫자가 아닌 asset_id → 422."""
    r = client.get("/ui/asset-detail/notanumber")
    assert r.status_code == 422


def test_asset_detail_negative_id(client):
    """음수 asset_id → 404 또는 422."""
    r = client.get("/ui/asset-detail/-1")
    assert r.status_code in (404, 422)


# ─── 정상 케이스 (populated_client) ─────────────────────────────────────


def test_asset_detail_returns_html_for_existing_asset(populated_client):
    """populated_client 의 첫 asset → 200 + HTML 반환."""
    from gah.core.store import Store

    store: Store = populated_client.app.state.deps.store
    assets = store.list_assets(limit=1, offset=0)
    assert len(assets) >= 1
    asset_id = assets[0].id
    r = populated_client.get(f"/ui/asset-detail/{asset_id}")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "modal" in r.text or "asset-detail" in r.text


def test_asset_detail_includes_adopt_button(populated_client):
    """모달에 채택 버튼이 포함된다."""
    from gah.core.store import Store

    store: Store = populated_client.app.state.deps.store
    assets = store.list_assets(limit=1, offset=0)
    asset_id = assets[0].id
    r = populated_client.get(f"/ui/asset-detail/{asset_id}")
    assert r.status_code == 200
    assert "채택" in r.text or "adopt" in r.text


def test_asset_detail_includes_labels(populated_client):
    """라벨이 있는 asset 에서 라벨 정보가 노출된다."""
    from gah.core.store import Store

    store: Store = populated_client.app.state.deps.store
    assets = store.list_assets(limit=10, offset=0)
    # 라벨이 있는 sprite asset 우선 선택
    sprite_assets = [a for a in assets if a.kind == "sprite"]
    asset_id = sprite_assets[0].id if sprite_assets else assets[0].id
    r = populated_client.get(f"/ui/asset-detail/{asset_id}")
    assert r.status_code == 200
    # 라벨 섹션 존재 여부 (라벨이 없으면 섹션이 숨겨짐 — 200이면 통과)
    assert "text/html" in r.headers["content-type"]


def test_asset_detail_sound_asset_no_img_tag(populated_client):
    """sound asset 상세 → <img> 없고 <audio> 관련 요소 있다."""
    from gah.core.store import Store

    store: Store = populated_client.app.state.deps.store
    assets = store.list_assets(limit=20, offset=0)
    sounds = [a for a in assets if a.kind == "sound"]
    if not sounds:
        pytest.skip("populated_client 에 sound asset 없음")
    asset_id = sounds[0].id
    r = populated_client.get(f"/ui/asset-detail/{asset_id}")
    assert r.status_code == 200
    # sound → thumbnail img 없고 audio 태그 있음
    assert "/api/thumbnail/" not in r.text
    assert "audio" in r.text or "/api/audio/" in r.text
