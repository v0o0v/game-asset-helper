"""Phase 5 task 5.1 — /settings batch 카드 + POST /settings/batch + POST /settings/batch/jobs/{id}/cancel.

10 테스트:
  1. GET /settings 에 batch 카드 HTML 포함 확인 (threshold input, toggle radio, jobs list)
  2. POST /settings/batch → cfg.batch.threshold 업데이트 + 303 리다이렉트
  3. POST /settings/batch → cfg.batch.toggle 업데이트
  4. POST /settings/batch → cfg.batch.poll_interval_seconds 업데이트
  5. POST /settings/batch 음수 threshold → 1 로 clamp
  6. POST /settings/batch threshold > 200 → 200 으로 clamp
  7. POST /settings/batch invalid toggle → "auto" 폴백
  8. POST /settings/batch/jobs/{id}/cancel → BatchManager.cancel 호출 + 303 리다이렉트
  9. POST /settings/batch/jobs/{id}/cancel (batch_manager=None) → 404 또는 안전하게 303
 10. GET /settings active_batch_jobs 반영 확인 (job 리스트 in HTML)
"""
from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from assetcache.web.app import build_app


# ─── fixture helpers ────────────────────────────────────────────────────────


@pytest.fixture
def client(populated_deps):
    """기본 client — batch_manager 없음 (None)."""
    with TestClient(build_app(populated_deps), follow_redirects=False) as c:
        yield c


@pytest.fixture
def client_with_bm(populated_deps):
    """batch_manager mock 이 주입된 client."""
    mock_bm = MagicMock()
    mock_bm.cancel = MagicMock()
    # WebDeps 는 frozen dataclass — replace 로 새 인스턴스 생성
    deps_with_bm = dataclasses.replace(populated_deps, batch_manager=mock_bm)
    with TestClient(build_app(deps_with_bm), follow_redirects=False) as c:
        c.app.state._mock_bm = mock_bm  # 테스트에서 mock 접근용
        yield c


# ─── 1. GET /settings batch 카드 포함 확인 ──────────────────────────────────


def test_get_settings_contains_batch_section(client):
    """GET /settings HTML 에 batch 설정 섹션이 포함된다."""
    r = client.get("/settings")
    assert r.status_code == 200
    assert "batch-settings" in r.text or "batch" in r.text.lower()


def test_get_settings_batch_threshold_input(client):
    """GET /settings HTML 에 threshold input 이 포함된다."""
    r = client.get("/settings")
    assert r.status_code == 200
    assert 'name="threshold"' in r.text


def test_get_settings_batch_toggle_radios(client):
    """GET /settings HTML 에 toggle radio button 3개 (auto/forced_on/forced_off) 가 있다."""
    r = client.get("/settings")
    assert r.status_code == 200
    text = r.text
    assert 'value="auto"' in text
    assert 'value="forced_on"' in text
    assert 'value="forced_off"' in text


def test_get_settings_no_active_jobs_message(client):
    """active batch job 이 없을 때 '활성 배치 없음' 안내 메시지가 있다."""
    r = client.get("/settings")
    assert r.status_code == 200
    # 영어 또는 한글 안내문 모두 허용
    lower = r.text.lower()
    assert "no active batch" in lower or "활성" in r.text or "active_batch" in r.text.lower()


# ─── 2~4. POST /settings/batch 정상 처리 ─────────────────────────────────────


