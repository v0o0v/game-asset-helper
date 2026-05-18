"""Shared pytest fixtures for GAH tests.

Heavy third-party imports (numpy, Pillow, soundfile, respx, torch) are
deliberately inside fixture bodies / helper functions rather than at
module top level — that way pytest can still collect M0/M1 tests in an
environment where the M2 dev-extras have not been installed yet, which
matters during the bootstrap of milestone M2 itself.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterator

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def qt_offscreen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force Qt to use the offscreen platform plugin so PySide6 can import
    without a display server in CI/sandbox environments."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qapp():
    """Provide a singleton :class:`QApplication` for widget tests.

    PySide6 forbids more than one QApplication per process and several
    widget constructors (notably :class:`QMainWindow` + ``QShortcut``)
    deadlock when none exists.  This fixture creates one on demand and
    reuses it across tests, mirroring what ``gah.ui.test_ui_smoke``
    already does manually.
    """
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def tmp_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override GAH's data root to a fresh temp directory for the test."""
    monkeypatch.setenv("GAH_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def library_root(tmp_appdata: Path) -> Path:
    """A fresh, empty library directory inside the temporary AppData root."""
    root = tmp_appdata / "library"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def make_pack(library_root: Path) -> Callable[..., Path]:
    """Factory for building a pack directory under ``library_root``.

    Usage::

        pack_dir = make_pack(
            "kenney_demo",
            files={"PNG/hero.png": b"\\x89PNG...", "Sounds/jump.wav": b"RIFF..."},
            manifest={"name": "Kenney Demo", "vendor": "kenney"},
        )
    """

    def _make_pack(
        name: str,
        *,
        files: dict[str, bytes] | None = None,
        manifest: dict | None = None,
        manifest_format: str = "json",
    ) -> Path:
        pack_dir = library_root / name
        pack_dir.mkdir(parents=True, exist_ok=True)
        for rel, payload in (files or {}).items():
            file_path = pack_dir / rel
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(payload)
        if manifest is not None:
            if manifest_format == "json":
                (pack_dir / "pack.json").write_text(
                    json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
                )
            elif manifest_format == "toml":
                import tomli_w

                (pack_dir / "pack.toml").write_bytes(tomli_w.dumps(manifest).encode("utf-8"))
            else:  # pragma: no cover - defensive
                raise ValueError(f"unknown manifest_format: {manifest_format!r}")
        return pack_dir

    return _make_pack


@pytest.fixture
def store(tmp_appdata: Path) -> Iterator["object"]:
    """Initialised on-disk Store at ``tmp_appdata/test.db``.

    Returns the live Store object; callers can use ``store.conn`` if they
    need raw SQL access for assertions.
    """
    from gah.core.store import Store

    s = Store(tmp_appdata / "test.db")
    s.initialize()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def asset_factory(store, make_pack):
    """테스트에서 asset row 를 빠르게 만드는 factory fixture.

    Usage::

        aid = asset_factory()                    # 기본: pack 자동 생성
        aid = asset_factory(path="hero.png")     # 경로 지정
        aid = asset_factory(pack_id=42)          # 기존 pack 재사용

    반환값: assets.id (int).

    pack 이 새로 생성될 때는 ``make_pack`` 을 통해 디렉터리를 만들고
    ``store.upsert_pack`` 으로 DB 에 등록한다.  kind 기본값은 'sprite'.
    """
    import time

    from gah.core.manifest import PackManifest

    counter = {"n": 0}

    def _factory(
        *,
        path: str | None = None,
        pack_id: int | None = None,
        kind: str = "sprite",
    ) -> int:
        counter["n"] += 1
        n = counter["n"]

        if pack_id is None:
            pack_name = f"pack_for_asset_{n}"
            _pack_dir = make_pack(name=pack_name)
            manifest = PackManifest(
                display_name=pack_name,
                vendor=None,
                source_url=None,
                license=None,
                description=None,
            )
            pack_id = store.upsert_pack(
                pack_name, manifest, scanned_at=int(time.time())
            )

        rel_path = path or f"asset_{n}.png"
        return store.upsert_asset(
            pack_id,
            rel_path,
            kind,
            file_hash=f"hash_{n}",
            file_size=1024,
            added_at=int(time.time()),
        )

    return _factory


@pytest.fixture
def clean_root_logger():
    """Snapshot and restore the root logger so logging tests don't bleed."""
    import logging

    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    for h in list(root.handlers):
        root.removeHandler(h)
    try:
        yield root
    finally:
        for h in list(root.handlers):
            try:
                h.close()
            except Exception:
                pass
            root.removeHandler(h)
        for h in saved_handlers:
            root.addHandler(h)
        root.setLevel(saved_level)


# ─────────────────────────────────────────────────────────────────────
# M2 fixtures — deterministic test assets + HTTP/CLIP mocks
#
# Why deterministic generators instead of binary blobs in git?
#   * keeps the repo small and reviewable
#   * regenerates byte-identical files every time, so test results stay
#     reproducible across machines
#   * fixtures live under tests/fixtures/ but are .gitignored (see
#     .gitignore — only .gitkeep is tracked)
# ─────────────────────────────────────────────────────────────────────


def _build_tiny_pixel_32(path: Path) -> None:
    """32x32 pixel-art image with only 4 colors → triggers the pixel-art heuristic."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed=1234)
    palette = np.array(
        [[255, 80, 80], [80, 200, 80], [80, 80, 255], [240, 220, 60]],
        dtype=np.uint8,
    )
    indices = rng.integers(0, len(palette), size=(32, 32))
    img = palette[indices]
    Image.fromarray(img, mode="RGB").save(path)


def _build_tiny_vector_256(path: Path) -> None:
    """256x256 smooth gradient → should NOT be classified as pixel art."""
    import numpy as np
    from PIL import Image

    xs = np.linspace(0, 1, 256, dtype=np.float32)
    ys = np.linspace(0, 1, 256, dtype=np.float32)
    xx, yy = np.meshgrid(xs, ys)
    r = (xx * 255).astype(np.uint8)
    g = (yy * 255).astype(np.uint8)
    b = ((1 - xx) * 200 + (1 - yy) * 50).astype(np.uint8)
    img = np.stack([r, g, b], axis=-1)
    Image.fromarray(img, mode="RGB").save(path)


def _build_transparent_alpha(path: Path) -> None:
    """64x64 RGBA image with a real alpha channel."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed=42)
    rgba = rng.integers(0, 255, size=(64, 64, 4), dtype=np.uint8)
    Image.fromarray(rgba, mode="RGBA").save(path)


def _write_wav(path: Path, samples, sample_rate: int = 16000) -> None:
    import numpy as np
    import soundfile as sf

    arr = np.clip(samples, -1.0, 1.0).astype(np.float32)
    sf.write(str(path), arr, sample_rate, subtype="PCM_16")


def _build_short_sfx_1s(path: Path) -> None:
    """1 second 440Hz sine — exercises the 'short SFX → native path' branch."""
    import numpy as np

    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
    _write_wav(path, 0.5 * np.sin(2 * np.pi * 440 * t), sr)


def _build_medium_sfx_5s(path: Path) -> None:
    """5 second white-noise SFX."""
    import numpy as np

    sr = 16000
    rng = np.random.default_rng(seed=7)
    _write_wav(path, 0.3 * rng.standard_normal(sr * 5).astype(np.float32), sr)


def _build_long_bgm_45s(path: Path) -> None:
    """45 second multi-tone tonal loop — exercises the smart 3-chunk path."""
    import numpy as np

    sr = 16000
    duration = 45
    t = np.linspace(0, duration, sr * duration, endpoint=False, dtype=np.float32)
    tone = (
        0.3 * np.sin(2 * np.pi * 220 * t)
        + 0.2 * np.sin(2 * np.pi * 330 * t)
        + 0.1 * np.sin(2 * np.pi * 440 * t)
    )
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 0.1 * t)
    _write_wav(path, tone * env, sr)


