"""Pack intake — walk a pack directory and reflect it into the store.

A pack is the top-level directory under ``library/``.  Ingestion is
idempotent: re-running it on an unchanged pack is cheap and leaves
already-analysed rows alone.  When a file's bytes change we update the
hash and reset the analysis flags so M2 can re-process it on the next
sweep.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Callable, Iterable

from .asset_kind import classify
from .manifest import load_manifest
from .store import Store

log = logging.getLogger(__name__)

_HASH_CHUNK_BYTES = 64 * 1024


def _stream_hash(file_path: Path) -> str:
    """blake2b-128 hex digest of ``file_path``'s bytes.

    DESIGN.md §5.1 documents the column as a free-form ``TEXT`` so we
    can change algorithms without a migration.  ``blake2b`` is in the
    standard library and avoids the extra ``xxhash`` dependency.
    """
    h = hashlib.blake2b(digest_size=16)
    with file_path.open("rb") as fh:
        while True:
            chunk = fh.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _iter_pack_files(pack_dir: Path) -> Iterable[Path]:
    """Yield every regular file inside ``pack_dir`` (recursive)."""
    for p in pack_dir.rglob("*"):
        if p.is_file():
            yield p


def ingest_pack(
    store: Store,
    pack_dir: Path,
    library_root: Path,
    *,
    now: Callable[[], float] = time.time,
) -> int:
    """Reflect ``pack_dir`` into the store and return its ``pack_id``.

    Parameters
    ----------
    store : Store
        Live, initialised store.
    pack_dir : Path
        Absolute path to the pack root (a direct child of ``library_root``).
    library_root : Path
        The library root used to derive relative POSIX paths.
    now : callable, optional
        Time source for ``added_at``/``scanned_at``; defaults to ``time.time``.
    """
    pack_dir = Path(pack_dir)
    library_root = Path(library_root)
    timestamp = int(now())

    manifest = load_manifest(pack_dir)
    pack_id = store.upsert_pack(pack_dir.name, manifest, scanned_at=timestamp)

    kept_rel_paths: set[str] = set()
    for file_path in _iter_pack_files(pack_dir):
        kind = classify(file_path)
        if kind is None:
            continue
        try:
            size = file_path.stat().st_size
            digest = _stream_hash(file_path)
        except OSError as exc:
            log.warning("skipping %s: %s", file_path, exc)
            continue
        rel = file_path.relative_to(library_root).as_posix()
        store.upsert_asset(pack_id, rel, kind, digest, size, added_at=timestamp)
        kept_rel_paths.add(rel)

    store.delete_assets_outside(pack_id, kept_rel_paths)
    return pack_id
