"""Batch domain dataclasses — pure data, no behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..llm.base import ChatMessage


@dataclass(frozen=True)
class BatchChatRequest:
    """Single asset 의 batch 요청 — chain.chat() 의 messages 와 1:1."""

    asset_id: int
    messages: list[ChatMessage] = field(default_factory=list)
    force_json: bool = True


@dataclass(frozen=True)
class GeminiBatchStatus:
    """`client.batches.get(name)` 결과를 정규화한 view.

    state: JOB_STATE_PENDING / RUNNING / SUCCEEDED / FAILED / CANCELLED / EXPIRED
    """

    state: str
    inlined_responses: list[Any] | None
    file_name: str | None
    error: str | None


@dataclass(frozen=True)
class BatchJobRow:
    """`batch_jobs` table row 의 read-only view."""

    id: int
    backend: str
    modality: str
    backend_job_id: str
    asset_count: int
    submitted_at: int
    expires_at: int
    state: str
    completed_at: int | None
    success_count: int
    failure_count: int
    error: str | None
    display_name: str | None
