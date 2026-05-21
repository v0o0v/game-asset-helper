"""M11.2 — BatchManager fetch 단계용 시트 분류 helper.

`classify_image_assets(rows, library_dir, store)` 는 각 row 에 대해
``detect_sheet`` 를 호출해 시트면 ``(AssetRow, SheetDetection)`` 튜플로,
일반 sprite 면 그대로 두 버킷으로 분리한다.  시트로 식별된 row 는 즉시
``store.update_asset_kind(id, 'spritesheet')`` 로 promote — 다음 sweep 의
``chat_spritesheet`` 카운트에 즉시 반영된다.

파일 I/O / detect_sheet 예외는 silent skip + sprite 로 분류 (graceful
fallback).  library_dir 이 ``None`` 이면 분류 자체를 skip 하고 모든 row 를
sprite_rows 로 반환한다 (테스트 / library 없는 환경 호환).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..sheet.detect import detect_sheet

if TYPE_CHECKING:
    from ..sheet.detect import SheetDetection
    from ..store import AssetRow, Store

log = logging.getLogger(__name__)


def classify_image_assets(
    rows: "list[AssetRow]",
    *,
    library_dir: Path | None,
    store: "Store",
) -> "tuple[list[tuple[AssetRow, SheetDetection]], list[AssetRow]]":
    """detect_sheet 결과로 (sheet_results, sprite_rows) 로 분리 + kind promote.

    sheet_results: ``[(row, detection), ...]`` — kind 가 spritesheet 로 promote 됨.
    sprite_rows: detect_sheet miss / 예외 / library_dir=None — 일반 sprite.
    """
    if library_dir is None:
        return [], list(rows)

    sheet_results: list[tuple["AssetRow", "SheetDetection"]] = []
    sprite_rows: list["AssetRow"] = []

    for row in rows:
        try:
            abs_path = (library_dir / row.path).resolve()
            detection = detect_sheet(abs_path)
        except Exception as e:  # noqa: BLE001 — file I/O 또는 detect 오류 graceful skip
            log.warning(
                "classify_image_assets: detect_sheet failed asset_id=%d path=%s: %s",
                row.id, row.path, e,
            )
            sprite_rows.append(row)
            continue
        if detection is None:
            sprite_rows.append(row)
        else:
            sheet_results.append((row, detection))
            try:
                store.update_asset_kind(row.id, "spritesheet")
            except Exception as e:  # noqa: BLE001 — DB 오류여도 batch 진행
                log.warning(
                    "classify_image_assets: update_asset_kind failed asset_id=%d: %s",
                    row.id, e,
                )
    return sheet_results, sprite_rows
