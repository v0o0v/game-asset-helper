"""M3 — MCP stdio 실제 subprocess 통합 (opt-in, slow).

기본 pytest 실행에서는 `addopts = -m 'not mcp_integration'` 로 제외된다.
명시적으로 돌리려면 `pytest -m mcp_integration`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.mcp_integration


def _spawn(tmp_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["GAH_DATA_DIR"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    # Force UTF-8 on both sides so multi-byte JSON payloads survive Windows cp949.
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        [sys.executable, "-m", "gah", "--mcp", "--data-dir", str(tmp_path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, text=True, encoding="utf-8", errors="replace", bufsize=1,
    )


def _write_jsonrpc(proc: subprocess.Popen, payload: dict) -> None:
    line = json.dumps(payload) + "\n"
    assert proc.stdin is not None
    proc.stdin.write(line)
    proc.stdin.flush()


def _read_jsonrpc_response(proc: subprocess.Popen, timeout_s: float = 10.0) -> dict:
    import select
    import time

    assert proc.stdout is not None
    deadline = time.monotonic() + timeout_s
    buffer = ""
    while time.monotonic() < deadline:
        # Cross-platform readline with timeout via select (POSIX) or short reads (Win).
        if sys.platform == "win32":
            line = proc.stdout.readline()
            if line:
                buffer += line
                try:
                    return json.loads(buffer)
                except json.JSONDecodeError:
                    continue
        else:
            r, _, _ = select.select([proc.stdout], [], [], 0.2)
            if r:
                chunk = os.read(proc.stdout.fileno(), 4096).decode("utf-8", errors="replace")
                buffer += chunk
                try:
                    # Try parsing each newline-separated message.
                    for line in buffer.splitlines():
                        if not line.strip():
                            continue
                        msg = json.loads(line)
                        return msg
                except json.JSONDecodeError:
                    continue
    raise TimeoutError(f"No response within {timeout_s}s; buffer={buffer!r}")


def test_stdio_subprocess_initialize_handshake(tmp_path):
    proc = _spawn(tmp_path)
    try:
        _write_jsonrpc(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        })
        resp = _read_jsonrpc_response(proc)
        assert resp.get("id") == 1
        assert "result" in resp
        assert "serverInfo" in resp["result"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_stdio_subprocess_tools_list_returns_17(tmp_path):
    """M3 의 12 → M4 의 16 → M5 의 17 (request_user_pick 신규 도구 추가)."""
    proc = _spawn(tmp_path)
    try:
        # initialize
        _write_jsonrpc(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "0"}},
        })
        _read_jsonrpc_response(proc)
        # notifications/initialized — fire-and-forget
        _write_jsonrpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        # tools/list
        _write_jsonrpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        resp = _read_jsonrpc_response(proc, timeout_s=15.0)
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        expected = {
            # M3 12 도구
            "find_asset", "get_asset", "list_assets", "list_packs", "suggest_packs",
            "record_asset_use", "set_project_pin", "request_rescan", "report_feedback",
            "list_label_axes", "list_labels", "describe_label",
            # M4 4 신규 도구
            "save_search", "list_saved_searches", "delete_saved_search",
            "run_saved_search",
            # M5 Phase 4C 1 신규 도구
            "request_user_pick",
        }
        assert expected <= names
        assert len(names) == 17
    finally:
        proc.terminate()
        proc.wait(timeout=5)
