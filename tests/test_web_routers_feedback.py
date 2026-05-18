"""M5 Phase 6A — /api/record-use + /api/feedback 엔드포인트 검증.

채택 버튼과 거부 버튼이 실제로 DB 에 기록되는지 확인한다.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


@pytest.fixture
def client(populated_deps):
    with TestClient(build_app(populated_deps)) as c:
        yield c


def _first_asset_id(client: TestClient) -> int:
    """populated 라이브러리의 첫 asset id 를 반환."""
    from gah.core.store import Store
    store: Store = client.app.state.deps.store
    assets = store.list_assets(limit=1, offset=0)
    assert assets, "populated_deps 에 asset 이 없음"
    return assets[0].id


# ─── POST /api/record-use ──────────────────────────────────────────────────


def test_record_use_inserts_asset_usage_row(client):
    """POST /api/record-use → asset_usage 행이 DB 에 삽입된다."""
    asset_id = _first_asset_id(client)
    store = client.app.state.deps.store

    before = store.conn.execute(
        "SELECT COUNT(*) FROM asset_usage WHERE asset_id = ?", (asset_id,)
    ).fetchone()[0]

    r = client.post(
        "/api/record-use",
        content=json.dumps({"asset_id": asset_id}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "usage_id" in body

    after = store.conn.execute(
        "SELECT COUNT(*) FROM asset_usage WHERE asset_id = ?", (asset_id,)
    ).fetchone()[0]
    assert after == before + 1


def test_record_use_source_is_manual(client):
    """POST /api/record-use → source='manual' 로 기록된다."""
    asset_id = _first_asset_id(client)
    store = client.app.state.deps.store

    r = client.post(
        "/api/record-use",
        content=json.dumps({"asset_id": asset_id}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    usage_id = r.json()["usage_id"]

    row = store.conn.execute(
        "SELECT source FROM asset_usage WHERE id = ?", (usage_id,)
    ).fetchone()
    assert row is not None
    assert row[0] == "manual"


def test_record_use_missing_asset_id_returns_422(client):
    """POST /api/record-use — asset_id 없음 → 422 Pydantic 검증 오류."""
    r = client.post(
        "/api/record-use",
        content=json.dumps({}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422


def test_record_use_unknown_asset_returns_404(client):
    """POST /api/record-use — 존재하지 않는 asset_id → 404."""
    r = client.post(
        "/api/record-use",
        content=json.dumps({"asset_id": 999999}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 404


# ─── POST /api/feedback ───────────────────────────────────────────────────


def test_feedback_skipped_when_no_query_id(client):
    """POST /api/feedback — query_id 없음 → skipped=True (프로젝트 매핑 불가)."""
    asset_id = _first_asset_id(client)
    r = client.post(
        "/api/feedback",
        content=json.dumps({"asset_id": asset_id, "reason": "negative"}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body.get("skipped") is True


def test_feedback_inserts_feedback_record(client):
    """POST /api/feedback — 유효한 query_id + asset_id → feedback_records 행 삽입."""
    asset_id = _first_asset_id(client)
    store = client.app.state.deps.store

    # search_queries 에 행 삽입 (project 포함)
    project = store.upsert_project("test_proj")
    project_db_id = project.id

    query_id = store.conn.execute(
        "INSERT INTO search_queries (project_id, query_text, results_json, created_at) "
        "VALUES (?, ?, ?, strftime('%s', 'now'))",
        (project_db_id, "test query", "[]"),
    ).lastrowid
    store.conn.commit()

    before = store.conn.execute(
        "SELECT COUNT(*) FROM feedback_records"
    ).fetchone()[0]

    r = client.post(
        "/api/feedback",
        content=json.dumps({
            "asset_id": asset_id,
            "reason": "negative",
            "query_id": query_id,
        }),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body.get("skipped") is not True

    after = store.conn.execute(
        "SELECT COUNT(*) FROM feedback_records"
    ).fetchone()[0]
    assert after == before + 1


def test_feedback_unknown_asset_returns_404(client):
    """POST /api/feedback — 존재하지 않는 asset_id → 404."""
    r = client.post(
        "/api/feedback",
        content=json.dumps({"asset_id": 999999, "reason": "negative"}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 404
