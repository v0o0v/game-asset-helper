"""SQLite store for AssetCacheMCP.

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


# ── M7 dataclasses ────────────────────────────────────────────────────


@dataclass
class ProjectSummary:
    """M7: 프로젝트 목록 뷰 — 통계 포함."""

    id: int
    external_id: str
    display_name: str | None
    first_seen: int
    last_seen: int
    asset_count: int
    top_pack_id: int | None
    top_pack_name: str | None
    top_pack_uses: int
    pinned_pack_id: int | None
    pinned_pack_name: str | None
    blocked_count: int


@dataclass
class AssetUsageRow:
    """M7: 프로젝트 단위 사용 이력 행."""

    asset_id: int
    asset_path: str
    pack_id: int
    pack_name: str | None
    used_at: int
    source: str
    context: str | None
    kind: str


@dataclass
class PackDistRow:
    """M7: 프로젝트 팩 분포 행."""

    pack_id: int
    pack_name: str | None
    uses: int


@dataclass
class PreferenceRow:
    """M7: 프로젝트 자산 선호도 행 — 피드백 + 사용 복합 점수."""

    asset_id: int
    asset_path: str
    pack_id: int
    pack_name: str | None
    kind: str
    composite_score: float
    signed_weight_sum: float
    positive_count: int
    negative_count: int
    irrelevant_count: int
    usage_count: int
    last_activity_at: int | None


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


_M7_UNITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS unity_imports (
  id                       INTEGER PRIMARY KEY,
  package_path             TEXT NOT NULL UNIQUE,
  publisher                TEXT,
  category                 TEXT,
  asset_name               TEXT NOT NULL,
  package_size             INTEGER NOT NULL,
  package_mtime            INTEGER NOT NULL,
  preview_asset_count      INTEGER,
  preview_image_count      INTEGER,
  preview_sound_count      INTEGER,
  preview_inspected_at     INTEGER,
  pack_id                  INTEGER REFERENCES packs(id) ON DELETE SET NULL,
  import_state             TEXT NOT NULL,
  import_error             TEXT,
  imported_at              INTEGER,
  first_seen_at            INTEGER NOT NULL,
  last_scanned_at          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_unity_imports_pack ON unity_imports(pack_id);
CREATE INDEX IF NOT EXISTS idx_unity_imports_state ON unity_imports(import_state);
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
        """Create M1 + M2 + M3 + M4 + M7 tables.  Safe to call repeatedly."""
        self.conn.executescript(_M1_SCHEMA)
        self.conn.executescript(_M2_SCHEMA)
        self.conn.executescript(_M3_SCHEMA)
        self.conn.executescript(_M4_SCHEMA)
        self._migrate_m6_animations_json()
        self._migrate_unity_imports()

    def _migrate_m6_animations_json(self) -> None:
        """M6 — sprite_meta.animations_json 컬럼 idempotent 추가."""
        with self.write_lock:
            cur = self.conn.execute("PRAGMA table_info(sprite_meta)")
            cols = {r[1] for r in cur.fetchall()}
            if "animations_json" not in cols:
                self.conn.execute(
                    "ALTER TABLE sprite_meta ADD COLUMN animations_json TEXT"
                )

    def _migrate_unity_imports(self) -> None:
        """M7 — unity_imports 테이블 + 인덱스 idempotent 생성."""
        with self.write_lock:
            self.conn.executescript(_M7_UNITY_SCHEMA)

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
        # M7 patch — read 도 write_lock 안에서 (M6 의 pack_aggregate fix 패턴).
        # 분석 thread 가 DB 쓰는 중 다른 thread 의 connection.execute 가
        # sqlite3.InterfaceError 발생하는 회귀 방어.
        with self.write_lock:
            return int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM assets WHERE pack_id = ?", (pack_id,)
                ).fetchone()[0]
            )

    def get_asset_by_id(self, asset_id: int) -> Optional[AssetRow]:
        # M7 patch — read 도 write_lock 안에서 (분석 큐 동시 access 시
        # sqlite3.InterfaceError 회피).
        with self.write_lock:
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
        row = self.conn.execute(
            "SELECT COUNT(*) FROM assets WHERE analysis_state = 'pending'"
        ).fetchone()
        # SQLite 의 COUNT(*) 는 항상 row 1개 반환하지만, 트레이 부팅 직후
        # 분석 워커 thread 가 conn 을 쓰는 동시에 main thread 가 schema
        # migration 중이면 cursor 가 일시적으로 None 을 보낼 수 있어 방어.
        if row is None or row[0] is None:
            return 0
        return int(row[0])

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

    def upsert_project_id(
        self, *, external_id: str, display_name: str | None = None
    ) -> int:
        """M7: upsert_project 의 int-반환 variant.

        기존 upsert_project(ProjectRow 반환) 와 동일 로직이지만
        project_id (int) 만 반환해 테스트·MCP 등에서 편리하게 쓸 수 있다.
        """
        return self.upsert_project(external_id, display_name=display_name).id

    # -- M7: projects 쿼리 --------------------------------------------------

    def list_projects_with_summary(self) -> "list[ProjectSummary]":
        """projects 목록 + asset_usage 통계 JOIN.

        ProjectSummary.asset_count — project 에 사용된 asset 고유 수.
        top_pack_* — 가장 많이 쓰인 팩.
        """
        rows = self.conn.execute(
            """
            SELECT
                p.id,
                p.external_id,
                p.display_name,
                p.first_seen,
                p.last_seen,
                p.pinned_pack_id,
                COALESCE(stats.asset_count, 0) AS asset_count,
                stats.top_pack_id,
                pk_top.name          AS top_pack_name,
                COALESCE(stats.top_pack_uses, 0) AS top_pack_uses,
                pk_pin.name          AS pinned_pack_name,
                COALESCE(stats.blocked_count, 0) AS blocked_count
            FROM projects p
            LEFT JOIN (
                SELECT
                    project_id,
                    COUNT(DISTINCT asset_id) AS asset_count,
                    pack_id                  AS top_pack_id,
                    COUNT(*)                 AS top_pack_uses,
                    0                        AS blocked_count
                FROM (
                    SELECT
                        au.project_id,
                        au.asset_id,
                        au.pack_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY au.project_id
                            ORDER BY cnt DESC
                        ) AS rn
                    FROM asset_usage au
                    JOIN (
                        SELECT project_id, pack_id, COUNT(*) AS cnt
                        FROM asset_usage
                        GROUP BY project_id, pack_id
                    ) agg ON agg.project_id = au.project_id
                           AND agg.pack_id = au.pack_id
                )
                WHERE rn = 1
                GROUP BY project_id
            ) stats ON stats.project_id = p.id
            LEFT JOIN packs pk_top ON pk_top.id = stats.top_pack_id
            LEFT JOIN packs pk_pin ON pk_pin.id = p.pinned_pack_id
            ORDER BY p.last_seen DESC
            """
        ).fetchall()
        result = []
        for r in rows:
            (pid, ext_id, dname, first_seen, last_seen, pinned_pack_id,
             asset_count, top_pack_id, top_pack_name, top_pack_uses,
             pinned_pack_name, blocked_count) = r
            result.append(ProjectSummary(
                id=int(pid),
                external_id=str(ext_id),
                display_name=dname,
                first_seen=int(first_seen),
                last_seen=int(last_seen),
                asset_count=int(asset_count),
                top_pack_id=int(top_pack_id) if top_pack_id is not None else None,
                top_pack_name=top_pack_name,
                top_pack_uses=int(top_pack_uses),
                pinned_pack_id=int(pinned_pack_id) if pinned_pack_id is not None else None,
                pinned_pack_name=pinned_pack_name,
                blocked_count=int(blocked_count),
            ))
        return result

    def get_project_asset_usage(
        self,
        *,
        project_id: int,
        offset: int = 0,
        limit: int | None = None,
    ) -> "list[AssetUsageRow]":
        """asset_usage JOIN assets, 최근 used_at DESC."""
        sql = (
            "SELECT au.asset_id, a.path, au.pack_id, p.name, "
            "au.used_at, au.source, au.context, a.kind "
            "FROM asset_usage au "
            "JOIN assets a ON a.id = au.asset_id "
            "LEFT JOIN packs p ON p.id = au.pack_id "
            "WHERE au.project_id = ? "
            "ORDER BY au.used_at DESC "
        )
        params: list = [int(project_id)]
        if limit is not None:
            sql += "LIMIT ? OFFSET ?"
            params += [int(limit), int(offset)]
        elif offset:
            sql += "LIMIT -1 OFFSET ?"
            params.append(int(offset))
        rows = self.conn.execute(sql, params).fetchall()
        return [
            AssetUsageRow(
                asset_id=int(r[0]), asset_path=str(r[1]),
                pack_id=int(r[2]), pack_name=r[3],
                used_at=int(r[4]), source=str(r[5]),
                context=r[6], kind=str(r[7]),
            )
            for r in rows
        ]

    def get_project_pack_distribution(
        self,
        *,
        project_id: int,
        top_n: int = 5,
    ) -> "list[PackDistRow]":
        """asset_usage GROUP BY pack_id, top_n."""
        rows = self.conn.execute(
            "SELECT au.pack_id, p.name, COUNT(*) AS uses "
            "FROM asset_usage au "
            "LEFT JOIN packs p ON p.id = au.pack_id "
            "WHERE au.project_id = ? "
            "GROUP BY au.pack_id "
            "ORDER BY uses DESC "
            "LIMIT ?",
            (int(project_id), int(top_n)),
        ).fetchall()
        return [
            PackDistRow(pack_id=int(r[0]), pack_name=r[1], uses=int(r[2]))
            for r in rows
        ]

    def get_project_asset_preferences(
        self,
        *,
        project_id: int,
        sort: str = "score_desc",
        search: str | None = None,
        offset: int = 0,
        limit: int | None = None,
        preference_usage_weight: float = 0.1,
    ) -> "list[PreferenceRow]":
        """feedback_records + asset_usage 종합 → composite_score.

        composite_score = SUM(feedback.weight) + preference_usage_weight * usage_count
        I-5 격리: project_id 별 필터 적용.
        """
        # 피드백 집계
        fb_rows = self.conn.execute(
            "SELECT f.asset_id, "
            "SUM(f.weight) AS wsum, "
            "SUM(CASE WHEN f.weight > 0 THEN 1 ELSE 0 END) AS pos, "
            "SUM(CASE WHEN f.weight < 0 THEN 1 ELSE 0 END) AS neg, "
            "SUM(CASE WHEN f.weight = 0 THEN 1 ELSE 0 END) AS irr "
            "FROM feedback_records f "
            "WHERE f.project_id = ? "
            "GROUP BY f.asset_id",
            (int(project_id),),
        ).fetchall()
        fb_map: dict[int, tuple] = {
            int(r[0]): (float(r[1] or 0), int(r[2] or 0), int(r[3] or 0), int(r[4] or 0))
            for r in fb_rows
        }

        # 사용 집계
        usage_rows = self.conn.execute(
            "SELECT asset_id, COUNT(*) AS cnt, MAX(used_at) AS last_at "
            "FROM asset_usage "
            "WHERE project_id = ? "
            "GROUP BY asset_id",
            (int(project_id),),
        ).fetchall()
        usage_map: dict[int, tuple] = {
            int(r[0]): (int(r[1]), int(r[2]) if r[2] is not None else None)
            for r in usage_rows
        }

        # 유니언 asset id
        all_ids = set(fb_map) | set(usage_map)
        if not all_ids:
            return []

        # asset 정보 조회
        placeholders = ",".join("?" * len(all_ids))
        asset_rows = self.conn.execute(
            f"SELECT a.id, a.path, a.pack_id, p.name, a.kind "
            f"FROM assets a "
            f"LEFT JOIN packs p ON p.id = a.pack_id "
            f"WHERE a.id IN ({placeholders})",
            list(all_ids),
        ).fetchall()
        asset_info = {
            int(r[0]): (str(r[1]), int(r[2]) if r[2] else 0, r[3], str(r[4]))
            for r in asset_rows
        }

        # 검색 필터
        if search:
            lo = search.lower()
            asset_info = {
                aid: info for aid, info in asset_info.items()
                if lo in info[0].lower() or (info[2] and lo in info[2].lower())
            }
            all_ids = set(asset_info)

        rows_out: list[PreferenceRow] = []
        for aid in all_ids:
            if aid not in asset_info:
                continue
            path, pack_id, pack_name, kind = asset_info[aid]
            wsum, pos, neg, irr = fb_map.get(aid, (0.0, 0, 0, 0))
            usage_cnt, last_used = usage_map.get(aid, (0, None))
            # feedback의 last created_at
            fb_last = self.conn.execute(
                "SELECT MAX(created_at) FROM feedback_records "
                "WHERE project_id = ? AND asset_id = ?",
                (int(project_id), int(aid)),
            ).fetchone()[0]
            last_act = None
            if fb_last is not None and last_used is not None:
                last_act = max(int(fb_last), int(last_used))
            elif fb_last is not None:
                last_act = int(fb_last)
            elif last_used is not None:
                last_act = int(last_used)

            composite = float(wsum) + preference_usage_weight * float(usage_cnt)
            rows_out.append(PreferenceRow(
                asset_id=int(aid),
                asset_path=path,
                pack_id=pack_id,
                pack_name=pack_name,
                kind=kind,
                composite_score=composite,
                signed_weight_sum=float(wsum),
                positive_count=int(pos),
                negative_count=int(neg),
                irrelevant_count=int(irr),
                usage_count=int(usage_cnt),
                last_activity_at=last_act,
            ))

        # 정렬
        if sort == "score_desc":
            rows_out.sort(key=lambda r: r.composite_score, reverse=True)
        elif sort == "score_asc":
            rows_out.sort(key=lambda r: r.composite_score)
        elif sort == "usage_desc":
            rows_out.sort(key=lambda r: r.usage_count, reverse=True)
        elif sort == "recent_desc":
            rows_out.sort(
                key=lambda r: r.last_activity_at if r.last_activity_at is not None else 0,
                reverse=True,
            )

        # 페이지네이션
        if limit is not None:
            rows_out = rows_out[offset: offset + limit]
        elif offset:
            rows_out = rows_out[offset:]

        return rows_out

    def count_project_asset_preferences(
        self,
        *,
        project_id: int,
        search: str | None = None,
    ) -> int:
        """페이지네이션용 total count."""
        return len(self.get_project_asset_preferences(
            project_id=project_id, search=search,
        ))

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
        used_at: int | None = None,
    ) -> int:
        """asset 사용 기록 INSERT.

        source 허용 값: "explicit" | "implicit_top1" | "manual" |
        "claude_pick" | "user_web" (M7 신규).
        used_at 이 None 이면 현재 시각 사용.
        """
        import time as _time

        ts = used_at if used_at is not None else int(_time.time())
        with self.write_lock:
            self.conn.execute(
                "INSERT INTO asset_usage (project_id, asset_id, pack_id, used_at, "
                "source, context) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, asset_id, pack_id, ts, source, context),
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

    # -- M7: unity_imports CRUD ------------------------------------------

    def insert_unity_import(
        self,
        pkg: "UnityPackagePath",
        *,
        first_seen_at: int,
        last_scanned_at: int,
    ) -> int:
        """신규 row INSERT (state='discovered' 자동). UNIQUE package_path 위반 시 raise."""
        from .unity_import.types import UnityPackagePath as _UPP  # noqa: F401

        with self.write_lock:
            self.conn.execute(
                """
                INSERT INTO unity_imports (
                  package_path, publisher, category, asset_name,
                  package_size, package_mtime,
                  import_state, first_seen_at, last_scanned_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'discovered', ?, ?)
                """,
                (
                    str(pkg.abs_path),
                    pkg.publisher,
                    pkg.category,
                    pkg.asset_name,
                    pkg.size,
                    pkg.mtime,
                    first_seen_at,
                    last_scanned_at,
                ),
            )
            return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def upsert_unity_import(
        self,
        pkg: "UnityPackagePath",
        *,
        last_scanned_at: int,
    ) -> int:
        """package_path 기준 INSERT OR UPDATE. publisher/category/asset_name/size/mtime 갱신."""
        with self.write_lock:
            row = self.conn.execute(
                "SELECT id FROM unity_imports WHERE package_path = ?",
                (str(pkg.abs_path),),
            ).fetchone()
            if row is None:
                self.conn.execute(
                    """
                    INSERT INTO unity_imports (
                      package_path, publisher, category, asset_name,
                      package_size, package_mtime,
                      import_state, first_seen_at, last_scanned_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'discovered', ?, ?)
                    """,
                    (
                        str(pkg.abs_path),
                        pkg.publisher,
                        pkg.category,
                        pkg.asset_name,
                        pkg.size,
                        pkg.mtime,
                        last_scanned_at,
                        last_scanned_at,
                    ),
                )
                return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            uid = int(row[0])
            self.conn.execute(
                """
                UPDATE unity_imports SET
                  publisher = ?,
                  category = ?,
                  asset_name = ?,
                  package_size = ?,
                  package_mtime = ?,
                  last_scanned_at = ?
                WHERE id = ?
                """,
                (
                    pkg.publisher,
                    pkg.category,
                    pkg.asset_name,
                    pkg.size,
                    pkg.mtime,
                    last_scanned_at,
                    uid,
                ),
            )
            return uid

    def update_unity_state(
        self,
        unity_import_id: int,
        state: str,
        *,
        pack_id: "int | None" = None,
        imported_at: "int | None" = None,
        import_error: "str | None" = None,
        new_mtime: "int | None" = None,
        new_size: "int | None" = None,
        last_scanned_at: "int | None" = None,
        reset_preview: bool = False,
    ) -> None:
        """state + 부수 컬럼 갱신. reset_preview=True 면 preview_* 4 컬럼 NULL 화."""
        parts: list[str] = ["import_state = ?"]
        params: list = [state]
        if pack_id is not None:
            parts.append("pack_id = ?")
            params.append(int(pack_id))
        if imported_at is not None:
            parts.append("imported_at = ?")
            params.append(int(imported_at))
        if import_error is not None:
            parts.append("import_error = ?")
            params.append(import_error)
        if new_mtime is not None:
            parts.append("package_mtime = ?")
            params.append(int(new_mtime))
        if new_size is not None:
            parts.append("package_size = ?")
            params.append(int(new_size))
        if last_scanned_at is not None:
            parts.append("last_scanned_at = ?")
            params.append(int(last_scanned_at))
        if reset_preview:
            parts.extend([
                "preview_asset_count = NULL",
                "preview_image_count = NULL",
                "preview_sound_count = NULL",
                "preview_inspected_at = NULL",
            ])
        params.append(int(unity_import_id))
        with self.write_lock:
            self.conn.execute(
                f"UPDATE unity_imports SET {', '.join(parts)} WHERE id = ?",
                params,
            )

    def update_unity_preview(
        self,
        unity_import_id: int,
        *,
        asset_count: int,
        image_count: int,
        sound_count: int,
    ) -> None:
        """미리보기 카운트 + preview_inspected_at 갱신. state 변경 X."""
        import time as _time

        with self.write_lock:
            self.conn.execute(
                """
                UPDATE unity_imports SET
                  preview_asset_count = ?,
                  preview_image_count = ?,
                  preview_sound_count = ?,
                  preview_inspected_at = ?
                WHERE id = ?
                """,
                (
                    int(asset_count),
                    int(image_count),
                    int(sound_count),
                    int(_time.time()),
                    int(unity_import_id),
                ),
            )

    def touch_unity_import(
        self, unity_import_id: int, *, last_scanned_at: int,
    ) -> None:
        """last_scanned_at 만 갱신 (unchanged 케이스용)."""
        with self.write_lock:
            self.conn.execute(
                "UPDATE unity_imports SET last_scanned_at = ? WHERE id = ?",
                (int(last_scanned_at), int(unity_import_id)),
            )

    def list_unity_imports(
        self,
        *,
        state: "str | None" = None,
        publisher_glob: "str | None" = None,
        asset_name_glob: "str | None" = None,
        offset: int = 0,
        limit: "int | None" = None,
    ) -> "list[UnityImportRecord]":
        """필터 + 페이지네이션. glob 은 SQL LIKE (% / _) 변환."""
        from .unity_import.types import UnityImportRecord as _UIR  # noqa: F401

        sql = (
            "SELECT id, package_path, publisher, category, asset_name,"
            " package_size, package_mtime,"
            " preview_asset_count, preview_image_count, preview_sound_count,"
            " preview_inspected_at, pack_id, import_state, import_error,"
            " imported_at, first_seen_at, last_scanned_at"
            " FROM unity_imports"
        )
        params: list = []
        where: list[str] = []
        if state is not None:
            where.append("import_state = ?")
            params.append(state)
        if publisher_glob is not None:
            where.append("publisher LIKE ?")
            params.append(publisher_glob.replace("*", "%").replace("?", "_"))
        if asset_name_glob is not None:
            where.append("asset_name LIKE ?")
            params.append(asset_name_glob.replace("*", "%").replace("?", "_"))
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(int(offset))
        rows = self.conn.execute(sql, params).fetchall()
        return [_unity_import_row(r) for r in rows]

    def count_unity_imports(
        self,
        *,
        state: "str | None" = None,
        publisher_glob: "str | None" = None,
        asset_name_glob: "str | None" = None,
    ) -> int:
        """페이지네이션용 total."""
        sql = "SELECT COUNT(*) FROM unity_imports"
        params: list = []
        where: list[str] = []
        if state is not None:
            where.append("import_state = ?")
            params.append(state)
        if publisher_glob is not None:
            where.append("publisher LIKE ?")
            params.append(publisher_glob.replace("*", "%").replace("?", "_"))
        if asset_name_glob is not None:
            where.append("asset_name LIKE ?")
            params.append(asset_name_glob.replace("*", "%").replace("?", "_"))
        if where:
            sql += " WHERE " + " AND ".join(where)
        row = self.conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    def get_unity_import_by_id(
        self, unity_import_id: int
    ) -> "UnityImportRecord | None":
        """단일 row by id. 없으면 None."""
        row = self.conn.execute(
            "SELECT id, package_path, publisher, category, asset_name,"
            " package_size, package_mtime,"
            " preview_asset_count, preview_image_count, preview_sound_count,"
            " preview_inspected_at, pack_id, import_state, import_error,"
            " imported_at, first_seen_at, last_scanned_at"
            " FROM unity_imports WHERE id = ?",
            (int(unity_import_id),),
        ).fetchone()
        return _unity_import_row(row) if row else None

    def get_unity_import_by_path(
        self, package_path: Path
    ) -> "UnityImportRecord | None":
        """단일 row by package_path. 없으면 None."""
        row = self.conn.execute(
            "SELECT id, package_path, publisher, category, asset_name,"
            " package_size, package_mtime,"
            " preview_asset_count, preview_image_count, preview_sound_count,"
            " preview_inspected_at, pack_id, import_state, import_error,"
            " imported_at, first_seen_at, last_scanned_at"
            " FROM unity_imports WHERE package_path = ?",
            (str(package_path),),
        ).fetchone()
        return _unity_import_row(row) if row else None


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


def _unity_import_row(r: tuple) -> "UnityImportRecord":
    """sqlite3 row tuple → UnityImportRecord dataclass 변환.

    컬럼 순서 (17개):
      0  id
      1  package_path
      2  publisher
      3  category
      4  asset_name
      5  package_size
      6  package_mtime
      7  preview_asset_count
      8  preview_image_count
      9  preview_sound_count
      10 preview_inspected_at
      11 pack_id
      12 import_state
      13 import_error
      14 imported_at
      15 first_seen_at
      16 last_scanned_at
    """
    from .unity_import.types import UnityImportRecord

    return UnityImportRecord(
        id=int(r[0]),
        package_path=Path(r[1]),
        publisher=r[2],
        category=r[3],
        asset_name=r[4],
        package_size=int(r[5]),
        package_mtime=int(r[6]),
        preview_asset_count=int(r[7]) if r[7] is not None else None,
        preview_image_count=int(r[8]) if r[8] is not None else None,
        preview_sound_count=int(r[9]) if r[9] is not None else None,
        preview_inspected_at=int(r[10]) if r[10] is not None else None,
        pack_id=int(r[11]) if r[11] is not None else None,
        import_state=r[12],
        import_error=r[13],
        imported_at=int(r[14]) if r[14] is not None else None,
        first_seen_at=int(r[15]),
        last_scanned_at=int(r[16]),
    )
