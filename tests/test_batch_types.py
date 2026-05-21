"""Phase 0 — core/batch/types.py dataclass smoke."""

from assetcache.core.batch.types import (
    BatchChatRequest,
    BatchJobRow,
    GeminiBatchStatus,
)
from assetcache.core.llm.base import ChatMessage


def test_batch_chat_request_dataclass():
    req = BatchChatRequest(
        asset_id=42,
        messages=[ChatMessage(role="user", content="hi")],
        force_json=True,
    )
    assert req.asset_id == 42
    assert req.force_json is True
    assert req.messages[0].content == "hi"


def test_gemini_batch_status_dataclass():
    s = GeminiBatchStatus(
        state="JOB_STATE_RUNNING",
        inlined_responses=None,
        file_name=None,
        error=None,
    )
    assert s.state == "JOB_STATE_RUNNING"
    assert s.inlined_responses is None


def test_batch_job_row_dataclass():
    row = BatchJobRow(
        id=1,
        backend="gemini",
        modality="chat_image",
        backend_job_id="batches/abc",
        asset_count=30,
        submitted_at=1000,
        expires_at=1000 + 172800,
        state="submitted",
        completed_at=None,
        success_count=0,
        failure_count=0,
        error=None,
        display_name="assetcache-chat_image-1000",
    )
    assert row.asset_count == 30
    assert row.modality == "chat_image"


def test_batch_chat_request_force_json_default():
    req = BatchChatRequest(asset_id=1, messages=[])
    assert req.force_json is True  # default
