"""M5 Phase 5A — 팩 관리 라우터 검증 (Task 5.1).

populated_client fixture 를 사용한다:
  - pack_a (vendor=kenney)  × 3 assets (sprite × 2, sound × 1)
  - pack_b (vendor=craftpix) × 3 assets (sprite × 2, sound × 1)
"""
from __future__ import annotations

import pytest


# ── Task 5.1: GET /api/packs ──────────────────────────────────────────


def test_api_packs_returns_pack_list(populated_client):
    """GET /api/packs → 200 + packs 키에 2 개 팩 반환."""
    r = populated_client.get("/api/packs")
    assert r.status_code == 200
    data = r.json()
    assert "packs" in data
    assert len(data["packs"]) == 2


def test_api_packs_includes_asset_count(populated_client):
    """각 팩의 asset_count 가 3 이다 (populated_store 에 팩당 3 자산)."""
    r = populated_client.get("/api/packs")
    assert r.status_code == 200
    for pack in r.json()["packs"]:
        assert pack["asset_count"] == 3


def test_api_packs_includes_kind_counts(populated_client):
    """kind_counts 가 dict 형태이고 sprite / sound 키를 포함한다."""
    r = populated_client.get("/api/packs")
    assert r.status_code == 200
    for pack in r.json()["packs"]:
        kc = pack["kind_counts"]
        assert isinstance(kc, dict)
        # populated_store: sprite × 2, sound × 1 per pack
        assert kc.get("sprite") == 2
        assert kc.get("sound") == 1


def test_api_packs_include_disabled_default(populated_client, populated_deps):
    """enabled=False 인 팩도 기본 include_disabled=True 에서 반환된다."""
    # pack_a 를 비활성화
    pack_a_id = populated_client.get("/api/packs").json()["packs"][0]["id"]
    populated_deps.store.set_pack_enabled(pack_a_id, False)

    r = populated_client.get("/api/packs")
    assert r.status_code == 200
    assert len(r.json()["packs"]) == 2  # 비활성화돼도 목록에 포함


def test_api_packs_contains_expected_fields(populated_client):
    """팩 dict 에 id / name / vendor / license / enabled / asset_count / kind_counts 포함."""
    r = populated_client.get("/api/packs")
    pack = r.json()["packs"][0]
    for field in ("id", "name", "vendor", "enabled", "asset_count", "kind_counts"):
        assert field in pack, f"{field} 필드 누락"


# ── Task 5.1: GET /ui/packs ───────────────────────────────────────────


def test_ui_packs_returns_html(populated_client):
    """GET /ui/packs → 200 + text/html."""
    r = populated_client.get("/ui/packs")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_ui_packs_contains_pack_names(populated_client):
    """GET /ui/packs HTML fragment 에 pack_a / pack_b 이름이 들어 있다."""
    r = populated_client.get("/ui/packs")
    assert r.status_code == 200
    assert "pack_a" in r.text
    assert "pack_b" in r.text


# ── Task 5.1: PATCH /api/packs/{pack_id} ─────────────────────────────


def test_patch_pack_toggles_enabled(populated_client, populated_deps):
    """PATCH /api/packs/{id} {"enabled": false} → DB 갱신 확인."""
    packs = populated_client.get("/api/packs").json()["packs"]
    target = next(p for p in packs if p["enabled"])
    pack_id = target["id"]

    r = populated_client.patch(f"/api/packs/{pack_id}", json={"enabled": False})
    assert r.status_code == 200

    # DB 에 반영됐는지 확인
    updated = populated_deps.store.get_pack_by_id(pack_id)
    assert updated is not None
    assert updated.enabled is False


def test_patch_pack_toggle_back_to_enabled(populated_client, populated_deps):
    """PATCH enabled=False → enabled=True 재토글 가능."""
    packs = populated_client.get("/api/packs").json()["packs"]
    pack_id = packs[0]["id"]

    populated_client.patch(f"/api/packs/{pack_id}", json={"enabled": False})
    r = populated_client.patch(f"/api/packs/{pack_id}", json={"enabled": True})
    assert r.status_code == 200

    updated = populated_deps.store.get_pack_by_id(pack_id)
    assert updated.enabled is True


def test_patch_pack_unknown_id_returns_404(populated_client):
    """PATCH 알 수 없는 pack_id → 404."""
    r = populated_client.patch("/api/packs/99999", json={"enabled": False})
    assert r.status_code == 404


def test_patch_pack_returns_html_fragment(populated_client):
    """PATCH 응답이 HTML fragment (_pack_card.html) 다."""
    packs = populated_client.get("/api/packs").json()["packs"]
    pack_id = packs[0]["id"]

    r = populated_client.patch(f"/api/packs/{pack_id}", json={"enabled": False})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
