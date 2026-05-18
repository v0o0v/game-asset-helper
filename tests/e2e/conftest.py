"""M5 Phase 6+ — Playwright e2e 테스트 인프라.

각 e2e 테스트가 실제 FastAPI + uvicorn + 헤드리스 Chromium 으로 동작.
mcp_integration 처럼 opt-in 마크 (-m e2e) 라 기본 회귀에서 제외.
"""
from __future__ import annotations

import hashlib
import socket
import struct
import time
from pathlib import Path

import numpy as np
import pytest


# ─────────────────────────────────────────────────────────────────────
# 세션 공유 라이브러리 디렉터리 (sprite + sound 실파일 시드)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def e2e_library_root(tmp_path_factory):
    """e2e 세션 동안 공유할 라이브러리 디렉터리. 실 sprite/sound 파일 시드."""
    from PIL import Image
    import soundfile as sf

    root = tmp_path_factory.mktemp("e2e_library")

    # sprite: 64x64 랜덤 PNG
    pack_a = root / "test_pack"
    pack_a.mkdir()
    rng = np.random.default_rng(seed=42)
    img = rng.integers(0, 255, size=(64, 64, 3), dtype=np.uint8)
    Image.fromarray(img, mode="RGB").save(pack_a / "hero.png")

    # sound: 1초 440Hz 사인파 WAV
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
    sf.write(str(pack_a / "jump.wav"), 0.3 * np.sin(2 * np.pi * 440 * t), sr)

    return root


# ─────────────────────────────────────────────────────────────────────
# Fake embedder — Ollama 없이 동작
# ─────────────────────────────────────────────────────────────────────


class _FakeEmbedder:
    """sha256 기반 결정론적 임베더 (네트워크 불필요)."""

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim
        self.model = "fake-e2e"

    def encode_text(self, text: str) -> tuple[bytes, int]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        out = bytearray()
        for i in range(self.dim):
            b = digest[i % 32]
            out += struct.pack("<f", (b - 127.5) / 127.5)
        return bytes(out), self.dim

    def decode_vector(self, blob: bytes, dim: int) -> np.ndarray:
        return np.frombuffer(blob, dtype="<f4", count=dim).copy()


# ─────────────────────────────────────────────────────────────────────
# 세션 공유 WebServer (uvicorn 백그라운드 스레드)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def e2e_web_server(e2e_library_root, tmp_path_factory):
    """uvicorn WebServer 를 백그라운드 스레드로 부팅. 세션 끝나면 stop."""
    from gah.config import AppPaths, Config
    from gah.core.consistency import ConsistencyScorer
    from gah.core.labels import LabelRegistry
    from gah.core.scanner import reconcile_library
    from gah.core.search import HybridSearcher
    from gah.core.store import Store
    from gah.core.usage_tracker import UsageTracker
    from gah.web.deps import WebDeps
    from gah.web.pending import PendingPickQueue
    from gah.web.server import WebServer

    tmp_dir = tmp_path_factory.mktemp("e2e_appdata")
    paths = AppPaths(
        data_dir=tmp_dir,
        library_dir=e2e_library_root,
        cache_dir=tmp_dir / "cache",
        db_path=tmp_dir / "metadata.db",
        config_path=tmp_dir / "config.toml",
        log_path=tmp_dir / "logs" / "gah.log",
        lock_path=tmp_dir / "gah.lock",
    )
    paths.ensure_dirs()

    # 임의의 사용 가능한 포트 확보 (race 방지 — max_attempts=1 로 묶음)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    cfg = Config()
    cfg.web_port = port
    cfg.web_port_max_attempts = 1  # 위에서 확보한 포트만 시도

    store = Store(paths.db_path)
    store.initialize()
    registry = LabelRegistry(store)
    registry.bootstrap()

    # 라이브러리 스캔 — hero.png + jump.wav 를 DB 에 인덱싱
    reconcile_library(store, e2e_library_root)

    # 분석은 생략 (Ollama 의존). 자산은 analysis_state="pending" 상태.
    # 검색/카드/썸네일 엔드포인트는 pending 상태에서도 동작해야 함.

    embedder = _FakeEmbedder()
    consistency = ConsistencyScorer(store, cfg)
    usage = UsageTracker(store, cfg)
    searcher = HybridSearcher(store, embedder, consistency, registry, cfg)
    pending = PendingPickQueue(max_pending=cfg.claude_pick_max_pending)
    deps = WebDeps(
        store=store,
        search=searcher,
        usage=usage,
        registry=registry,
        queue=None,
        config=cfg,
        paths=paths,
        pending_picks=pending,
        library_root=e2e_library_root,
    )

    server = WebServer(deps)
    server.start()

    # 부팅 대기 — 최대 5초
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.settimeout(0.1)
            probe.connect(("127.0.0.1", server.actual_port))
            probe.close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        server.stop()
        store.close()
        raise RuntimeError(f"e2e WebServer 부팅 타임아웃 (port={port})")

    yield server

    server.stop()
    store.close()


# ─────────────────────────────────────────────────────────────────────
# 테스트별 편의 fixture
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def e2e_url(e2e_web_server):
    """페이지 진입용 base URL."""
    return f"http://127.0.0.1:{e2e_web_server.actual_port}"
