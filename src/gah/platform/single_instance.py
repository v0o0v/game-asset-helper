"""Cross-platform single-instance enforcement via an exclusive file lock.

DESIGN.md §9 calls for a `gah.lock` file under the AppData root that
prevents a second tray-mode invocation from launching.  We use
``portalocker`` for the OS-level exclusive lock (Windows + POSIX).
The lock file itself stores the holder's PID for human debugging; the
real mutual exclusion is the kernel lock, so a stale file from a
crashed previous run is automatically recoverable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO, Optional

import portalocker


class AlreadyRunning(RuntimeError):
    """Raised when another GAH instance currently holds the lock."""

    def __init__(self, lock_path: Path, holder_pid: Optional[int] = None) -> None:
        self.lock_path = lock_path
        self.holder_pid = holder_pid
        msg = f"Another instance is already running (lock: {lock_path}"
        if holder_pid is not None:
            msg += f", pid={holder_pid}"
        msg += ")"
        super().__init__(msg)


class SingleInstance:
    """Context manager that grants exclusive ownership of ``lock_path``."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = Path(lock_path)
        self._fh: Optional[IO[str]] = None

    def __enter__(self) -> "SingleInstance":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_path, "a+", encoding="utf-8")
        try:
            portalocker.lock(fh, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.LockException as exc:
            holder = self._read_pid_from(fh)
            fh.close()
            raise AlreadyRunning(self.lock_path, holder) from exc
        # We hold the lock — record our pid for diagnostics.
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(f"{os.getpid()}\n")
            fh.flush()
        except OSError:
            pass
        self._fh = fh
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fh is None:
            return
        try:
            portalocker.unlock(self._fh)
        except Exception:
            pass
        try:
            self._fh.close()
        except Exception:
            pass
        self._fh = None
        # Best-effort cleanup of the on-disk marker.
        try:
            self.lock_path.unlink()
        except OSError:
            pass

    @staticmethod
    def _read_pid_from(fh: IO[str]) -> Optional[int]:
        try:
            fh.seek(0)
            content = fh.read().strip()
            return int(content) if content else None
        except (OSError, ValueError):
            return None
