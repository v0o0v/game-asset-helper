"""SQLite store for Game Asset Helper.

M1 owns the ``packs``, ``assets``, ``tags`` and ``asset_tags`` tables
described in ``DESIGN.md §5.1``.  The richer schema (``sprite_meta``,
``sound_meta``, ``assets_fts``, ``asset_embeddings``, ``projects``,
``asset_usage``, ``search_queries``, ``unity_imports``) is the
responsibility of later milestones — adding them here would inflate
M1's surface area and lock decisions about analyzer fields that we have
not validated yet.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .manifest import PackManifest

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PackRow:
    id: int
    name: str
    display_name: Optional[str]
    vendor: Optional[str]
    source_url: Optional[str]
    license: Optional[str]
    description: Optional[str]
    enabled: bool
    added_at: int
    scanned_at: Optional[int]


@dataclass(frozen=True)
class AssetRow:
    id: int
    pack_id: int
    path: str
    kind: str
    file_hash: str
    file_size: int
    added_at: int
    analyzed_at: Optional[int]
    analysis_state: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS packs (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  display_name    TEXT,
  vendor          TEXT,
  source_url      TEXT,
  license         TEXT,
  description     TEXT,
  enabled         INTEGER NOT NULL DEFAULT 1,
  added_at        INTEGER NOT NULL,
  scanned_at      INTEGER,
  aggregate_meta  TEXT
);

CREATE TABLE IF NOT EXISTS assets (
  id              INTEGER PRIMARY KEY,
  pack_id         INTEGER NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
  path            TEXT NOT NULL UNIQUE,
  kind            TEXT NOT NULL,
  file_hash       TEXT NOT NULL,
  file_size       INTEGER NOT NULL,
  added_at        INTEGER NOT NULL,
  analyzed_at     INTEGER,
  analysis_state  TEXT NOT NULL,
  analysis_error  TEXT,
  manual_override INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_assets_pack ON assets(pack_id);

CREATE TABLE IF NOT EXISTS tags (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS asset_tags (
  asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
  tag_id   INTEGER REFERENCES tags(id) ON DELETE CASCADE,
  source   TEXT NOT NULL,
  PRIMARY KEY (asset_id, tag_id)
);
"""


