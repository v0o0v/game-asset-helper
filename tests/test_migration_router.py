"""Migration 라우터 endpoint 테스트."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def candidate_fixture(tmp_path):
    """detect_v001_candidate 가 가짜 candidate 반환하도록 prepare."""
    from assetcache.core.migration import MigrationCandidate

    src = tmp_path / "old"
    tgt = tmp_path / "new"
    src.mkdir()
    tgt.mkdir()
    return MigrationCandidate(
        source=src, target=tgt,
        total_files=10, total_bytes=1000,
        has_db=True, has_library=True,
    )


@pytest.fixture
def client_with_candidate(candidate_fixture, monkeypatch, deps_fixture):
    """detect_v001_candidate 가 candidate 반환하도록 monkeypatch한 client."""
    monkeypatch.setattr(
        "assetcache.web.routers.migration.detect_v001_candidate",
        lambda paths: candidate_fixture,
    )
    from fastapi.testclient import TestClient
    from assetcache.web.app import build_app
    app = build_app(deps_fixture)
    return TestClient(app), candidate_fixture


@pytest.fixture
def client_without_candidate(monkeypatch, deps_fixture):
    monkeypatch.setattr(
        "assetcache.web.routers.migration.detect_v001_candidate",
        lambda paths: None,
    )
    from fastapi.testclient import TestClient
    from assetcache.web.app import build_app
    return TestClient(build_app(deps_fixture))


def test_migration_status_returns_candidate(client_with_candidate):
    client, candidate = client_with_candidate
    resp = client.get("/api/migration/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == str(candidate.source)
    assert data["target"] == str(candidate.target)
    assert data["total_files"] == 10
    assert data["has_db"] is True


def test_migration_status_returns_null_when_no_candidate(client_without_candidate):
    resp = client_without_candidate.get("/api/migration/status")
    assert resp.status_code == 200
    assert resp.json() == {"candidate": None}


def test_migration_run_returns_task_id(client_with_candidate):
    client, _ = client_with_candidate
    resp = client.post("/api/migration/run", json={"mode": "copy"})
    assert resp.status_code == 202
    assert "task_id" in resp.json()
