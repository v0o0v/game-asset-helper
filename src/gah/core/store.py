"""SQLite store for Game Asset Helper.

M1 owns ``packs`` / ``assets`` / ``tags`` / ``asset_tags``.  M2 extends
the schema with ``sprite_meta`` / ``sound_meta`` / ``assets_fts``
(FTS5) / ``asset_embeddings`` / ``asset_labels`` / ``clip_label_cache``
and ``labels``.  ``initialize()`` runs both scripts so the same DB
file boots cleanly on first run *and* on upgrade.
"""

from __future__ import annotations

import json
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
    animation_tags: list[str] | None = None  # M5 가 채움 → M6 분석기가 채움
    animations_json: dict | None = None  # M6 — {name: {start_frame, end_frame, fps_hint, source}}


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


@dataclass(frozen=True)
class ProjectRow:
    """M3: 프로젝트 (Claude Code 가 보내는 external_id 로 식별)."""

    id: int
    external_id: str
    display_name: str | None
    first_seen: int
    last_seen: int
    pinned_pack_id: int | None
    blocked_packs: list[int]   # JSON 디코드 결과


@dataclass(frozen=True)
class ProjectUsageSummary:
    """M3: 프로젝트의 사용 이력 요약 — ConsistencyScorer 의 핵심 입력.

    ``usage_tracker.py`` 에서도 그대로 import 해 쓴다 — 모듈 경계는 데이터
    의존 방향(usage → store) 을 거꾸로 만들지 않도록 store 가 source of truth.
    """

    pack_uses: dict[int, int]            # {pack_id: count}
    vendor_uses: dict[str, int]
    total_uses: int
    distinct_packs: int
    dominant_style: str | None
    dominant_palette: list[str]


@dataclass(frozen=True)
class SavedSearchRow:
    """M4: 저장된 검색.  ``query_json`` 은 SearchRequest 직렬화 (project_id 제외)."""

    id: int
    project_id: int | None
    name: str
    query_json: str
    created_at: int
    last_used_at: int | None


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


_M3_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id              INTEGER PRIMARY KEY,
  external_id     TEXT NOT NULL UNIQUE,
  display_name    TEXT,
  first_seen      INTEGER NOT NULL,
  last_seen       INTEGER NOT NULL,
  pinned_pack_id  INTEGER REFERENCES packs(id) ON DELETE SET NULL,
  blocked_packs   TEXT
);

