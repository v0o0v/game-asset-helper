"""M5 — uvicorn 을 별 스레드 + 별 asyncio 루프에서 실행하는 WebServer.

트레이 Qt main thread 가 본 클래스를 부팅 (`start`) → 새 스레드에서
`uvicorn.Server.serve()` async 진입. 종료 시 `should_exit=True + join`.

포트 폴백: `Config.web_port` 부터 `web_port_max_attempts` 번 시도.
성공 시 실 사용 포트를 `paths.data_dir/web.port` 에 atomic write
(MCP server 가 별 프로세스라 같은 파일로 URL 공유).
"""
from __future__ import annotations

import asyncio
import logging
import socket
import threading

import uvicorn

from .app import build_app
from .deps import WebDeps
from .url import write_web_port

log = logging.getLogger(__name__)


class WebServer:
    """uvicorn 을 별 스레드 + 별 asyncio 루프에서 실행하는 WebServer."""

    def __init__(self, deps: WebDeps) -> None:
        self.deps = deps
        self.thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self.actual_port: int | None = None

    def start(self) -> None:
        """포트를 확보하고 uvicorn 서버를 백그라운드 스레드에서 시작한다."""
        port = self._find_available_port()
        app = build_app(self.deps)
        # health endpoint 가 실 port 를 반환할 수 있도록 app.state 에 기록한다.
        app.state.web_port = port
        config = uvicorn.Config(
            app,
            host=self.deps.config.web_host,
            port=port,
            log_level="info" if self.deps.config.web_log_requests else "warning",
            loop="asyncio",
            lifespan="on",
            access_log=self.deps.config.web_log_requests,
        )
        self._server = uvicorn.Server(config)
        self.actual_port = port
        write_web_port(self.deps.paths.data_dir, port)
        self.thread = threading.Thread(
            target=self._run_loop, daemon=True, name="GAH-WebServer",
        )
        self.thread.start()
        log.info("WebServer 시작 — port=%d thread=%s", port, self.thread.name)

    def _run_loop(self) -> None:
        """새 asyncio 루프를 만들고 uvicorn.Server.serve() 를 실행한다."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._server.serve())
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # pragma: no cover
                pass
            loop.close()

    def _find_available_port(self) -> int:
        """base 포트부터 max_attempts 번 시도해 사용 가능한 포트를 반환한다."""
        base = self.deps.config.web_port
        host = self.deps.config.web_host
        attempts = self.deps.config.web_port_max_attempts
        last_err: OSError | None = None
        for offset in range(attempts):
            port = base + offset
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sk:
                try:
                    sk.bind((host, port))
                    return port
                except OSError as e:
                    last_err = e
                    continue
        raise RuntimeError(
            f"포트 할당 실패: {base}..{base + attempts - 1} 모두 점유 ({last_err})"
        )

    def stop(self, timeout: float = 5.0) -> None:
        """should_exit 플래그를 세우고 스레드가 종료될 때까지 최대 timeout 초 대기."""
        if self._server is not None:
            self._server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=timeout)
            if self.thread.is_alive():
                log.warning("WebServer 스레드가 %.1fs 안에 종료 안 됨", timeout)
            self.thread = None
        log.info("WebServer 종료")