def _build_mel_sample(path: Path) -> None:
    """A stand-in for the mel-spectrogram PNG used by the 2nd-tier sound fallback."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed=99)
    img = rng.integers(0, 255, size=(128, 256, 3), dtype=np.uint8)
    Image.fromarray(img, mode="RGB").save(path)


_FIXTURE_BUILDERS: dict[str, Callable[[Path], None]] = {
    "tiny_pixel_32.png": _build_tiny_pixel_32,
    "tiny_vector_256.png": _build_tiny_vector_256,
    "transparent_alpha.png": _build_transparent_alpha,
    "short_sfx_1s.wav": _build_short_sfx_1s,
    "medium_sfx_5s.wav": _build_medium_sfx_5s,
    "long_bgm_45s.wav": _build_long_bgm_45s,
    "mel_sample.png": _build_mel_sample,
}


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    """Absolute path to ``tests/fixtures``; lazily materializes any missing files.

    Session-scoped so the deterministic generators only fire once per
    test run — subsequent fixtures just observe the existing files.
    """
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, builder in _FIXTURE_BUILDERS.items():
        target = FIXTURES_DIR / name
        if not target.exists():
            builder(target)
    return FIXTURES_DIR


@pytest.fixture
def mock_ollama():
    """``respx`` router configured for both Ollama transports.

    Tests get a ready-made ``router`` object and can attach routes for
    ``POST /v1/chat/completions`` (OpenAI-compatible) and
    ``POST /api/chat`` (Ollama native).  ``assert_all_mocked=True`` means
    any unstubbed HTTP call is a test bug rather than a silent network
    hit.
    """
    import respx

    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


@pytest.fixture
def fake_clip_backend():
    """Deterministic CLIP stand-in.

    Imported lazily because ``gah.core.clip_labeler`` only exists once the
    C.3 step of M2 is implemented; until then this fixture will simply
    fail to collect — that is intentional and matches the RED phase.
    """
    from gah.core.clip_labeler import FakeBackend  # type: ignore[import-not-found]

    return FakeBackend(dim=128)


@pytest.fixture
def analyzer_inputs(fixture_dir: Path):
    """Factory that builds ``AnalyzerInput`` objects pointing at fixture files.

    Same lazy-import note as ``fake_clip_backend`` — only resolvable once
    ``gah.core.analyzer.base`` lands in C.4.
    """
    from gah.core.analyzer.base import AnalyzerInput  # type: ignore[import-not-found]

    def _build(
        name: str,
        *,
        asset_id: int = 1,
        pack_id: int = 1,
        rel_path: str | None = None,
        language: str = "ko",
    ) -> "AnalyzerInput":
        return AnalyzerInput(
            asset_id=asset_id,
            pack_id=pack_id,
            abs_path=fixture_dir / name,
            rel_path=rel_path or f"test_pack/{name}",
            language=language,
        )

    return _build


# ─────────────────────────────────────────────────────────────────────
# M3 fixtures — deterministic embedder + populated store + consistency
# summary builder + MCP tool deps.
#
# Same lazy-import policy as M2: any fixture that touches a yet-to-be-
# implemented M3 module imports it inside the fixture body, so M0/M1/M2
# tests still collect during the RED phase.
# ─────────────────────────────────────────────────────────────────────


def _fake_embed_vec(text: str, dim: int = 768) -> bytes:
    """Deterministic float32 LE vector derived from sha256(text).

    Used by the M3 ``HybridSearcher`` tests as a drop-in replacement for
    ``gah.core.embedding.EmbeddingEncoder`` — same byte format
    (float32 little-endian, dim * 4 bytes) so it round-trips through
    ``Store.semantic_candidates_load``.
    """
    import hashlib
    import struct

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Stretch the 32-byte digest into ``dim`` float32 values in [-1, 1].
    out = bytearray()
    for i in range(dim):
        b = digest[i % 32]
        # Center on 0, scale to roughly unit range.
        f = (b - 127.5) / 127.5
        out += struct.pack("<f", f)
    return bytes(out)


@pytest.fixture
def fake_embedder():
    """Lightweight stand-in for ``gah.core.embedding.EmbeddingEncoder``.

    Exposes the same surface used by the M3 search path::

        embedder.encode_text(text) -> (bytes, dim)
        embedder.decode_vector(blob, dim) -> np.ndarray

    The encoding is purely deterministic (sha256-derived), so query
    vectors hash to the same point as identical asset texts — handy for
    asserting that semantic similarity rises monotonically with text
    overlap in unit tests.
    """
    import numpy as np

    class _FakeEmbedder:
        def __init__(self, dim: int = 768) -> None:
            self.dim = dim
            self.model = "fake-embed"

        def encode_text(self, text: str) -> tuple[bytes, int]:
            return _fake_embed_vec(text, self.dim), self.dim

        def decode_vector(self, blob: bytes, dim: int) -> "np.ndarray":
            return np.frombuffer(blob, dtype="<f4", count=dim).copy()

    return _FakeEmbedder()


@pytest.fixture
def populated_store(store, fake_embedder):
    """A live Store seeded with 2 packs × 3 analyzed assets.

    Layout:

        pack_a (vendor=kenney,  main_style=pixel_art)
          ├─ assets/hero.png      labels: category=character, style=pixel_art
          ├─ assets/coin.png      labels: category=item,      style=pixel_art
          └─ sounds/jump.wav      labels: sound_category=sfx
        pack_b (vendor=craftpix, main_style=vector_cartoon)
          ├─ assets/menu_bg.png   labels: category=background, style=vector_cartoon
          ├─ assets/button.png    labels: category=ui,         style=vector_cartoon
          └─ sounds/bgm_loop.ogg  labels: sound_category=bgm, sound_mood=calm

    Each asset has analysis_state='ok', an embedding (via fake_embedder),
    label rows, and the parent pack carries an ``aggregate_meta`` JSON
    with ``main_style`` + ``palette``.  Returns a dict with handles for
    each row so tests can assert on stable IDs::

        store, ids = populated_store
        ids["pack_a"], ids["hero"], ids["bgm_loop"], ...
    """
    import json
    import time

    from gah.core.store import AssetRow  # noqa: F401 -- import sanity-check

    now = int(time.time())

    def _add_pack(name: str, vendor: str, main_style: str, palette: list[str]) -> int:
        store.conn.execute(
            "INSERT INTO packs (name, display_name, vendor, enabled, added_at, scanned_at, aggregate_meta) "
            "VALUES (?,?,?,1,?,?,?)",
            (
                name,
                name.replace("_", " ").title(),
                vendor,
                now,
                now,
                json.dumps({"main_style": main_style, "palette": palette}),
            ),
        )
        return int(store.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def _add_asset(
        pack_id: int, rel_path: str, kind: str, labels: list[tuple[str, str, float, str]]
    ) -> int:
        store.conn.execute(
            "INSERT INTO assets (pack_id, path, kind, file_hash, file_size, added_at, "
            "analyzed_at, analysis_state) VALUES (?,?,?,?,?,?,?,?)",
            (pack_id, rel_path, kind, "hash_" + rel_path, 1024, now, now, "ok"),
        )
        asset_id = int(store.conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        # FTS text — pack name + path + label tokens.
        fts_text = " ".join(
            [
                rel_path.replace("/", " "),
                kind,
                *(f"label:{label}" for _, label, _, _ in labels),
                *(f"{axis}:{label}" for axis, label, _, _ in labels),
            ]
        )
        store.conn.execute(
            "INSERT INTO assets_fts (asset_id, searchable_text) VALUES (?, ?)",
            (asset_id, fts_text),
        )
        # Labels.
        for axis, label, score, source in labels:
            store.conn.execute(
                "INSERT INTO asset_labels (asset_id, axis, label, score, source) "
                "VALUES (?,?,?,?,?)",
                (asset_id, axis, label, score, source),
            )
        # Embedding — fake deterministic.
        blob, dim = fake_embedder.encode_text(fts_text)
        store.conn.execute(
            "INSERT INTO asset_embeddings (asset_id, model, dim, vector) VALUES (?,?,?,?)",
            (asset_id, fake_embedder.model, dim, blob),
        )
        # kind-specific meta (minimal — just to satisfy joins).
        if kind == "sprite":
            store.conn.execute(
                "INSERT INTO sprite_meta (asset_id, width, height, has_alpha, "
                "is_pixel_art, dominant_colors) VALUES (?,?,?,?,?,?)",
                (asset_id, 64, 64, 0, 1 if "pixel" in fts_text else 0, json.dumps([])),
            )
        elif kind == "sound":
            store.conn.execute(
                "INSERT INTO sound_meta (asset_id, duration_ms, sample_rate, channels, "
                "audio_path_used) VALUES (?,?,?,?,?)",
                (asset_id, 1500, 16000, 1, "native"),
            )
        return asset_id

    with store.write_lock:
        pack_a = _add_pack(
            "pack_a", "kenney", "pixel_art", ["#aa1122", "#22aa11", "#1122aa"]
        )
        pack_b = _add_pack(
            "pack_b", "craftpix", "vector_cartoon", ["#ffffff", "#000000", "#888888"]
        )
        hero = _add_asset(
            pack_a,
            "pack_a/assets/hero.png",
            "sprite",
            [
                ("category", "character", 0.92, "gemma"),
                ("style", "pixel_art", 0.88, "gemma"),
            ],
        )
        coin = _add_asset(
            pack_a,
            "pack_a/assets/coin.png",
            "sprite",
            [
                ("category", "item", 0.91, "gemma"),
                ("style", "pixel_art", 0.85, "gemma"),
            ],
        )
        jump = _add_asset(
            pack_a,
            "pack_a/sounds/jump.wav",
            "sound",
            [("sound_category", "sfx", 0.93, "gemma")],
        )
        menu_bg = _add_asset(
            pack_b,
            "pack_b/assets/menu_bg.png",
            "sprite",
            [
                ("category", "background", 0.88, "gemma"),
                ("style", "vector_cartoon", 0.86, "gemma"),
            ],
        )
        button = _add_asset(
            pack_b,
            "pack_b/assets/button.png",
            "sprite",
            [
                ("category", "ui", 0.90, "gemma"),
                ("style", "vector_cartoon", 0.84, "gemma"),
            ],
        )
        bgm_loop = _add_asset(
            pack_b,
            "pack_b/sounds/bgm_loop.ogg",
            "sound",
            [
                ("sound_category", "bgm", 0.94, "gemma"),
                ("sound_mood", "calm", 0.81, "gemma"),
            ],
        )
        store.conn.commit()

    ids = {
        "pack_a": pack_a,
        "pack_b": pack_b,
        "hero": hero,
        "coin": coin,
        "jump": jump,
        "menu_bg": menu_bg,
        "button": button,
        "bgm_loop": bgm_loop,
    }
    return store, ids


@pytest.fixture
def consistency_summary_factory():
    """Builder for ``ProjectUsageSummary`` instances in consistency tests.

    Lazy import means the fixture is resolvable only after C.3 lands the
    ``gah.core.usage_tracker`` module — exactly the M2 pattern.
    """
    from gah.core.usage_tracker import ProjectUsageSummary  # type: ignore[import-not-found]

    def _make(
        *,
        pack_uses: dict[int, int] | None = None,
        vendor_uses: dict[str, int] | None = None,
        dominant_style: str | None = None,
        dominant_palette: list[str] | None = None,
    ) -> "ProjectUsageSummary":
        pu = dict(pack_uses or {})
        vu = dict(vendor_uses or {})
        return ProjectUsageSummary(
            pack_uses=pu,
            vendor_uses=vu,
            total_uses=sum(pu.values()),
            distinct_packs=len(pu),
            dominant_style=dominant_style,
            dominant_palette=list(dominant_palette or []),
        )

    return _make


@pytest.fixture
def mcp_tool_deps(populated_store, fake_embedder):
    """Factory for a ``ToolDeps`` carrying the live store + sensible defaults.

    Tests can override individual components by passing kwargs::

        deps = mcp_tool_deps(queue=None, registry=my_fake_registry)

    Resolves M3 modules lazily so RED-phase collection still works.
    """
    from gah.config import Config
    from gah.core.consistency import ConsistencyScorer  # type: ignore[import-not-found]
    from gah.core.search import HybridSearcher  # type: ignore[import-not-found]
    from gah.core.usage_tracker import UsageTracker  # type: ignore[import-not-found]
    from gah.core.labels import LabelRegistry
    from gah.mcp.tools import ToolDeps  # type: ignore[import-not-found]

    store, _ids = populated_store
    config = Config()
    registry = LabelRegistry(store)
    registry.bootstrap()
    consistency = ConsistencyScorer(store, config)
    usage = UsageTracker(store, config)
    search = HybridSearcher(store, fake_embedder, consistency, registry, config)

    def _build(**overrides):
        kwargs = dict(
            store=store,
            search=search,
            usage=usage,
            registry=registry,
            queue=None,
            config=config,
        )
        kwargs.update(overrides)
        return ToolDeps(**kwargs)

    return _build


# ─────────────────────────────────────────────────────────────────────
# M5 fixtures — WebDeps + PendingPickQueue (Phase 1B)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def deps_fixture(tmp_path):
    """M5 WebDeps — in-memory store + paths in tmp_path + 빈 PendingPickQueue.

    Phase 1B / 1C 의 FastAPI app factory + WebServer 테스트에서 사용.
    Ollama 네트워크 호출 없이 동작하도록 fake_embedder 패턴 재사용.
    """
    from gah.config import AppPaths, Config
    from gah.core.store import Store
    from gah.core.labels import LabelRegistry
    from gah.core.consistency import ConsistencyScorer
    from gah.core.usage_tracker import UsageTracker
    from gah.core.search import HybridSearcher
    from gah.web.deps import WebDeps
    from gah.web.pending import PendingPickQueue

    paths = AppPaths(
        data_dir=tmp_path,
        library_dir=tmp_path / "library",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "metadata.db",
        config_path=tmp_path / "config.toml",
        log_path=tmp_path / "logs" / "gah.log",
        lock_path=tmp_path / "gah.lock",
    )
    paths.ensure_dirs()

    cfg = Config()
    s = Store(paths.db_path)
    s.initialize()
    registry = LabelRegistry(s)
    # 빈 registry — Phase 1B 의 health/server 테스트는 시드 불필요

    # 네트워크 없이 동작하는 fake embedder (conftest._fake_embed_vec 재사용)
    import numpy as np

    class _FakeEmbedder:
        def __init__(self, dim: int = 768) -> None:
            self.dim = dim
            self.model = "fake-embed"

        def encode_text(self, text: str) -> tuple[bytes, int]:
            return _fake_embed_vec(text, self.dim), self.dim

        def decode_vector(self, blob: bytes, dim: int) -> np.ndarray:
            return np.frombuffer(blob, dtype="<f4", count=dim).copy()

    embedder = _FakeEmbedder()
    consistency = ConsistencyScorer(s, cfg)
    usage = UsageTracker(s, cfg)
    searcher = HybridSearcher(s, embedder, consistency, registry, cfg)
    pending = PendingPickQueue(max_pending=cfg.claude_pick_max_pending)
    deps = WebDeps(
        store=s,
        search=searcher,
        usage=usage,
        registry=registry,
        queue=None,
        config=cfg,
        paths=paths,
        pending_picks=pending,
        library_root=paths.library_dir,  # M5 bugfix: assets.path 상대경로 해석용
    )
    yield deps
    s.close()


@pytest.fixture
def populated_deps(tmp_path, populated_store, fake_embedder):
    """에셋이 채워진 WebDeps — 라이브러리/검색/모달/오디오/사이드패널 테스트 공통.

    populated_store (2 packs × 3 assets, bootstrap 포함) 를 WebDeps 로 래핑.
    6개 test_web_*.py 파일이 동일하게 정의하던 fixture 를 conftest 로 통합.
    """
    from gah.config import AppPaths, Config
    from gah.core.labels import LabelRegistry
    from gah.core.consistency import ConsistencyScorer
    from gah.core.usage_tracker import UsageTracker
    from gah.core.search import HybridSearcher
    from gah.web.deps import WebDeps
    from gah.web.pending import PendingPickQueue

    store, _ids = populated_store
    cfg = Config()
    paths = AppPaths(
        data_dir=tmp_path,
        library_dir=tmp_path / "library",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "metadata.db",
        config_path=tmp_path / "config.toml",
        log_path=tmp_path / "logs" / "gah.log",
        lock_path=tmp_path / "gah.lock",
    )
    paths.ensure_dirs()
    registry = LabelRegistry(store)
    registry.bootstrap()
    consistency = ConsistencyScorer(store, cfg)
    usage = UsageTracker(store, cfg)
    searcher = HybridSearcher(store, fake_embedder, consistency, registry, cfg)
    pending = PendingPickQueue(max_pending=cfg.claude_pick_max_pending)
    return WebDeps(
        store=store,
        search=searcher,
        usage=usage,
        registry=registry,
        queue=None,
        config=cfg,
        paths=paths,
        pending_picks=pending,
        library_root=paths.library_dir,  # M5 bugfix: assets.path 상대경로 해석용
    )


@pytest.fixture
def populated_client(populated_deps):
    """populated_deps 를 기반으로 한 TestClient — HTTP 레벨 통합 테스트용."""
    from fastapi.testclient import TestClient
    from gah.web.app import build_app

    with TestClient(build_app(populated_deps)) as c:
        yield c
