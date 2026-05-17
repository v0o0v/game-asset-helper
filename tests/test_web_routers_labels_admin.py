"""M5 Phase 5B — 라벨 관리 라우터 검증 (Task 5.3).

populated_client fixture 를 사용한다:
  - LabelRegistry.bootstrap() 으로 24 axis × ~316 seed 라벨 채워진 상태.
  - asset_labels 행 포함 (category=character, style=pixel_art, etc.)
"""
from __future__ import annotations

import asyncio
import json

import pytest


# ── Task 5.3: GET /api/labels ──────────────────────────────────────────


def test_get_labels_returns_signature_and_list(populated_client):
    """GET /api/labels → 200 + signature 문자열 + labels 리스트."""
    r = populated_client.get("/api/labels")
    assert r.status_code == 200
    data = r.json()
    assert "signature" in data
    assert isinstance(data["signature"], str) and len(data["signature"]) > 0
    assert "labels" in data
    assert isinstance(data["labels"], list)
    # seed 로 316개 전후 라벨 존재
    assert len(data["labels"]) > 100


def test_get_labels_with_axis_filter(populated_client):
    """GET /api/labels?axis=category → 해당 axis 라벨만 반환."""
    r = populated_client.get("/api/labels?axis=category")
    assert r.status_code == 200
    data = r.json()
    assert "labels" in data
    # 모두 axis=category 여야 함
    for lb in data["labels"]:
        assert lb["axis"] == "category"
    # seed 에서 category 는 22개
    assert len(data["labels"]) >= 10


def test_get_labels_label_fields(populated_client):
    """각 라벨 항목이 id / axis / label / description / enabled / source 를 포함."""
    r = populated_client.get("/api/labels?axis=style")
    assert r.status_code == 200
    for lb in r.json()["labels"]:
        for field in ("id", "axis", "label", "description", "enabled", "source"):
            assert field in lb, f"{field} 필드 누락"


# ── Task 5.3: POST /api/labels ─────────────────────────────────────────


