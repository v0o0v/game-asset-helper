"""M5 — WebServer (uvicorn 별 스레드) 검증."""
from __future__ import annotations
import socket
import time
import pytest
import httpx

from gah.web.server import WebServer


def test_actual_port_set_after_start(deps_fixture):
    s = WebServer(deps_fixture)
    s.start()
    try:
        time.sleep(1.0)  # uvicorn 부팅 대기
        assert s.actual_port is not None
        assert s.actual_port >= deps_fixture.config.web_port
    finally:
        s.stop()


def test_port_file_written_on_start(deps_fixture):
    s = WebServer(deps_fixture)
    s.start()
    try:
        time.sleep(1.0)
        port_file = deps_fixture.paths.data_dir / "web.port"
        assert port_file.exists()
        assert int(port_file.read_text(encoding="utf-8").strip()) == s.actual_port
    finally:
        s.stop()


def test_health_after_start(deps_fixture):
    s = WebServer(deps_fixture)
    s.start()
    try:
        time.sleep(1.0)
        url = f"http://127.0.0.1:{s.actual_port}/api/health"
        r = httpx.get(url, timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
    finally:
        s.stop()


def test_port_fallback(deps_fixture):
    # 9874 점유 후 시작 → 9875 로 폴백
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        blocker.bind(("127.0.0.1", deps_fixture.config.web_port))
        blocker.listen(1)
    except OSError:
        pytest.skip(f"port {deps_fixture.config.web_port} unexpectedly unavailable")
    try:
        s = WebServer(deps_fixture)
        s.start()
        try:
            time.sleep(1.0)
            assert s.actual_port == deps_fixture.config.web_port + 1
        finally:
            s.stop()
    finally:
        blocker.close()


def test_stop_joins_thread(deps_fixture):
    s = WebServer(deps_fixture)
    s.start()
    time.sleep(0.5)
    s.stop()
    assert s.thread is None or not s.thread.is_alive()


def test_max_attempts_exceeded(deps_fixture):
    # 9874..9883 모두 점유 → RuntimeError
    blockers = []
    base = deps_fixture.config.web_port
    try:
        for offset in range(deps_fixture.config.web_port_max_attempts):
            b = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                b.bind(("127.0.0.1", base + offset))
                b.listen(1)
                blockers.append(b)
            except OSError:
                b.close()
                pytest.skip(f"port {base + offset} unexpectedly unavailable")
        s = WebServer(deps_fixture)
        with pytest.raises(RuntimeError, match="포트 할당 실패"):
            s.start()
    finally:
        for b in blockers:
            b.close()
