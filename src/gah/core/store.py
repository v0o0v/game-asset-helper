"""SQLite store for Game Asset Helper.

M1 owns ``packs`` / ``assets`` / ``tags`` / ``asset_tags``.  M2 extends
the schema with ``sprite_meta`` / ``sound_meta`` / ``assets_fts``
(FTS5) / ``asset_embeddings`` / ``asset_labels`` / ``clip_label_cache``
and ``labels``.  ``initialize()`` runs both scripts so the same DB
file boots cleanly on first run *and* on upgrade.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .manifest import PackManifest

log = logging.getLogger(__name__)


# ── dataclasses ──────────────────────────────────────────────────────


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
    analysis_error: Optional[str] = None


@dataclass(frozen=True)
class SpriteMeta:
    width: int
    height: int
    has_alpha: bool
    is_pixel_art: bool
    dominant_colors: list[str]
    frame_w: int | None = None
    frame_h: int | None = None
    frame_count: int | None = None
    animation_tags: list[str] | None = None  # M5 가 채움


@dataclass(frozen=True)
class SoundMeta:
    duration_ms: int
    sample_rate: int
    channels: int
    loudness_db: float | None
    bpm: float | None
    category: str | None
    loopable: bool | None
    instruments: list[str] | None
    tempo: str | None
    intensity: str | None
    genre: str | None
    voice_type: str | None
    audio_path_used: str  # 'native' | 'spectrogram' | 'heuristic'


@dataclass(frozen=True)
class LabelScore:
    axis: str
    label: str
    score: float
    source: str           # 'gemma' | 'clip' | 'user'
    weight: str | None    # 'primary'/'secondary'/'tertiary' (Gemma 만)


@dataclass(frozen=True)
class LabelRow:
    id: int
    axis: str
    label: str
    description: str | None
    source: str           # 'seed' | 'user'
    enabled: bool


# ── schemas ──────────────────────────────────────────────────────────


_M1_SCHEMA = """
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


_M2_SCHEMA = """
CREATE TABLE IF NOT EXISTS sprite_meta (
  asset_id        INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
  width           INTEGER NOT NULL,
  height          INTEGER NOT NULL,
  has_alpha       INTEGER NOT NULL,
  is_pixel_art    INTEGER NOT NULL,
  dominant_colors TEXT,
  frame_w         INTEGER,
  frame_h         INTEGER,
  frame_count     INTEGER,
  animation_tags  TEXT
);

CREATE TABLE IF NOT EXISTS sound_meta (
  asset_id        INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
  duration_ms     INTEGER NOT NULL,
  sample_rate     INTEGER NOT NULL,
  channels        INTEGER NOT NULL,
  loudness_db     REAL,
  bpm             REAL,
  category        TEXT,
  loopable        INTEGER,
  instruments     TEXT,
  tempo           TEXT,
  intensity       TEXT,
  genre           TEXT,
  voice_type      TEXT,
  audio_path_used TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(
  asset_id UNINDEXED,
  searchable_text,
  tokenize = 'porter unicode61'
);

CREATE TABLE IF NOT EXISTS asset_embeddings (
  asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
  model    TEXT NOT NULL,
  dim      INTEGER NOT NULL,
  vector   BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_labels (
  asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  axis     TEXT NOT NULL,
  label    TEXT NOT NULL,
  score    REAL NOT NULL,
  source   TEXT NOT NULL,
  weight   TEXT,
  PRIMARY KEY (asset_id, axis, label, source)
);
CREATE INDEX IF NOT EXISTS idx_labels_label ON asset_labels(label);
CREATE INDEX IF NOT EXISTS idx_labels_asset ON asset_labels(asset_id);

CREATE TABLE IF NOT EXISTS clip_label_cache (
  label    TEXT NOT NULL,
  model    TEXT NOT NULL,
  dim      INTEGER NOT NULL,
  vector   BLOB NOT NULL,
  PRIMARY KEY (label, model)
);

CREATE TABLE IF NOT EXISTS labels (
  id          INTEGER PRIMARY KEY,
  axis        TEXT NOT NULL,
  label       TEXT NOT NULL,
  description TEXT,
  source      TEXT NOT NULL,
  enabled     INTEGER NOT NULL DEFAULT 1,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL,
  UNIQUE (axis, label)
);
CREATE INDEX IF NOT EXISTS idx_labels_axis_enabled ON labels(axis, enabled);
"""


