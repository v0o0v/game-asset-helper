"""Folder watcher + pack-scoped debouncer.

Splitting the watcher into two layers keeps the testable bits free of
``watchdog`` so they can be exercised without a real filesystem event
loop:

* ``PackDebouncer`` — pure logic with an injectable clock.  This is
  what M1's unit tests cover.
* ``LibraryWatcher`` — thin adapter around ``watchdog.Observer`` that
  routes filesystem events into the debouncer and pumps it on a timer.
  Its real correctness lives in M1 manual verification (dropping a
  folder into ``library/`` and watching the GUI update).
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)


class PackDebouncer:
    """Coalesces a stream of ``notify`` calls into one fire per quiet window.

    The class is intentionally synchronous: external code calls
    :meth:`notify` whenever it sees a filesystem event, and pumps
    :meth:`tick` on its own cadence.  Each call to :meth:`tick` returns
    the pack names that have been quiet for at least ``window_seconds``
    and invokes ``on_fire`` for each of them.
    """

    def __init__(
        self,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        on_fire: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.window_seconds = float(window_seconds)
        self._clock = clock
        self._on_fire = on_fire
        self._fire_at: dict[str, float] = {}

    def notify(self, pack_name: str) -> None:
        """Record an event for ``pack_name``; reset its quiet-window."""
        self._fire_at[pack_name] = self._clock() + self.window_seconds

    def tick(self) -> list[str]:
        """Return (and drop) pack names whose window has elapsed."""
        now = self._clock()
        due = [name for name, deadline in self._fire_at.items() if deadline <= now]
        for name in due:
            self._fire_at.pop(name, None)
            if self._on_fire is not None:
                try:
                    self._on_fire(name)
                except Exception:  # pragma: no cover - callback errors shouldn't kill watcher
                    log.exception("on_fire callback failed for pack %r", name)
        return due

    def pending(self) -> list[str]:
        """Pack names that have been notified but not yet fired (mainly for debugging)."""
        return list(self._fire_at)


class LibraryWatcher:
    """``watchdog`` adapter that drives a :class:`PackDebouncer`.

    Use::

        watcher = LibraryWatcher(window_seconds=2.0,
                                 on_pack_changed=enqueue_intake)
        watcher.start(library_root)
        ...
        watcher.stop()

    ``on_pack_changed`` is invoked from a background thread, so callers
    that touch GUI state must marshal back to the main thread.
    """

    _PUMP_INTERVAL_SECONDS = 0.5

    def __init__(
        self,
        *,
        window_seconds: float = 2.0,
        on_pack_changed: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._debouncer = PackDebouncer(
            window_seconds=window_seconds,
            on_fire=on_pack_changed,
        )
        self._observer = None  # type: ignore[assignment]
        self._pump_stop = threading.Event()
        self._pump_thread: Optional[threading.Thread] = None
        self._library_root: Optional[Path] = None

    def start(self, library_root: Path) -> None:
        # watchdog is an import-time-heavy module; defer it to the start path.
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        library_root = Path(library_root).resolve()
        library_root.mkdir(parents=True, exist_ok=True)
        self._library_root = library_root

        debouncer = self._debouncer

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event) -> None:
                pack = _pack_name_for_event(library_root, event.src_path)
                if pack:
                    debouncer.notify(pack)
                # moved events: the *destination* may also lie under a pack
                dest = getattr(event, "dest_path", None)
                if dest:
                    pack_dest = _pack_name_for_event(library_root, dest)
                    if pack_dest:
                        debouncer.notify(pack_dest)

        observer = Observer()
        observer.schedule(_Handler(), str(library_root), recursive=True)
        observer.start()
        self._observer = observer

        self._pump_stop.clear()
        self._pump_thread = threading.Thread(
            target=self._pump_loop, name="assetcache-watcher-pump", daemon=True
        )
        self._pump_thread.start()
        log.info("LibraryWatcher started for %s", library_root)

    def stop(self) -> None:
        self._pump_stop.set()
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:  # pragma: no cover
                log.exception("error while stopping watchdog observer")
            self._observer = None
        if self._pump_thread is not None:
            self._pump_thread.join(timeout=2.0)
            self._pump_thread = None

    def _pump_loop(self) -> None:
        while not self._pump_stop.is_set():
            self._debouncer.tick()
            self._pump_stop.wait(self._PUMP_INTERVAL_SECONDS)


def _pack_name_for_event(library_root: Path, raw_path: str) -> Optional[str]:
    """Return the first directory segment under ``library_root``, or ``None``."""
    try:
        rel = Path(raw_path).resolve().relative_to(library_root)
    except (ValueError, OSError):
        return None
    parts = rel.parts
    if not parts:
        return None
    # Event on library root itself, or a file directly inside library/, never a pack.
    if len(parts) == 1 and not (library_root / parts[0]).is_dir():
        return None
    return parts[0]
