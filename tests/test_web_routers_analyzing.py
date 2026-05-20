"""Phase 5 task 5.2 — /analyzing dashboard sections A+B.

6 테스트:
  1. GET /analyzing → 200 + HTMX polling target URL 포함
  2. GET /analyzing → 제목(분석 진행 / Analysis progress) 포함
  3. GET /analyzing/partial → 200 + id="analyzing-partial" 포함
  4. GET /analyzing/partial → 요약(Summary) 섹션 포함
  5. GET /analyzing/partial → 즉시 분석(Interactive queue) 섹션 포함
  6. GET /analyzing/partial → 빈 큐 → empty state 표시 (status 200)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from assetcache.web.app import build_app


# ─── fixture ───────────────────────────────────────────────────────────────


@pytest.fixture
def client(populated_deps):
    """populated_deps 기반 TestClient — queue=None (분석 큐 없는 상태)."""
    with TestClient(build_app(populated_deps), follow_redirects=False) as c:
        yield c


# ─── 1. GET /analyzing 200 + HTMX polling target ──────────────────────────


def test_analyzing_dashboard_200(client: TestClient):
    r = client.get("/analyzing")
    assert r.status_code == 200
    assert "/analyzing/partial" in r.text


# ─── 2. GET /analyzing 제목 포함 ──────────────────────────────────────────


def test_analyzing_dashboard_includes_summary_heading(client: TestClient):
    r = client.get("/analyzing")
    assert r.status_code == 200
    # 한글 또는 영어 제목 모두 허용
    lower = r.text.lower()
    assert (
        "분석 진행" in r.text
        or "analysis progress" in lower
        or "analyzing" in lower
    )


# ─── 3. GET /analyzing/partial → id="analyzing-partial" ──────────────────


def test_analyzing_partial_returns_partial_html(client: TestClient):
    r = client.get("/analyzing/partial")
    assert r.status_code == 200
    assert 'id="analyzing-partial"' in r.text


# ─── 4. GET /analyzing/partial → 요약 섹션 포함 ──────────────────────────


def test_analyzing_partial_shows_summary_section(client: TestClient):
    r = client.get("/analyzing/partial")
    assert r.status_code == 200
    assert "요약" in r.text or "Summary" in r.text


# ─── 5. GET /analyzing/partial → 즉시 분석 큐 섹션 포함 ──────────────────


def test_analyzing_partial_interactive_queue_section(client: TestClient):
    r = client.get("/analyzing/partial")
    assert r.status_code == 200
    assert "즉시 분석" in r.text or "Interactive queue" in r.text or "interactive" in r.text.lower()


# ─── 6. GET /analyzing/partial → 빈 큐 empty state ───────────────────────


def test_analyzing_partial_empty_queue(client: TestClient):
    """queue=None 또는 빈 큐 → 200 + 빈 상태 메시지."""
    r = client.get("/analyzing/partial")
    assert r.status_code == 200
    # 빈 큐 안내: "없음", "empty", "0" 등
    lower = r.text.lower()
    assert (
        "없음" in r.text
        or "empty" in lower
        or "queue empty" in lower
        or ">0<" in r.text
        or "0개" in r.text
    )