# ── Store ────────────────────────────────────────────────────────────


class Store:
    """Thin wrapper around a ``sqlite3.Connection``."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = (
            Path(db_path)
            if not isinstance(db_path, str) or db_path != ":memory:"
            else db_path
        )
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # autocommit; we use explicit transactions only where needed.
        self.conn: sqlite3.Connection = sqlite3.connect(
            str(self.db_path), isolation_level=None, check_same_thread=False
        )
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        try:
            self.conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:  # pragma: no cover - memory DB fallback
            pass
        # M2.1: 다른 프로세스(sqlite3 CLI 등) 가 잠시 lock 을 잡고 있어도
        # 5초까지는 기다린다. 우리 자체 워커 사이 직렬화는 write_lock 으로 처리.
        self.conn.execute("PRAGMA busy_timeout = 5000")
        # M2.1: 워커 N 개가 같은 connection 을 공유하므로 caller 가 serialise 한다.
        # RLock 인 이유 — 외부 호출자가 with store.write_lock: 안에서 다시 writer
        # 메서드를 부르는 패턴(LabelRegistry.bootstrap 등)을 nested acquire 로 허용.
        self.write_lock: threading.RLock = threading.RLock()

    # -- lifecycle ----------------------------------------------------

    def initialize(self) -> None:
        """Create M1 + M2 tables.  Safe to call repeatedly."""
        self.conn.executescript(_M1_SCHEMA)
        self.conn.executescript(_M2_SCHEMA)

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:  # pragma: no cover - defensive
            pass

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- pack CRUD ----------------------------------------------------

    def upsert_pack(
        self, name: str, manifest: PackManifest, *, scanned_at: int
    ) -> int:
        with self.write_lock:
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
                return int(
                    self.conn.execute(
                        "SELECT id FROM packs WHERE name = ?", (name,)
                    ).fetchone()[0]
                )

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
        with self.write_lock:
            self.conn.execute("DELETE FROM packs WHERE id = ?", (pack_id,))

    def set_pack_enabled(self, pack_id: int, enabled: bool) -> None:
        with self.write_lock:
            self.conn.execute(
                "UPDATE packs SET enabled = ? WHERE id = ?",
                (1 if enabled else 0, pack_id),
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

    def update_pack_aggregate(self, pack_id: int, aggregate_json: str) -> None:
        with self.write_lock:
            self.conn.execute(
                "UPDATE packs SET aggregate_meta = ? WHERE id = ?",
                (aggregate_json, pack_id),
            )

    # -- asset CRUD ---------------------------------------------------

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
        with self.write_lock:
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
                return int(
                    self.conn.execute(
                        "SELECT id FROM assets WHERE path = ?", (rel_path,)
                    ).fetchone()[0]
                )

            asset_id = int(existing[0])
            if existing[1] == file_hash:
                self.conn.execute(
                    "UPDATE assets SET pack_id = ?, kind = ?, file_size = ? WHERE id = ?",
                    (pack_id, kind, file_size, asset_id),
                )
                return asset_id

            # hash changed → re-analyse on next pass
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
        with self.write_lock:
            # FTS5 is not bound by FK — clean it explicitly.
            self.conn.execute("DELETE FROM assets_fts WHERE asset_id = ?", (asset_id,))
            self.conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))

    def delete_assets_outside(
        self, pack_id: int, kept_rel_paths: Iterable[str]
    ) -> None:
        kept = list(kept_rel_paths)
        with self.write_lock:
            if not kept:
                self.conn.execute(
                    "DELETE FROM assets WHERE pack_id = ?", (pack_id,)
                )
                return
            placeholders = ",".join("?" * len(kept))
            self.conn.execute(
                f"DELETE FROM assets WHERE pack_id = ? AND path NOT IN ({placeholders})",
                (pack_id, *kept),
            )

    def assets_for_pack(self, pack_id: int) -> list[AssetRow]:
        rows = self.conn.execute(
            "SELECT id, pack_id, path, kind, file_hash, file_size, added_at,"
            "       analyzed_at, analysis_state, analysis_error"
            " FROM assets WHERE pack_id = ? ORDER BY path",
            (pack_id,),
        ).fetchall()
        return [_asset_row(r) for r in rows]

    def list_assets(self, *, limit: int = 500, offset: int = 0) -> list[AssetRow]:
        rows = self.conn.execute(
            "SELECT id, pack_id, path, kind, file_hash, file_size, added_at,"
            "       analyzed_at, analysis_state, analysis_error"
            " FROM assets ORDER BY path LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_asset_row(r) for r in rows]

    def count_assets_in_pack(self, pack_id: int) -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM assets WHERE pack_id = ?", (pack_id,)
            ).fetchone()[0]
        )

    def get_asset_by_id(self, asset_id: int) -> Optional[AssetRow]:
        row = self.conn.execute(
            "SELECT id, pack_id, path, kind, file_hash, file_size, added_at,"
            "       analyzed_at, analysis_state, analysis_error"
            " FROM assets WHERE id = ?",
            (asset_id,),
        ).fetchone()
        return _asset_row(row) if row else None

    # -- M2: analysis state transitions -------------------------------

    def mark_asset_analyzing(self, asset_id: int) -> None:
        with self.write_lock:
            self.conn.execute(
                "UPDATE assets SET analysis_state = 'analyzing' WHERE id = ?",
                (asset_id,),
            )

    def mark_asset_state(
        self,
        asset_id: int,
        state: str,
        *,
        error: str | None = None,
        analyzed_at: int | None = None,
    ) -> None:
        with self.write_lock:
            self.conn.execute(
                "UPDATE assets SET analysis_state = ?, analysis_error = ?, analyzed_at = ?"
                " WHERE id = ?",
                (state, error, analyzed_at, asset_id),
            )

    def mark_asset_pending(self, asset_id: int) -> None:
        """Restore an asset's state to 'pending'.

        Used by :meth:`AnalysisQueue.drain_pending` to re-queue rows that
        were temporarily flipped to 'analyzing' during the sweep.  Carved
        out as a real Store method so all writes flow through ``write_lock``.
        """
        with self.write_lock:
            self.conn.execute(
                "UPDATE assets SET analysis_state = 'pending' WHERE id = ?",
                (asset_id,),
            )

    def next_pending_asset(self) -> Optional[AssetRow]:
        row = self.conn.execute(
            "SELECT id, pack_id, path, kind, file_hash, file_size, added_at,"
            "       analyzed_at, analysis_state, analysis_error"
            " FROM assets WHERE analysis_state = 'pending'"
            " ORDER BY added_at ASC, id ASC LIMIT 1"
        ).fetchone()
        return _asset_row(row) if row else None

    def pending_assets_for_pack(self, pack_id: int) -> list[AssetRow]:
        rows = self.conn.execute(
            "SELECT id, pack_id, path, kind, file_hash, file_size, added_at,"
            "       analyzed_at, analysis_state, analysis_error"
            " FROM assets WHERE pack_id = ? AND analysis_state = 'pending'"
            " ORDER BY added_at, id",
            (pack_id,),
        ).fetchall()
        return [_asset_row(r) for r in rows]

    def count_pending_assets(self) -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM assets WHERE analysis_state = 'pending'"
            ).fetchone()[0]
        )

    # -- M2: meta writers ---------------------------------------------

    def save_sprite_meta(self, asset_id: int, meta: SpriteMeta) -> None:
        import json

        with self.write_lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO sprite_meta (
                  asset_id, width, height, has_alpha, is_pixel_art,
                  dominant_colors, frame_w, frame_h, frame_count, animation_tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    meta.width,
                    meta.height,
                    1 if meta.has_alpha else 0,
                    1 if meta.is_pixel_art else 0,
                    json.dumps(meta.dominant_colors),
                    meta.frame_w,
                    meta.frame_h,
                    meta.frame_count,
                    json.dumps(meta.animation_tags) if meta.animation_tags else None,
                ),
            )

    def save_sound_meta(self, asset_id: int, meta: SoundMeta) -> None:
        import json

        with self.write_lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO sound_meta (
                  asset_id, duration_ms, sample_rate, channels, loudness_db,
                  bpm, category, loopable, instruments,
                  tempo, intensity, genre, voice_type, audio_path_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    meta.duration_ms,
                    meta.sample_rate,
                    meta.channels,
                    meta.loudness_db,
                    meta.bpm,
                    meta.category,
                    None if meta.loopable is None else (1 if meta.loopable else 0),
                    json.dumps(meta.instruments) if meta.instruments else None,
                    meta.tempo,
                    meta.intensity,
                    meta.genre,
                    meta.voice_type,
                    meta.audio_path_used,
                ),
            )

    def save_asset_labels(
        self, asset_id: int, labels: list[LabelScore]
    ) -> None:
        # 트랜잭션 안에서 기존 라벨 제거 후 일괄 INSERT.
        with self.write_lock:
            self.conn.execute("BEGIN")
            try:
                self.conn.execute(
                    "DELETE FROM asset_labels WHERE asset_id = ?", (asset_id,)
                )
                self.conn.executemany(
                    "INSERT INTO asset_labels (asset_id, axis, label, score, source, weight)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (asset_id, lbl.axis, lbl.label, lbl.score, lbl.source, lbl.weight)
                        for lbl in labels
                    ],
                )
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def labels_for_asset(self, asset_id: int) -> list[LabelScore]:
        rows = self.conn.execute(
            "SELECT axis, label, score, source, weight FROM asset_labels"
            " WHERE asset_id = ? ORDER BY score DESC",
            (asset_id,),
        ).fetchall()
        return [
            LabelScore(axis=r[0], label=r[1], score=r[2], source=r[3], weight=r[4])
            for r in rows
        ]

    def save_embedding(
        self, asset_id: int, model: str, vector_bytes: bytes, dim: int
    ) -> None:
        with self.write_lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO asset_embeddings (asset_id, model, dim, vector)"
                " VALUES (?, ?, ?, ?)",
                (asset_id, model, dim, vector_bytes),
            )

    def update_fts(self, asset_id: int, searchable_text: str) -> None:
        with self.write_lock:
            self.conn.execute(
                "DELETE FROM assets_fts WHERE asset_id = ?", (asset_id,)
            )
            self.conn.execute(
                "INSERT INTO assets_fts (asset_id, searchable_text) VALUES (?, ?)",
                (asset_id, searchable_text),
            )

    # -- M2: CLIP label vector cache ----------------------------------

    def clip_label_cache_get(self, label: str, model: str) -> bytes | None:
        row = self.conn.execute(
            "SELECT vector FROM clip_label_cache WHERE label = ? AND model = ?",
            (label, model),
        ).fetchone()
        return row[0] if row else None

    def clip_label_cache_put(
        self, label: str, model: str, dim: int, vector: bytes
    ) -> None:
        with self.write_lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO clip_label_cache (label, model, dim, vector)"
                " VALUES (?, ?, ?, ?)",
                (label, model, dim, vector),
            )

    # -- M2: labels (vocabulary) --------------------------------------

    def list_labels_raw(
        self, axis: str | None = None, *, enabled_only: bool = True
    ) -> list[LabelRow]:
        sql = (
            "SELECT id, axis, label, description, source, enabled FROM labels"
        )
        params: list = []
        where: list[str] = []
        if axis is not None:
            where.append("axis = ?")
            params.append(axis)
        if enabled_only:
            where.append("enabled = 1")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY axis, label"
        return [
            LabelRow(
                id=int(r[0]),
                axis=r[1],
                label=r[2],
                description=r[3],
                source=r[4],
                enabled=bool(r[5]),
            )
            for r in self.conn.execute(sql, params).fetchall()
        ]


# ── helpers ──────────────────────────────────────────────────────────


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
        analysis_error=r[9] if len(r) > 9 else None,
    )
