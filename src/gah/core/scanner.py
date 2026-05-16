"""Boot-time full-scan reconciler.

On startup we don't trust that the on-disk library matches the DB: a
pack folder may have been added, removed, or its bytes changed while
GAH wasn't running.  ``reconcile_library`` walks the library root,
ingests every pack found, and deletes DB rows for packs whose folder no
longer exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .pack_manager import ingest_pack
from .store import Store

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconcileReport:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    rescanned: list[str] = field(default_factory=list)


def _disk_pack_names(library_root: Path) -> list[str]:
    if not library_root.exists():
        return []
    return sorted(p.name for p in library_root.iterdir() if p.is_dir())


def reconcile_library(store: Store, library_root: Path) -> ReconcileReport:
    """Walk ``library_root`` and bring the store in sync with disk."""
    library_root = Path(library_root)

    disk_names = _disk_pack_names(library_root)
    db_packs = {p.name: p for p in store.list_packs(include_disabled=True)}

    added: list[str] = []
    rescanned: list[str] = []
    for name in disk_names:
        if name in db_packs:
            rescanned.append(name)
        else:
            added.append(name)
        ingest_pack(store, library_root / name, library_root)

    removed: list[str] = []
    for name, row in db_packs.items():
        if name not in disk_names:
            store.delete_pack(row.id)
            removed.append(name)

    # Stray files at library root: log once but do not enter the report.
    if library_root.exists():
        strays = [p.name for p in library_root.iterdir() if p.is_file()]
        if strays:
            log.warning("ignoring %d non-pack file(s) at library root: %s", len(strays), strays)

    return ReconcileReport(added=added, removed=removed, rescanned=rescanned)
