"""Phase 6 task 6.2 — 옵트인 Gemini Batch API integration.

`pytest -m llm_integration` 으로 실행. GEMINI_API_KEY 환경변수 필요.

실 24h 대기 없이 즉시 cancel 로 검증 (submit + cancel + get unknown).
"""

import os
import time

import pytest

pytestmark = pytest.mark.llm_integration


@pytest.fixture
def gemini_real():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set")
    from assetcache.core.llm.backends.gemini import GeminiBackend
    return GeminiBackend(
        api_key=api_key,
        model_image="gemini-3.1-flash-lite",
        model_audio="gemini-3.1-flash-lite",
        model_embed="gemini-embedding-001",
        timeout=60.0,
    )


def test_batch_chat_submit_and_cancel(gemini_real):
    """실 submit → 즉시 cancel (24h 대기 X)."""
    from assetcache.core.batch.types import BatchChatRequest
    from assetcache.core.llm.base import ChatMessage
    job_name = gemini_real.batch_chat(
        modality="chat_image",
        requests=[
            BatchChatRequest(
                asset_id=1,
                messages=[ChatMessage(role="user", content="Say hi in JSON: {\"reply\": \"hi\"}")],
                force_json=True,
            ),
        ],
    )
    assert job_name.startswith("batches/")

    # 즉시 cancel
    gemini_real.batch_cancel(job_name)
    # 잠시 후 상태 확인 (cancelled / running / pending — 어느 것이든 OK)
    time.sleep(2)
    status = gemini_real.batch_get(job_name)
    assert status.state in (
        "JOB_STATE_CANCELLED", "JOB_STATE_RUNNING",
        "JOB_STATE_PENDING", "JOB_STATE_SUCCEEDED",
    )


def test_batch_embed_submit_and_cancel(gemini_real):
    """Embed batch submit + cancel."""
    job_name = gemini_real.batch_embed(texts=["alpha", "beta"])
    assert job_name.startswith("batches/")
    gemini_real.batch_cancel(job_name)


def test_batch_get_unknown_returns_error(gemini_real):
    """존재하지 않는 job_name → BackendError."""
    from assetcache.core.llm.base import BackendError
    with pytest.raises(BackendError):
        gemini_real.batch_get("batches/does-not-exist-9999-fake")