def test_post_batch_settings_threshold(client):
    """POST /settings/batch threshold=50 → cfg.batch.threshold=50 + 303 리다이렉트."""
    r = client.post(
        "/settings/batch",
        data={"threshold": "50", "toggle": "auto", "poll_interval_seconds": "1800"},
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/settings"
    # config 가 업데이트 됐는지 확인
    cfg = client.app.state.deps.config
    assert cfg.batch.threshold == 50


def test_post_batch_settings_toggle(client):
    """POST /settings/batch toggle=forced_on → cfg.batch.toggle='forced_on'."""
    r = client.post(
        "/settings/batch",
        data={"threshold": "30", "toggle": "forced_on", "poll_interval_seconds": "1800"},
    )
    assert r.status_code == 303
    cfg = client.app.state.deps.config
    assert cfg.batch.toggle == "forced_on"


def test_post_batch_settings_poll_interval(client):
    """POST /settings/batch poll_interval_seconds=3600 → cfg.batch.poll_interval_seconds=3600."""
    r = client.post(
        "/settings/batch",
        data={"threshold": "30", "toggle": "auto", "poll_interval_seconds": "3600"},
    )
    assert r.status_code == 303
    cfg = client.app.state.deps.config
    assert cfg.batch.poll_interval_seconds == 3600


# ─── 5~7. POST /settings/batch 유효성 검사 ──────────────────────────────────


def test_post_batch_settings_negative_threshold_clamped(client):
    """음수 threshold → 1 로 clamp."""
    r = client.post(
        "/settings/batch",
        data={"threshold": "-5", "toggle": "auto", "poll_interval_seconds": "1800"},
    )
    assert r.status_code == 303
    cfg = client.app.state.deps.config
    assert cfg.batch.threshold == 1


def test_post_batch_settings_over200_threshold_clamped(client):
    """threshold > 200 → 200 으로 clamp."""
    r = client.post(
        "/settings/batch",
        data={"threshold": "999", "toggle": "auto", "poll_interval_seconds": "1800"},
    )
    assert r.status_code == 303
    cfg = client.app.state.deps.config
    assert cfg.batch.threshold == 200


def test_post_batch_settings_invalid_toggle_fallback(client):
    """invalid toggle → 'auto' 로 폴백."""
    r = client.post(
        "/settings/batch",
        data={"threshold": "30", "toggle": "invalid_value", "poll_interval_seconds": "1800"},
    )
    assert r.status_code == 303
    cfg = client.app.state.deps.config
    assert cfg.batch.toggle == "auto"


# ─── 8. POST /settings/batch/jobs/{id}/cancel ────────────────────────────────


def test_cancel_batch_job_calls_batch_manager(client_with_bm):
    """POST /settings/batch/jobs/42/cancel → batch_manager.cancel(42) 호출 + 303."""
    mock_bm = client_with_bm.app.state._mock_bm
    r = client_with_bm.post("/settings/batch/jobs/42/cancel")
    assert r.status_code == 303
    assert r.headers["location"] == "/settings"
    mock_bm.cancel.assert_called_once_with(42)


# ─── 9. POST /settings/batch/jobs/{id}/cancel (batch_manager=None) ───────────


def test_cancel_batch_job_no_manager_is_safe(client):
    """batch_manager=None 일 때 cancel 요청이 500 없이 처리된다."""
    r = client.post("/settings/batch/jobs/1/cancel")
    # 404 (batch_manager 없음) 또는 303 (no-op) 모두 허용 — 500 만 금지
    assert r.status_code != 500


# ─── 10. GET /settings active_batch_jobs HTML 반영 ───────────────────────────


def test_get_settings_with_active_jobs(populated_deps, tmp_path):
    """active_batch_jobs 가 있을 때 HTML 에 job 정보가 렌더링된다."""
    import time
    from assetcache.core.batch.types import BatchJobRow

    # store 에 active batch job 삽입
    store = populated_deps.store
    job_id = store.save_batch_job(
        backend="gemini",
        modality="chat_image",
        backend_job_id="batches/test-job-001",
        asset_count=5,
        submitted_at=int(time.time()),
        expires_at=int(time.time()) + 86400,
        display_name="test job",
    )
    # state 를 'submitted' (active) 로 유지 (save_batch_job 기본 state = 'submitted')

    with TestClient(build_app(populated_deps), follow_redirects=False) as c:
        r = c.get("/settings")

    assert r.status_code == 200
    # job id 또는 backend 이름이 HTML 에 있어야 함
    assert "gemini" in r.text or str(job_id) in r.text
