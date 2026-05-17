"""Concurrency tests for :class:`OllamaClient` — semaphore-based cap on
simultaneous backend calls.

Each test spins up *N* threads that hit ``chat()``/``embed()`` while a
respx handler measures the **in-flight count** at every entry.  The
invariant we want is::

    max(in_flight) <= client.parallel

regardless of how aggressively callers pile on.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager

import httpx
import pytest

from gah.core.ollama_client import ChatMessage, OllamaClient


# ── inflight tracker -------------------------------------------------


class _InFlightTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.current = 0
        self.max_seen = 0

    @contextmanager
    def enter(self, hold_seconds: float = 0.05):
        with self._lock:
            self.current += 1
            if self.current > self.max_seen:
                self.max_seen = self.current
        try:
            time.sleep(hold_seconds)
            yield
        finally:
            with self._lock:
                self.current -= 1


def _make_client(parallel: int = 2, max_retries: int = 0) -> OllamaClient:
    return OllamaClient(
        base_url="http://127.0.0.1:11434",
        model="gemma4:e4b",
        timeout_seconds=10.0,
        max_retries=max_retries,
        parallel=parallel,
    )


def _openai_ok(content_obj: dict = {"ok": True}) -> dict:  # noqa: B006
    import json
    return {
        "choices": [
            {"message": {"role": "assistant",
                         "content": json.dumps(content_obj)}}
        ]
    }


# ── tests ------------------------------------------------------------


def test_chat_caps_concurrent_calls_at_parallel(mock_ollama) -> None:
    tracker = _InFlightTracker()

    def handler(request: httpx.Request) -> httpx.Response:
        with tracker.enter(hold_seconds=0.08):
            pass
        return httpx.Response(200, json=_openai_ok())

    mock_ollama.post(
        "http://127.0.0.1:11434/v1/chat/completions"
    ).mock(side_effect=handler)

    client = _make_client(parallel=2)

    def worker() -> None:
        client.chat([ChatMessage(role="user", content="hi")])

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert tracker.max_seen <= 2, (
        f"semaphore should cap at parallel=2, observed max={tracker.max_seen}"
    )
    # 그리고 cap 이 의미 있어야 하므로 1 보다는 컸어야 한다 — 안 그러면 동시성 0.
    assert tracker.max_seen >= 2


def test_embed_shares_semaphore_with_chat(mock_ollama) -> None:
    """chat + embed 가 같은 cap 을 공유해야 backend 가 OOM 안 난다."""
    tracker = _InFlightTracker()

    def handler(request: httpx.Request) -> httpx.Response:
        with tracker.enter(hold_seconds=0.08):
            pass
        # respx 가 path 로 분기 — 응답 모양은 path 와 무관하게 OK 만
        if "embed" in request.url.path:
            return httpx.Response(
                200, json={"data": [{"embedding": [0.1, 0.2]}]}
            )
        return httpx.Response(200, json=_openai_ok())

    mock_ollama.post(
        "http://127.0.0.1:11434/v1/chat/completions"
    ).mock(side_effect=handler)
    mock_ollama.post(
        "http://127.0.0.1:11434/v1/embeddings"
    ).mock(side_effect=handler)

    client = _make_client(parallel=2)

    def call_chat() -> None:
        client.chat([ChatMessage(role="user", content="hi")])

    def call_embed() -> None:
        client.embed("hello world")

    threads = (
        [threading.Thread(target=call_chat) for _ in range(3)]
        + [threading.Thread(target=call_embed) for _ in range(3)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert tracker.max_seen <= 2


def test_parallel_one_serializes_completely(mock_ollama) -> None:
    tracker = _InFlightTracker()

    def handler(request: httpx.Request) -> httpx.Response:
        with tracker.enter(hold_seconds=0.04):
            pass
        return httpx.Response(200, json=_openai_ok())

    mock_ollama.post(
        "http://127.0.0.1:11434/v1/chat/completions"
    ).mock(side_effect=handler)

    client = _make_client(parallel=1)

    def worker() -> None:
        client.chat([ChatMessage(role="user", content="hi")])

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert tracker.max_seen == 1