class Store:
    """Thin wrapper around a ``sqlite3.Connection`` with the M1 schema."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path) if not isinstance(db_path, str) or db_path != ":memory:" else db_path
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None → autocommit; we use explicit transactions only where needed.
        self.conn: sqlite3.Connection = sqlite3.connect(
            str(self.db_path), isolation_level=None, check_same_thread=False
        )
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        # WAL is incompatible with :memory:, but every production path uses an on-disk DB.
        try:
            self.conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:  # pragma: no cover - memory DB fallback
            pass

    # -- lifecycle -----------------------------------------------------

    def initialize(self) -> None:
        """Create the M1 tables.  Safe to call repeatedly."""
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:  # pragma: no cover - defensive
            pass

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- pack CRUD -----------------------------------------------------

    def upsert_pack(self, name: str, manifest: PackManifest, *, scanned_at: int) -> int:
        """Insert or update a pack identified by ``name``.

        Returns the row's primary key.  ``added_at`` is only set on the
        very first insert; subsequent calls leave it untouched and
        merely refresh manifest fields plus ``scanned_at``.
        """
        cur = self.conn.execute("SELECT id FROM packs WHERE name = ?", (name,))
        row = cur.fetchone()
        if row is None:
            self.conn.execute(
                """
                INSERT INTO packs (
                  name, display_name, vendor, source_url, license, description,
                  enabled, added_at, scanned_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    name,
                    manifest.display_name,
                    manifest.vendor,
                    manifest.source_url,
                    manifest.license,
                    manifest.description,
                    scanned_at,
                    scanned_at,
                ),
            )
            return int(self.conn.execute("SELECT id FROM packs WHERE name = ?", (name,)).fetchone()[0])

        pack_id = int(row[0])
        self.conn.execute(
            """
            UPDATE packs SET
              display_name = ?,
              vendor = ?,
              source_url = ?,
              license = ?,
              description = ?,
              scanned_at = ?
            WHERE id = ?
            """,
            (
                manifest.display_name,
                manifest.vendor,
                manifest.source_url,
                manifest.license,
                manifest.description,
                scanned_at,
                pack_id,
            ),
        )
        return pack_id

    def delete_pack(self, pack_id: int) -> None:
        self.conn.execute("DELETE FROM packs WHERE id = ?", (pack_id,))

    def set_pack_enabled(self, pack_id: int, enabled: bool) -> None:
        self.conn.execute(
            "UPDATE packs SET enabled = ? WHERE id = ?", (1 if enabled else 0, pack_id)
        )

    def get_pack_by_name(self, name: str) -> Optional[PackRow]:
        row = self.conn.execute(
            "SELECT id, name, display_name, vendor, source_url, license, description,"
            "       enabled, added_at, scanned_at"
            " FROM packs WHERE name = ?",
            (name,),
        ).fetchone()
        return _pack_row(row) if row else None

    def list_packs(self, *, include_disabled: bool = True) -> list[PackRow]:
        sql = (
            "SELECT id, name, display_name, vendor, source_url, license, description,"
            "       enabled, added_at, scanned_at FROM packs"
        )
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY name"
        return [_pack_row(r) for r in self.conn.execute(sql).fetchall()]

    # -- asset CRUD ----------------------------------------------------

    def upsert_asset(
        self,
        pack_id: int,
        rel_path: str,
        kind: str,
        file_hash: str,
        file_size: int,
        *,
        added_at: int,
    ) -> int:
        """Insert/refresh an asset row.

        If the path is new, the row enters with ``analysis_state='pending'``.
        If the path exists and the hash changed, the analysis state is
        rolled back to ``pending`` so M2 can re-analyse.  An unchanged
        hash leaves any existing analysis result untouched.
        """
        cur = self.conn.execute(
            "SELECT id, file_hash FROM assets WHERE path = ?", (rel_path,)
        )
        existing = cur.fetchone()
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO assets (
                  pack_id, path, kind, file_hash, file_size,
                  added_at, analyzed_at, analysis_state
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'pending')
                """,
                (pack_id, rel_path, kind, file_hash, file_size, added_at),
            )
            return int(self.conn.execute("SELECT id FROM assets WHERE path = ?", (rel_path,)).fetchone()[0])

        asset_id = int(existing[0])
        if existing[1] == file_hash:
            # nothing meaningful changed; just keep pack_id/kind/size in sync
            self.conn.execute(
                "UPDATE assets SET pack_id = ?, kind = ?, file_size = ? WHERE id = ?",
                (pack_id, kind, file_size, asset_id),
            )
            return asset_id

        # hash changed → byte-level change; force re-analysis on next pass
        self.conn.execute(
            """
            UPDATE assets SET
              pack_id = ?,
              kind = ?,
              file_hash = ?,
              file_size = ?,
              analyzed_at = NULL,
              analysis_state = 'pending',
              analysis_error = NULL
            WHERE id = ?
            """,
            (pack_id, kind, file_hash, file_size, asset_id),
        )
        return asset_id

    def delete_asset(self, asset_id: int) -> None:
        self.conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))

    def delete_assets_outside(self, pack_id: int, kept_rel_paths: Iterable[str]) -> None:
        kept = list(kept_rel_paths)
        if not kept:
            self.conn.execute("DELETE FROM assets WHERE pack_id = ?", (pack_id,))
            return
        placeholders = ",".join("?" * len(kept))
        self.conn.execute(
            f"DELETE FROM assets WHERE pack_id = ? AND path NOT IN ({placeholders})",
            (pack_id, *kept),
        )

    def assets_for_pack(self, pack_id: int) -> list[AssetRow]:
        rows = self.conn.execute(
            "SELECT id, pack_id, path, kind, file_hash, file_size, added_at,"
            "       analyzed_at, analysis_state"
            " FROM assets WHERE pack_id = ? ORDER BY path",
            (pack_id,),
        ).fetchall()
        return [_asset_row(r) for r in rows]

    def list_assets(self, *, limit: int = 500, offset: int = 0) -> list[AssetRow]:
        rows = self.conn.execute(
            "SELECT id, pack_id, path, kind, file_hash, file_size, added_at,"
            "       analyzed_at, analysis_state"
            " FROM assets ORDER BY path LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_asset_row(r) for r in rows]

    def count_assets_in_pack(self, pack_id: int) -> int:
        return int(
            self.conn.execute("SELECT COUNT(*) FROM assets WHERE pack_id = ?", (pack_id,)).fetchone()[0]
        )


def _pack_row(r: tuple) -> PackRow:
    return PackRow(
        id=int(r[0]),
        name=r[1],
        display_name=r[2],
        vendor=r[3],
        source_url=r[4],
        license=r[5],
        description=r[6],
        enabled=bool(r[7]),
        added_at=int(r[8]),
        scanned_at=int(r[9]) if r[9] is not None else None,
    )


def _asset_row(r: tuple) -> AssetRow:
    return AssetRow(
        id=int(r[0]),
        pack_id=int(r[1]),
        path=r[2],
        kind=r[3],
        file_hash=r[4],
        file_size=int(r[5]),
        added_at=int(r[6]),
        analyzed_at=int(r[7]) if r[7] is not None else None,
        analysis_state=r[8],
    )
