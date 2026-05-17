"""Concurrency tests for :class:`ClipLabeler` — a single ``threading.Lock``
serialises ``score_image()`` and ``warmup()`` because the underlying torch
model is not thread-safe.

The ``FakeBackend`` is extended in-test with an inflight counter so the
serialisation invariant ``in_flight <= 1`` is checkable without standing
up an actual CLIP model.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np

from gah.core.clip_labeler import ClipLabeler, FakeBackend


class _InstrumentedBackend(FakeBackend):
    """``FakeBackend`` that records max-concurrent calls."""

    def __init__(self, *, dim: int = 32, hold_seconds: float = 0.03) -> None:
        super().__init__(dim=dim, model_id="instrumented-clip:test")
        self._cnt_lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0
        self.hold_seconds = hold_seconds

    def _enter(self) -> None:
        with self._cnt_lock:
            self.in_flight += 1
            if self.in_flight > self.max_in_flight:
                self.max_in_flight = self.in_flight

    def _exit(self) -> None:
        with self._cnt_lock:
            self.in_flight -= 1

    def encode_text(self, texts: list[str]) -> np.ndarray:
        self._enter()
        try:
            time.sleep(self.hold_seconds)
            return super().encode_text(texts)
        finally:
            self._exit()

    def encode_image(self, image_path: Path) -> np.ndarray:
        self._enter()
        try:
            time.sleep(self.hold_seconds)
            return super().encode_image(image_path)
        finally:
            self._exit()


class _StubRegistry:
    """Minimal LabelRegistry stand-in — just returns a fixed label list."""

    def __init__(self, labels: list[str]) -> None:
        self._labels = labels

    def list_labels(self, *, axis: str | None = None,
                    enabled_only: bool = True,
                    with_description: bool = False) -> list[str]:
        # `axis` 없어도 모두 반환 — 테스트는 visual axes 14 축에서 호출됨
        return list(self._labels)


def _make_labeler(store, *, hold: float = 0.03) -> ClipLabeler:
    backend = _InstrumentedBackend(hold_seconds=hold)
    registry = _StubRegistry(["pixel_art", "vector_flat", "heroic", "cute"])
    return ClipLabeler(
        backend=backend, store=store, registry=registry, enabled=True,
    )


def test_score_image_serialized_across_threads(store, fixture_dir) -> None:
    labeler = _make_labeler(store, hold=0.03)
    image = fixture_dir / "tiny_pixel_32.png"

    def worker() -> None:
        labeler.score_image(image)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert labeler.backend.max_in_flight == 1, (
        f"ClipLabeler must serialize backend calls; observed max="
        f"{labeler.backend.max_in_flight}"
    )


def test_warmup_serialized_across_threads(store) -> None:
    labeler = _make_labeler(store, hold=0.02)

    def worker() -> None:
        labeler.warmup()

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert labeler.backend.max_in_flight == 1
