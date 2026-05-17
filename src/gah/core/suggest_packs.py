"""M4 — `suggest_packs` 의 samples 풍부화 (thumbnail_path + preview_blurb).

DESIGN §6.5 의 `samples[]` 필드를 채운다.  v1 정책:
- sprite → `thumbnail_path` = lazy 256×256 PNG, `preview_blurb` = top-2 라벨
- sound/spritesheet → `thumbnail_path = None`, `preview_blurb` = top-2 라벨

description (Gemma 한 줄 요약) 통합은 M5+ 가 `assets.description` 컬럼 추가
시 갱신.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .thumbnails import ensure_thumbnail


if TYPE_CHECKING:  # pragma: no cover
    from .store import AssetRow, Store


log = logging.getLogger(__name__)


def enrich_sample(
    asset_row: "AssetRow",
    store: "Store",
    cache_dir: Path,
    *,
    library_root: Path,
    include_thumbnails: bool = True,
) -> dict:
    """asset_row → suggest_packs.samples[i] dict.

    Returned dict shape:
        {asset_id, path, kind, thumbnail_path: str|None, preview_blurb: str|None}

    ``library_root`` は assets.path が library_root 기준 상대경로이므로
    절대경로로 변환할 때 필요하다.
    """
    thumb: Path | None = None
    if include_thumbnails:
        thumb = ensure_thumbnail(
            library_root / asset_row.path, asset_row.kind, cache_dir, asset_row.id,
        )
    return {
        "asset_id": asset_row.id,
        "path": asset_row.path,
        "kind": asset_row.kind,
        "thumbnail_path": str(thumb) if thumb is not None else None,
        "preview_blurb": _extract_blurb(asset_row, store),
    }


def _extract_blurb(asset_row: "AssetRow", store: "Store") -> str | None:
    """v1: 상위 2개 라벨로 `axis=label · axis=label` 문자열 생성.

    M5+ 에서 Gemma description 통합 시 description 첫 한 줄 (80자 컷) 으로 갱신
    예정 (`assets.description` 컬럼 추가가 선행).
    """
    labels = store.labels_for_asset(asset_row.id)
    if not labels:
        return None
    # labels_for_asset 은 score DESC 정렬 — 상위 2개.
    seen: set[tuple[str, str]] = set()
    picks: list[str] = []
    for lbl in labels:
        key = (lbl.axis, lbl.label)
        if key in seen:
            continue
        seen.add(key)
        picks.append(f"{lbl.axis}={lbl.label}")
        if len(picks) >= 2:
            break
    return " · ".join(picks) if picks else None