CREATE TABLE IF NOT EXISTS asset_usage (
  id          INTEGER PRIMARY KEY,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id    INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  pack_id     INTEGER NOT NULL,
  used_at     INTEGER NOT NULL,
  source      TEXT NOT NULL,
  context     TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_project ON asset_usage(project_id, used_at);
CREATE INDEX IF NOT EXISTS idx_usage_pack    ON asset_usage(project_id, pack_id);

CREATE TABLE IF NOT EXISTS search_queries (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  query_text   TEXT NOT NULL,
  results_json TEXT NOT NULL,
  created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_queries_project ON search_queries(project_id, created_at);
"""


_M4_SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_searches (
  id              INTEGER PRIMARY KEY,
  project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  query_json      TEXT NOT NULL,
  created_at      INTEGER NOT NULL,
  last_used_at    INTEGER,
  UNIQUE(project_id, name)
);
CREATE INDEX IF NOT EXISTS idx_saved_searches_project
  ON saved_searches(project_id, last_used_at);

CREATE TABLE IF NOT EXISTS feedback_records (
  id              INTEGER PRIMARY KEY,
  project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id        INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  query_id        INTEGER REFERENCES search_queries(id) ON DELETE SET NULL,
  reason          TEXT NOT NULL,
  weight          REAL NOT NULL,
  created_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_project_asset
  ON feedback_records(project_id, asset_id, created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_project_pack_asset
  ON feedback_records(project_id, asset_id);
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
        """Create M1 + M2 + M3 + M4 tables.  Safe to call repeatedly."""
        self.conn.executescript(_M1_SCHEMA)
        self.conn.executescript(_M2_SCHEMA)
        self.conn.executescript(_M3_SCHEMA)
        self.conn.executescript(_M4_SCHEMA)
        self._migrate_m6_animations_json()

    def _migrate_m6_animations_json(self) -> None:
        """M6 — sprite_meta.animations_json 컬럼 idempotent 추가."""
        with self.write_lock:
            cur = self.conn.execute("PRAGMA table_info(sprite_meta)")
            cols = {r[1] for r in cur.fetchall()}
            if "animations_json" not in cols:
                self.conn.execute(
                    "ALTER TABLE sprite_meta ADD COLUMN animations_json TEXT"
                )

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

    def get_pack_by_id(self, pack_id: int) -> Optional[PackRow]:
        """pack_id 로 팩 조회. 없으면 None."""
        row = self.conn.execute(
            "SELECT id, name, display_name, vendor, source_url, license, description,"
            "       enabled, added_at, scanned_at"
            " FROM packs WHERE id = ?",
            (pack_id,),
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

    def list_packs_with_stats(
        self, *, include_disabled: bool = True
    ) -> list[dict]:
        """팩 목록 + 에셋 통계 (asset_count, kind_counts) 를 한 번에 반환.

        두 쿼리 방식: 팩 메타 + asset_count 를 첫 쿼리로, kind 분포를 두 번째
        쿼리로 얻어 Python 에서 병합한다.

        반환 형태::

            [
              {
                "id": 1, "name": "kenney_demo", "display_name": ...,
                "vendor": ..., "license": ..., "enabled": True,
                "asset_count": 15,
                "kind_counts": {"sprite": 12, "sound": 3},
              },
              ...
            ]
        """
        # 1) 팩 메타 + asset_count
        where = "" if include_disabled else " WHERE p.enabled = 1"
        rows = self.conn.execute(
            "SELECT p.id, p.name, p.display_name, p.vendor, p.source_url,"
            "       p.license, p.description, p.enabled, p.added_at, p.scanned_at,"
            "       COUNT(a.id) AS asset_count"
            " FROM packs p"
            " LEFT JOIN assets a ON a.pack_id = p.id"
            f"{where}"
            " GROUP BY p.id"
            " ORDER BY p.name"
        ).fetchall()

        packs: list[dict] = []
        pack_ids: list[int] = []
        for r in rows:
            pack_ids.append(int(r[0]))
            packs.append(
                {
                    "id": int(r[0]),
                    "name": r[1],
                    "display_name": r[2],
                    "vendor": r[3],
                    "source_url": r[4],
                    "license": r[5],
                    "description": r[6],
                    "enabled": bool(r[7]),
                    "added_at": int(r[8]),
                    "scanned_at": int(r[9]) if r[9] is not None else None,
                    "asset_count": int(r[10]),
                    "kind_counts": {},
                }
            )

        if not pack_ids:
            return packs

        # 2) kind 분포
        placeholders = ",".join("?" * len(pack_ids))
        kind_rows = self.conn.execute(
            f"SELECT pack_id, kind, COUNT(*) FROM assets"
            f" WHERE pack_id IN ({placeholders})"
            f" GROUP BY pack_id, kind",
            pack_ids,
        ).fetchall()

        # pack_id → dict 인덱스
        id_to_idx = {p["id"]: i for i, p in enumerate(packs)}
        for pack_id, kind, cnt in kind_rows:
            idx = id_to_idx.get(int(pack_id))
            if idx is not None:
                packs[idx]["kind_counts"][kind] = int(cnt)

        return packs

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
                  dominant_colors, frame_w, frame_h, frame_count, animation_tags,
                  animations_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(meta.animations_json) if meta.animations_json is not None else None,
                ),
            )

    def get_sprite_meta(self, asset_id: int) -> "SpriteMeta | None":
        """asset_id 의 sprite_meta 행을 SpriteMeta 로 반환. 없으면 None."""
        import json

        row = self.conn.execute(
            """
            SELECT width, height, has_alpha, is_pixel_art, dominant_colors,
                   frame_w, frame_h, frame_count, animation_tags, animations_json
              FROM sprite_meta WHERE asset_id = ?
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            return None

        # JSON 디코드 — 손상 데이터에 견고하게
        try:
            dominant_colors = json.loads(row[4]) if row[4] else []
        except (json.JSONDecodeError, TypeError):
            dominant_colors = []
        try:
            animation_tags = json.loads(row[8]) if row[8] else None
        except (json.JSONDecodeError, TypeError):
            animation_tags = None
        try:
            animations_json = json.loads(row[9]) if row[9] else None
        except (json.JSONDecodeError, TypeError):
            animations_json = None

        return SpriteMeta(
            width=int(row[0]), height=int(row[1]),
            has_alpha=bool(row[2]), is_pixel_art=bool(row[3]),
            dominant_colors=dominant_colors,
            frame_w=int(row[5]) if row[5] is not None else None,
            frame_h=int(row[6]) if row[6] is not None else None,
            frame_count=int(row[7]) if row[7] is not None else None,
            animation_tags=animation_tags,
            animations_json=animations_json,
        )

    def update_asset_kind(self, asset_id: int, kind: str) -> None:
        """분석기가 sprite → spritesheet 로 promote 할 때 호출."""
        if kind not in ("sprite", "spritesheet", "sound"):
            raise ValueError(f"invalid kind: {kind}")
        with self.write_lock:
            self.conn.execute(
                "UPDATE assets SET kind = ? WHERE id = ?", (kind, asset_id)
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

    def get_label_by_id(self, label_id: int) -> Optional[LabelRow]:
        """label_id 로 라벨 조회. 없으면 None."""
        row = self.conn.execute(
            "SELECT id, axis, label, description, source, enabled FROM labels WHERE id = ?",
            (label_id,),
        ).fetchone()
        if row is None:
            return None
        return LabelRow(
            id=int(row[0]),
            axis=row[1],
            label=row[2],
            description=row[3],
            source=row[4],
            enabled=bool(row[5]),
        )

    def update_label(
        self,
        label_id: int,
        *,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        """라벨 description/enabled 을 개별 또는 함께 갱신한다."""
        import time as _time

        now = int(_time.time())
        parts: list[str] = ["updated_at = ?"]
        params: list = [now]
        if description is not None:
            parts.append("description = ?")
            params.append(description)
        if enabled is not None:
            parts.append("enabled = ?")
            params.append(1 if enabled else 0)
        params.append(label_id)
        with self.write_lock:
            self.conn.execute(
                f"UPDATE labels SET {', '.join(parts)} WHERE id = ?",
                params,
            )

    def delete_label(self, label_id: int) -> None:
        """라벨 행 삭제. 호출 전 count_asset_labels_for_label_id 로 사용 중 여부 확인."""
        with self.write_lock:
            self.conn.execute("DELETE FROM labels WHERE id = ?", (label_id,))

    def count_asset_labels_for_label_id(self, label_id: int) -> int:
        """asset_labels 에서 해당 label_id 가 대응하는 (axis, label) 을 참조하는 행 수.

        asset_labels 는 label_id FK 가 없고 (axis, label) 문자열로 join 해야 한다.
        """
        row = self.conn.execute(
            "SELECT COUNT(*) FROM asset_labels al"
            " JOIN labels l ON al.axis = l.axis AND al.label = l.label"
            " WHERE l.id = ?",
            (label_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    # -- M3: projects -----------------------------------------------------

    def upsert_project(
        self, external_id: str, *, display_name: str | None = None
    ) -> ProjectRow:
        import time as _time

        now = int(_time.time())
        with self.write_lock:
            cur = self.conn.execute(
                "SELECT id FROM projects WHERE external_id = ?", (external_id,)
            )
            row = cur.fetchone()
            if row is None:
                self.conn.execute(
                    "INSERT INTO projects (external_id, display_name, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?)",
                    (external_id, display_name, now, now),
                )
            else:
                # display_name=None 일 때는 기존 값 보존, 아니면 갱신.
                if display_name is None:
                    self.conn.execute(
                        "UPDATE projects SET last_seen = ? WHERE id = ?",
                        (now, int(row[0])),
                    )
                else:
                    self.conn.execute(
                        "UPDATE projects SET display_name = ?, last_seen = ? WHERE id = ?",
                        (display_name, now, int(row[0])),
                    )
        got = self.get_project(external_id)
        assert got is not None
        return got

    def get_project(self, external_id: str) -> ProjectRow | None:
        row = self.conn.execute(
            "SELECT id, external_id, display_name, first_seen, last_seen, "
            "pinned_pack_id, blocked_packs FROM projects WHERE external_id = ?",
            (external_id,),
        ).fetchone()
        if row is None:
            return None
        return _project_row(row)

    def get_project_by_id(self, project_id: int) -> ProjectRow | None:
        row = self.conn.execute(
            "SELECT id, external_id, display_name, first_seen, last_seen, "
            "pinned_pack_id, blocked_packs FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        return _project_row(row)

    def set_project_pin(self, project_id: int, pinned_pack_id: int | None) -> None:
        with self.write_lock:
            self.conn.execute(
                "UPDATE projects SET pinned_pack_id = ? WHERE id = ?",
                (pinned_pack_id, project_id),
            )

    def set_blocked_packs(self, project_id: int, pack_ids: list[int]) -> None:
        import json as _json

        payload = _json.dumps(list(pack_ids)) if pack_ids else None
        with self.write_lock:
            self.conn.execute(
                "UPDATE projects SET blocked_packs = ? WHERE id = ?",
                (payload, project_id),
            )

    # -- M3: asset_usage --------------------------------------------------

    def record_asset_use(
        self,
        project_id: int,
        asset_id: int,
        pack_id: int,
        *,
        source: str = "explicit",
        context: str | None = None,
    ) -> int:
        import time as _time

        with self.write_lock:
            self.conn.execute(
                "INSERT INTO asset_usage (project_id, asset_id, pack_id, used_at, "
                "source, context) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, asset_id, pack_id, int(_time.time()), source, context),
            )
            return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def project_usage_summary(self, project_id: int) -> ProjectUsageSummary:
        rows = self.conn.execute(
            "SELECT au.pack_id, p.vendor "
            "FROM asset_usage au LEFT JOIN packs p ON p.id = au.pack_id "
            "WHERE au.project_id = ?",
            (project_id,),
        ).fetchall()
        pack_uses: dict[int, int] = {}
        vendor_uses: dict[str, int] = {}
        for pack_id, vendor in rows:
            pack_uses[int(pack_id)] = pack_uses.get(int(pack_id), 0) + 1
            if vendor:
                vendor_uses[vendor] = vendor_uses.get(vendor, 0) + 1
        dominant_style = None
        dominant_palette: list[str] = []
        if pack_uses:
            dom_pack_id = max(pack_uses, key=lambda k: pack_uses[k])
            agg = self.pack_aggregate(dom_pack_id) or {}
            dominant_style = agg.get("main_style")
            pal = agg.get("palette") or []
            if isinstance(pal, list):
                dominant_palette = [str(x) for x in pal]
        return ProjectUsageSummary(
            pack_uses=pack_uses,
            vendor_uses=vendor_uses,
            total_uses=sum(pack_uses.values()),
            distinct_packs=len(pack_uses),
            dominant_style=dominant_style,
            dominant_palette=dominant_palette,
        )

    # -- M3: search_queries ----------------------------------------------

    def insert_search_query(
        self, project_id: int | None, query_text: str, results: list[tuple[int, float]]
    ) -> int:
        import json as _json
        import time as _time

        payload = _json.dumps([[int(aid), float(score)] for aid, score in results])
        with self.write_lock:
            self.conn.execute(
                "INSERT INTO search_queries (project_id, query_text, results_json, "
                "created_at) VALUES (?, ?, ?, ?)",
                (project_id, query_text, payload, int(_time.time())),
            )
            return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def last_query_top1_for_project(
        self, project_id: int, *, within_seconds: int = 3600
    ) -> tuple[int, int] | None:
        import json as _json
        import time as _time

        # within_seconds 가 0 이하면 "최근 0초 안" — 정의상 항상 빈 윈도우.
        if within_seconds <= 0:
            return None
        cutoff = int(_time.time()) - int(within_seconds)
        row = self.conn.execute(
            "SELECT id, results_json FROM search_queries "
            "WHERE project_id = ? AND created_at > ? "
            "ORDER BY created_at DESC LIMIT 1",
            (project_id, cutoff),
        ).fetchone()
        if row is None:
            return None
        try:
            data = _json.loads(row[1])
            if not data:
                return None
            return (int(row[0]), int(data[0][0]))
        except (json.JSONDecodeError, IndexError, ValueError, TypeError):
            return None

    # -- M3: search inputs (FTS + semantic + labels + meta) --------------

    def fts_search(
        self,
        query: str,
        *,
        kind: str | None = None,
        pack_id: int | None = None,
        exclude_pack_ids: Iterable[int] = (),
        k: int = 200,
    ) -> list[tuple[int, float]]:
        """`(asset_id, raw_bm25)` 페어. caller 가 부호 뒤집기 + 정규화.

        FTS5 의 unicode61 토크나이저는 `:` 를 단어 구분자로 다루므로
        ``label:pixel_art`` 같은 쿼리는 column-prefix 매칭으로 잘못
        해석된다. 그래서 콜론·하이픈·괄호·따옴표·별 등을 포함한 토큰은
        자동으로 phrase quote 한다. 호출자는 plain text 그대로 보내면 된다.
        """
        params: list = [_safe_fts_query(query)]
        sql_parts = [
            "SELECT f.asset_id, bm25(assets_fts) AS rank, a.pack_id, a.kind",
            "FROM assets_fts f JOIN assets a ON a.id = f.asset_id",
            "WHERE assets_fts MATCH ?",
        ]
        if kind is not None:
            sql_parts.append("AND a.kind = ?")
            params.append(kind)
        if pack_id is not None:
            sql_parts.append("AND a.pack_id = ?")
            params.append(int(pack_id))
        excl = list(exclude_pack_ids)
        if excl:
            placeholders = ",".join("?" * len(excl))
            sql_parts.append(f"AND a.pack_id NOT IN ({placeholders})")
            params.extend(int(p) for p in excl)
        sql_parts.append("ORDER BY rank LIMIT ?")
        params.append(int(k))
        sql = " ".join(sql_parts)
        try:
            return [(int(r[0]), float(r[1])) for r in self.conn.execute(sql, params).fetchall()]
        except sqlite3.OperationalError:
            # FTS5 syntax 오류 (사용자 입력에 special char 등) → 빈 결과.
            return []

    def semantic_candidates_load(
        self, *, asset_ids: list[int] | None = None
    ) -> tuple[list[int], "np.ndarray", str]:  # type: ignore[name-defined]
        """``(ids, matrix[N×dim] float32, model)`` 반환. import numpy 는 lazy."""
        import numpy as _np

        if asset_ids is not None and not asset_ids:
            empty = _np.zeros((0, 0), dtype="<f4")
            return [], empty, ""
        sql = "SELECT asset_id, model, dim, vector FROM asset_embeddings"
        params: list = []
        if asset_ids is not None:
            placeholders = ",".join("?" * len(asset_ids))
            sql += f" WHERE asset_id IN ({placeholders})"
            params.extend(int(x) for x in asset_ids)
        rows = self.conn.execute(sql, params).fetchall()
        if not rows:
            empty = _np.zeros((0, 0), dtype="<f4")
            return [], empty, ""
        # All rows must share dim — first row sets the contract.
        dim = int(rows[0][2])
        model = str(rows[0][1])
        ids: list[int] = []
        matrix = _np.zeros((len(rows), dim), dtype="<f4")
        for i, (aid, _m, d, blob) in enumerate(rows):
            ids.append(int(aid))
            vec = _np.frombuffer(blob, dtype="<f4", count=int(d))
            matrix[i] = vec
        return ids, matrix, model

    def asset_labels_for(
        self, asset_ids: list[int]
    ) -> dict[int, list[LabelScore]]:
        if not asset_ids:
            return {}
        placeholders = ",".join("?" * len(asset_ids))
        rows = self.conn.execute(
            f"SELECT asset_id, axis, label, score, source, weight "
            f"FROM asset_labels WHERE asset_id IN ({placeholders})",
            [int(x) for x in asset_ids],
        ).fetchall()
        result: dict[int, list[LabelScore]] = {int(aid): [] for aid in asset_ids}
        for aid, axis, label, score, source, weight in rows:
            result[int(aid)].append(
                LabelScore(
                    axis=axis,
                    label=label,
                    score=float(score),
                    source=source,
                    weight=weight,
                )
            )
        return result

    def pack_aggregate(self, pack_id: int) -> dict | None:
        import json as _json

        row = self.conn.execute(
            "SELECT aggregate_meta FROM packs WHERE id = ?", (int(pack_id),)
        ).fetchone()
        if row is None or row[0] is None:
            return None
        try:
            return _json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None

    def recent_assets_score(
        self, asset_ids: list[int], *, window_seconds: int = 2_592_000
    ) -> dict[int, float]:
        """analyzed_at 기준 지수 감쇠 0..1. NULL 이면 added_at → 현재시간 순 폴백."""
        import math as _math
        import time as _time

        if not asset_ids:
            return {}
        placeholders = ",".join("?" * len(asset_ids))
        rows = self.conn.execute(
            f"SELECT id, analyzed_at, added_at FROM assets WHERE id IN ({placeholders})",
            [int(x) for x in asset_ids],
        ).fetchall()
        now = int(_time.time())
        out: dict[int, float] = {}
        for aid, analyzed_at, added_at in rows:
            ts = analyzed_at if analyzed_at is not None else added_at
            if ts is None:
                out[int(aid)] = 1.0
                continue
            age = max(0, now - int(ts))
            # 지수 감쇠 — window 안이면 ≥ 1/e ≈ 0.37.
            decay = _math.exp(-age / max(1, window_seconds))
            out[int(aid)] = float(max(0.0, min(1.0, decay)))
        return out

    def asset_count_by_kind(self, pack_id: int | None = None) -> dict[str, int]:
        if pack_id is None:
            rows = self.conn.execute(
                "SELECT kind, COUNT(*) FROM assets GROUP BY kind"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT kind, COUNT(*) FROM assets WHERE pack_id = ? GROUP BY kind",
                (int(pack_id),),
            ).fetchall()
        return {str(k): int(c) for k, c in rows}

    # -- M4: saved_searches -----------------------------------------------

    def save_search(
        self, project_id: int | None, name: str, query_json: str,
    ) -> int:
        """저장된 검색 행을 INSERT.

        ``UNIQUE(project_id, name)`` 충돌 시 ``sqlite3.IntegrityError`` 가
        그대로 raise 된다 — caller (MCP tool) 가 ``400_invalid_input`` 으로
        매핑.
        """
        import time as _time

        now = int(_time.time())
        with self.write_lock:
            self.conn.execute(
                "INSERT INTO saved_searches "
                "(project_id, name, query_json, created_at) VALUES (?,?,?,?)",
                (project_id, name, query_json, now),
            )
            return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def delete_saved_search(self, project_id: int | None, name: str) -> bool:
        """저장된 검색 삭제.  삭제 행 수 ≥ 1 이면 True."""
        with self.write_lock:
            if project_id is None:
                cur = self.conn.execute(
                    "DELETE FROM saved_searches WHERE project_id IS NULL AND name = ?",
                    (name,),
                )
            else:
                cur = self.conn.execute(
                    "DELETE FROM saved_searches WHERE project_id = ? AND name = ?",
                    (project_id, name),
                )
            return (cur.rowcount or 0) > 0

    def update_saved_search_last_used(self, saved_search_id: int) -> None:
        import time as _time

        with self.write_lock:
            self.conn.execute(
                "UPDATE saved_searches SET last_used_at = ? WHERE id = ?",
                (int(_time.time()), int(saved_search_id)),
            )

    def upsert_saved_search(
        self, project_id: int | None, name: str, query_json: str,
    ) -> int:
        """저장된 검색 INSERT or UPDATE — 이름 중복 시 query_json 만 교체.

        같은 (project_id, name) 행이 있으면 그 행 ID 를 그대로 유지하고
        ``query_json`` 만 교체.  없으면 새로 INSERT.  반환은 saved_search_id.

        > NULL 처리 주의: SQLite 의 UNIQUE 는 NULL 을 distinct 로 본다.
        > ``ON CONFLICT`` 는 ``project_id=NULL`` 케이스에서 발화 안 함.
        > 명시적으로 ``IS NULL`` 분기해서 SELECT 후 INSERT/UPDATE 결정.
        """
        import time as _time

        now = int(_time.time())
        with self.write_lock:
            if project_id is None:
                row = self.conn.execute(
                    "SELECT id FROM saved_searches "
                    "WHERE project_id IS NULL AND name = ?",
                    (name,),
                ).fetchone()
            else:
                row = self.conn.execute(
                    "SELECT id FROM saved_searches "
                    "WHERE project_id = ? AND name = ?",
                    (int(project_id), name),
                ).fetchone()
            if row is None:
                self.conn.execute(
                    "INSERT INTO saved_searches "
                    "(project_id, name, query_json, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (project_id, name, query_json, now),
                )
                return int(
                    self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                )
            self.conn.execute(
                "UPDATE saved_searches SET query_json = ? WHERE id = ?",
                (query_json, int(row[0])),
            )
            return int(row[0])

    def rename_saved_search(self, saved_search_id: int, new_name: str) -> None:
        """저장된 검색 이름 UPDATE.

        같은 (project_id, new_name) 행이 이미 있으면 SQLite UNIQUE 위반 →
        ``sqlite3.IntegrityError`` 가 raise — caller (GUI) 가 메시지 표시.
        """
        with self.write_lock:
            self.conn.execute(
                "UPDATE saved_searches SET name = ? WHERE id = ?",
                (new_name, int(saved_search_id)),
            )

    def list_saved_searches(self, project_id: int | None) -> list[SavedSearchRow]:
        """``last_used_at DESC NULLS LAST, created_at DESC`` 순."""
        if project_id is None:
            rows = self.conn.execute(
                "SELECT id, project_id, name, query_json, created_at, last_used_at "
                "FROM saved_searches WHERE project_id IS NULL "
                "ORDER BY last_used_at IS NULL, last_used_at DESC, created_at DESC"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, project_id, name, query_json, created_at, last_used_at "
                "FROM saved_searches WHERE project_id = ? "
                "ORDER BY last_used_at IS NULL, last_used_at DESC, created_at DESC",
                (int(project_id),),
            ).fetchall()
        return [_saved_search_row(r) for r in rows]

    def get_saved_search(
        self, project_id: int | None, name: str,
    ) -> SavedSearchRow | None:
        if project_id is None:
            row = self.conn.execute(
                "SELECT id, project_id, name, query_json, created_at, last_used_at "
                "FROM saved_searches WHERE project_id IS NULL AND name = ?",
                (name,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT id, project_id, name, query_json, created_at, last_used_at "
                "FROM saved_searches WHERE project_id = ? AND name = ?",
                (int(project_id), name),
            ).fetchone()
        if row is None:
            return None
        return _saved_search_row(row)

    def get_saved_search_by_id(self, ss_id: int) -> "SavedSearchRow | None":
        """저장된 검색을 id 로 직접 조회. 없으면 None."""
        row = self.conn.execute(
            "SELECT id, project_id, name, query_json, created_at, last_used_at"
            " FROM saved_searches WHERE id = ?",
            (ss_id,),
        ).fetchone()
        return _saved_search_row(row) if row else None

    # -- M4: feedback_records --------------------------------------------

    def insert_feedback_record(
        self,
        project_id: int,
        asset_id: int,
        query_id: int | None,
        reason: str,
        weight: float,
    ) -> int:
        """페널티 학습용 signed weight 행 INSERT."""
        import time as _time

        with self.write_lock:
            self.conn.execute(
                "INSERT INTO feedback_records "
                "(project_id, asset_id, query_id, reason, weight, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    int(project_id), int(asset_id),
                    int(query_id) if query_id is not None else None,
                    reason, float(weight), int(_time.time()),
                ),
            )
            return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def feedback_records_for_project(
        self,
        project_id: int,
        asset_ids: list[int] | None,
        *,
        within_seconds: int,
    ) -> dict[int, float]:
        """`{asset_id: sum(weight)}` 윈도우 내 행만 합산.

        ``asset_ids=None`` 이면 모든 asset 의 합을 돌려준다.
        """
        import time as _time

        cutoff = int(_time.time()) - int(within_seconds)
        if asset_ids is None:
            rows = self.conn.execute(
                "SELECT asset_id, SUM(weight) FROM feedback_records "
                "WHERE project_id = ? AND created_at >= ? "
                "GROUP BY asset_id",
                (int(project_id), cutoff),
            ).fetchall()
        else:
            if not asset_ids:
                return {}
            placeholders = ",".join("?" * len(asset_ids))
            params: list = [int(project_id), cutoff, *[int(x) for x in asset_ids]]
            rows = self.conn.execute(
                f"SELECT asset_id, SUM(weight) FROM feedback_records "
                f"WHERE project_id = ? AND created_at >= ? "
                f"AND asset_id IN ({placeholders}) GROUP BY asset_id",
                params,
            ).fetchall()
        return {int(aid): float(s or 0.0) for aid, s in rows}

    def pack_feedback_count(
        self,
        project_id: int,
        pack_ids: list[int],
        *,
        within_seconds: int,
    ) -> dict[int, int]:
        """`{pack_id: 음수 가중치 행 카운트}` — pack-level penalty 임계 입력."""
        import time as _time

        if not pack_ids:
            return {}
        cutoff = int(_time.time()) - int(within_seconds)
        placeholders = ",".join("?" * len(pack_ids))
        # asset → pack 매핑은 assets 테이블 JOIN 으로.
        params: list = [int(project_id), cutoff, *[int(x) for x in pack_ids]]
        rows = self.conn.execute(
            f"SELECT a.pack_id, COUNT(*) "
            f"FROM feedback_records f JOIN assets a ON a.id = f.asset_id "
            f"WHERE f.project_id = ? AND f.created_at >= ? AND f.weight < 0 "
            f"AND a.pack_id IN ({placeholders}) "
            f"GROUP BY a.pack_id",
            params,
        ).fetchall()
        return {int(pid): int(c) for pid, c in rows}


# ── helpers ──────────────────────────────────────────────────────────


_FTS_SPECIAL = set(':*-()"+^')


def _safe_fts_query(query: str) -> str:
    """FTS5 special-char 가 든 토큰을 phrase-quote 해서 안전 변환."""
    stripped = query.strip()
    if not stripped:
        return '""'
    parts: list[str] = []
    for tok in stripped.split():
        if any(ch in tok for ch in _FTS_SPECIAL):
            # 내부 따옴표는 두 번 escape (FTS5 phrase 규칙)
            inner = tok.replace('"', '""')
            parts.append(f'"{inner}"')
        else:
            parts.append(tok)
    return " ".join(parts)


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


def _project_row(r: tuple) -> ProjectRow:
    import json as _json

    blocked: list[int] = []
    if r[6]:
        try:
            data = _json.loads(r[6])
            if isinstance(data, list):
                blocked = [int(x) for x in data]
        except (json.JSONDecodeError, TypeError, ValueError):
            blocked = []
    return ProjectRow(
        id=int(r[0]),
        external_id=r[1],
        display_name=r[2],
        first_seen=int(r[3]),
        last_seen=int(r[4]),
        pinned_pack_id=int(r[5]) if r[5] is not None else None,
        blocked_packs=blocked,
    )


def _saved_search_row(r: tuple) -> SavedSearchRow:
    return SavedSearchRow(
        id=int(r[0]),
        project_id=int(r[1]) if r[1] is not None else None,
        name=str(r[2]),
        query_json=str(r[3]),
        created_at=int(r[4]),
        last_used_at=int(r[5]) if r[5] is not None else None,
    )
