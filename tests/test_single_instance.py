"""Tests for gah.platform.single_instance."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_first_instance_acquires_lock(tmp_path: Path) -> None:
    from gah.platform.single_instance import SingleInstance

    lock = tmp_path / "gah.lock"
    with SingleInstance(lock) as inst:
        assert inst is not None
        assert lock.exists()


def test_second_instance_raises_already_running(tmp_path: Path) -> None:
    from gah.platform.single_instance import AlreadyRunning, SingleInstance

    lock = tmp_path / "gah.lock"
    with SingleInstance(lock):
        with pytest.raises(AlreadyRunning):
            with SingleInstance(lock):
                pass


def test_lock_released_after_context_exit(tmp_path: Path) -> None:
    from gah.platform.single_instance import SingleInstance

    lock = tmp_path / "gah.lock"
    with SingleInstance(lock):
        pass
    # After first context exit a new instance must succeed.
    with SingleInstance(lock):
        pass


def test_stale_lock_file_does_not_block(tmp_path: Path) -> None:
    """If a lock file exists but no process is holding the OS-level lock,
    a new instance must still be able to acquire it (recovery from a crash)."""
    from gah.platform.single_instance import SingleInstance

    lock = tmp_path / "gah.lock"
    lock.write_text("99999\n", encoding="utf-8")  # stale PID, no real lock
    with SingleInstance(lock):
        pass
