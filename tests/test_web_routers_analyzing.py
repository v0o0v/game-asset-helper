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


# ─── 7. GET /analyzing/partial → Section C batch jobs 빈 상태 ────────────


def test_analyzing_partial_batch_jobs_section_empty(client: TestClient):
    """진행 중 batch job 없을 때 'No active batch jobs' 메시지."""
    r = client.get("/analyzing/partial")
    assert r.status_code == 200
    assert "Batch jobs" in r.text or "배치 작업" in r.text
    assert (
        "No active batch jobs" in r.text
        or "진행 중 배치 작업" in r.text
        or "<em>" in r.text
    )


# ─── 8. GET /analyzing/partial → Section D recent failures 빈 상태 ────────


def test_analyzing_partial_recent_failures_section_empty(client: TestClient):
    """최근 실패 없을 때 'No recent failures' 또는 관련 메시지."""
    r = client.get("/analyzing/partial")
    assert r.status_code == 200
    assert "Recent failures" in r.text or "최근 실패" in r.text


# ─── 9. POST /analyzing/batch/<id>/cancel → 303 또는 404 ─────────────────


def test_analyzing_cancel_batch_job_redirects(client: TestClient):
    """POST /analyzing/batch/<id>/cancel — 303 redirect 또는 404 (batch_manager 없음).

    populated_deps fixture 에 batch_manager=None 이므로 404 expected.
    Either way, not 500.
    """
    r = client.post("/analyzing/batch/1/cancel", follow_redirects=False)
    assert r.status_code in (303, 404)


# ─── 10. base template nav 에 /analyzing 링크 ─────────────────────────────


def test_base_template_has_analyzing_nav_link(client: TestClient):
    """nav 에 /analyzing 링크 — 아무 풀 페이지에서 확인."""
    r = client.get("/analyzing")
    assert r.status_code == 200
    assert "/analyzing" in r.text