def test_post_label_creates_new_label(populated_client):
    """POST valid → 201 + DB 반영 확인."""
    body = {"axis": "style", "label": "test_new_label", "description": "테스트용"}
    r = populated_client.post("/api/labels", json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["axis"] == "style"
    assert data["label"] == "test_new_label"
    assert data["id"] > 0

    # GET 에서도 보여야 함
    r2 = populated_client.get("/api/labels?axis=style")
    labels = [lb["label"] for lb in r2.json()["labels"]]
    assert "test_new_label" in labels


def test_post_label_invalid_axis_returns_400(populated_client):
    """axis 가 24개 seed axis 에 없으면 400."""
    r = populated_client.post(
        "/api/labels",
        json={"axis": "not_an_axis", "label": "foo"},
    )
    assert r.status_code == 400


def test_post_label_invalid_token_returns_400(populated_client):
    """라벨 토큰이 정규식(^[a-z][a-z0-9_]{0,31}$) 불일치 → 400."""
    r = populated_client.post(
        "/api/labels",
        json={"axis": "style", "label": "UPPERCASE"},
    )
    assert r.status_code == 400


def test_post_label_invalid_token_with_spaces_returns_400(populated_client):
    """공백 포함 토큰 → 400."""
    r = populated_client.post(
        "/api/labels",
        json={"axis": "style", "label": "has space"},
    )
    assert r.status_code == 400


# ── Task 5.3: PATCH /api/labels/{label_id} ────────────────────────────


def test_patch_label_updates_description(populated_client):
    """PATCH /api/labels/{id} {description: ...} → DB 반영."""
    # 먼저 label_id 를 조회
    labels = populated_client.get("/api/labels?axis=style").json()["labels"]
    target = next(lb for lb in labels if lb["label"] == "pixel_art")
    label_id = target["id"]

    r = populated_client.patch(
        f"/api/labels/{label_id}",
        json={"description": "수정된 설명"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["description"] == "수정된 설명"
    assert data["id"] == label_id


def test_patch_label_updates_enabled(populated_client):
    """PATCH {enabled: false} → 해당 라벨 비활성화."""
    labels = populated_client.get("/api/labels?axis=style").json()["labels"]
    # enabled_only=False 로 모든 라벨 포함 쿼리
    r_all = populated_client.get("/api/labels?axis=style")
    target = next(lb for lb in r_all.json()["labels"] if lb["enabled"])
    label_id = target["id"]

    r = populated_client.patch(f"/api/labels/{label_id}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_patch_label_unknown_id_returns_404(populated_client):
    """PATCH 알 수 없는 label_id → 404."""
    r = populated_client.patch("/api/labels/99999", json={"description": "x"})
    assert r.status_code == 404


# ── Task 5.3: DELETE /api/labels/{label_id} ───────────────────────────


def test_delete_label_succeeds_when_unused(populated_client):
    """사용 중이 아닌 라벨 DELETE → 200 + {"ok": true}."""
    # 새 라벨 추가 (asset_labels 에 없음)
    r = populated_client.post(
        "/api/labels", json={"axis": "style", "label": "delete_me_label"}
    )
    assert r.status_code == 201
    label_id = r.json()["id"]

    r2 = populated_client.delete(f"/api/labels/{label_id}")
    assert r2.status_code == 200
    assert r2.json().get("ok") is True

    # GET 에서 사라졌는지 확인
    labels_after = populated_client.get("/api/labels?axis=style").json()["labels"]
    ids_after = [lb["id"] for lb in labels_after]
    assert label_id not in ids_after


def test_delete_label_in_use_returns_400(populated_client, populated_deps):
    """asset_labels 에 참조 중인 (axis, label) DELETE → 400."""
    # populated_store 에는 style=pixel_art 가 asset_labels 에 있음
    labels = populated_client.get("/api/labels?axis=style").json()["labels"]
    target = next(
        (lb for lb in labels if lb["label"] == "pixel_art"),
        None,
    )
    if target is None:
        pytest.skip("seed 에 pixel_art 없음 — 환경 불일치")
    label_id = target["id"]

    r = populated_client.delete(f"/api/labels/{label_id}")
    assert r.status_code == 400


def test_delete_label_unknown_id_returns_404(populated_client):
    """존재하지 않는 label_id DELETE → 404."""
    r = populated_client.delete("/api/labels/99999")
    assert r.status_code == 404


# ── Task 5.3: SSE broadcast ───────────────────────────────────────────


def test_post_label_broadcasts_signature_changed(populated_deps):
    """POST /api/labels → SSE bus 에 labels_signature_changed 이벤트 broadcast."""
    from gah.web import sse_bus
    from gah.web.app import build_app
    from fastapi.testclient import TestClient

    # SSE subscriber 등록 (synchronous 큐 모의)
    events: list[dict] = []

    original_broadcast = sse_bus.broadcast

    def _capture(event: str, data):
        events.append({"event": event, "data": data})
        original_broadcast(event, data)

    import unittest.mock as mock

    with mock.patch.object(sse_bus, "broadcast", side_effect=_capture):
        with TestClient(build_app(populated_deps)) as client:
            r = client.post(
                "/api/labels",
                json={"axis": "style", "label": "sse_test_label"},
            )
            assert r.status_code == 201

    sig_events = [e for e in events if e["event"] == "labels_signature_changed"]
    assert len(sig_events) >= 1
    assert "signature" in sig_events[0]["data"]


# ── Task 5.3: GET /api/labels/export ──────────────────────────────────


def test_get_export_returns_json_attachment(populated_client):
    """GET /api/labels/export → 200 + Content-Disposition attachment + JSON 파싱 가능."""
    r = populated_client.get("/api/labels/export")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".json" in cd

    # 파싱 가능한 JSON 배열
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 100
    # 각 항목 필드 확인
    item = data[0]
    for field in ("axis", "label"):
        assert field in item, f"{field} 필드 누락"


# ── Task 5.3: POST /api/labels/import ─────────────────────────────────


def test_post_import_bulk_inserts_labels(populated_client):
    """POST /api/labels/import JSON body → imported/skipped 통계 반환."""
    payload = [
        {"axis": "style", "label": "import_label_1", "description": "import 1"},
        {"axis": "style", "label": "import_label_2", "description": "import 2"},
        # 이미 존재하는 seed 라벨 → skipped
        {"axis": "style", "label": "pixel_art", "description": "updated desc"},
    ]
    r = populated_client.post("/api/labels/import", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "imported" in data
    assert "skipped" in data
    # 신규 2개는 imported 에 포함
    assert data["imported"] >= 2


# ── Task 5.3: GET /ui/labels/admin ────────────────────────────────────


def test_ui_labels_admin_returns_html(populated_client):
    """GET /ui/labels/admin → 200 + text/html."""
    r = populated_client.get("/ui/labels/admin")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_ui_labels_admin_contains_axes(populated_client):
    """GET /ui/labels/admin HTML 에 axis 이름이 포함된다."""
    r = populated_client.get("/ui/labels/admin")
    assert r.status_code == 200
    assert "category" in r.text
    assert "style" in r.text
