"""Tests for gah.core.watcher — pure debouncer behavior.

The watchdog Observer adapter (LibraryWatcher) is only smoke-checked at
import time; its real correctness shows up in M1 manual verification.
"""

from __future__ import annotations

from typing import List


class FakeClock:
    """A monotonic-style clock the test controls explicitly."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_debouncer_fires_after_window() -> None:
    from gah.core.watcher import PackDebouncer

    clock = FakeClock()
    fired: List[str] = []
    deb = PackDebouncer(window_seconds=2.0, clock=clock, on_fire=fired.append)

    deb.notify("kenney_demo")
    assert deb.tick() == []
    clock.advance(1.9)
    assert deb.tick() == []
    clock.advance(0.2)  # total 2.1s elapsed
    out = deb.tick()
    assert out == ["kenney_demo"]
    assert fired == ["kenney_demo"]


def test_debouncer_coalesces_within_window() -> None:
    from gah.core.watcher import PackDebouncer

    clock = FakeClock()
    fired: List[str] = []
    deb = PackDebouncer(window_seconds=2.0, clock=clock, on_fire=fired.append)

    for _ in range(5):
        deb.notify("kenney_demo")
        clock.advance(0.1)

    # only 0.5s elapsed; nothing fires yet
    assert deb.tick() == []

    clock.advance(3.0)
    out = deb.tick()
    assert out == ["kenney_demo"]
    assert fired == ["kenney_demo"]


def test_debouncer_resets_window_on_new_event() -> None:
    from gah.core.watcher import PackDebouncer

    clock = FakeClock()
    fired: List[str] = []
    deb = PackDebouncer(window_seconds=2.0, clock=clock, on_fire=fired.append)

    deb.notify("p")
    clock.advance(1.8)
    deb.notify("p")  # window resets

    clock.advance(1.0)  # total 2.8s, but only 1.0s since the last notify
    assert deb.tick() == []

    clock.advance(1.5)  # +1.5s since last notify
    assert deb.tick() == ["p"]
    assert fired == ["p"]


def test_debouncer_handles_multiple_packs_independently() -> None:
    from gah.core.watcher import PackDebouncer

    clock = FakeClock()
    fired: List[str] = []
    deb = PackDebouncer(window_seconds=2.0, clock=clock, on_fire=fired.append)

    deb.notify("alpha")
    clock.advance(1.0)
    deb.notify("beta")
    clock.advance(1.5)  # alpha has waited 2.5s, beta 1.5s

    out1 = deb.tick()
    assert out1 == ["alpha"]

    clock.advance(1.0)  # beta now 2.5s old
    out2 = deb.tick()
    assert out2 == ["beta"]

    assert fired == ["alpha", "beta"]


def test_debouncer_uses_injected_clock() -> None:
    """Sanity-check that nothing in the debouncer falls back to wall-clock time."""
    from gah.core.watcher import PackDebouncer

    clock = FakeClock(start=1_000_000.0)
    fired: List[str] = []
    deb = PackDebouncer(window_seconds=2.0, clock=clock, on_fire=fired.append)

    deb.notify("p")
    # if the implementation accidentally read time.monotonic(), 'now' might still
    # be far less than 1_000_002.0; with the fake clock, only an explicit advance
    # past the window should fire.
    clock.advance(2.5)
    assert deb.tick() == ["p"]
    assert fired == ["p"]
