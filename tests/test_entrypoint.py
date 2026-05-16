"""Tests for the CLI entrypoint in gah.__main__."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(args: list[str], env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["QT_QPA_PLATFORM"] = "offscreen"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "gah", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_version_flag_prints_version_and_exits_zero() -> None:
    result = _run(["--version"])
    assert result.returncode == 0, result.stderr
    from gah import __version__

    assert __version__ in (result.stdout + result.stderr)


def test_mcp_flag_returns_not_implemented_exit_code(tmp_path: Path) -> None:
    result = _run(["--mcp", "--data-dir", str(tmp_path)])
    assert result.returncode == 2
    assert "not implemented" in (result.stdout + result.stderr).lower()


def test_data_dir_override_used(tmp_path: Path) -> None:
    """--data-dir must win over GAH_DATA_DIR and create files in the given path."""
    other = tmp_path / "elsewhere"
    result = _run(
        ["--data-dir", str(other), "--mcp"],   # --mcp exits fast (code 2) but should
                                               #  still trigger paths.ensure_dirs first
        env_extra={"GAH_DATA_DIR": str(tmp_path / "ignored")},
    )
    assert result.returncode == 2
    assert (other / "config.toml").exists()
    assert not (tmp_path / "ignored" / "config.toml").exists()
