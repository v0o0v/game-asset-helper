"""M11.2 — BatchManager fetch 단계용 시트 분류 helper.

`classify_image_assets(rows, library_dir, store, cache, save_sprite_meta)` 는
각 row 에 대해 ``detect_sheet`` 를 호출해 시트면 ``(AssetRow, SheetDetection)``
튜플로, 일반 sprite 면 그대로 두 버킷으로 분리한다.  시트로 식별된 row 는 즉시
``store.update_asset_kind(id, 'spritesheet')`` 로 promote — 다음 sweep 의
``chat_spritesheet`` 카운트에 즉시 반영된다.

파일 I/O / detect_sheet 예외는 silent skip + sprite 로 분류 (graceful
fallback).  library_dir 이 ``None`` 이면 분류 자체를 skip 하고 모든 row 를
sprite_rows 로 반환한다 (테스트 / library 없는 환경 호환).

M11.3 — 2-층 캐시:
* ``cache: dict[int, SheetDetection | None]`` — same-sweep 메모리 캐시 (옵션 C).
  hit 시 ``detect_sheet`` 호출 우회.  miss 시 결과 (양성 SheetDetection 또는
  None) 를 cache 에 기록.  ``None`` 값은 "시트 아님이 확인됨" 의미 — 다음 호출도
  detect_sheet 우회.  ``cache=None`` 이면 캐시 사용 안 함 (기존 동작).
* ``save_sprite_meta: bool = True`` — 시트 hit 시 ``compute_sprite_meta`` +
  ``enrich_sprite_meta_with_sheet`` + ``store.save_sprite_meta`` 까지 자동
  수행 (옵션 B).  이후 BatchPoller persist 시 ``sprite_meta`` 캐시 hit 으로
  detect_sheet 재호출 우회.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..analyzer.spritesheet_meta import enrich_sprite_meta_with_sheet
from ..analyzer.tech_meta import compute_sprite_meta
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
    cache: "dict[int, SheetDetection | None] | None" = None,
    save_sprite_meta: bool = True,
    alpha_color_weight: float = 0.5,
) -> "tuple[list[tuple[AssetRow, SheetDetection]], list[AssetRow]]":
    """detect_sheet 결과로 (sheet_results, sprite_rows) 로 분리 + kind promote.

    sheet_results: ``[(row, detection), ...]`` — kind 가 spritesheet 로 promote 됨.
    sprite_rows: detect_sheet miss / 예외 / library_dir=None — 일반 sprite.

    M11.3 — ``cache`` dict 가 주어지면 row.id 키로 detection 결과 (양성/음성)
    를 기록하고 hit 시 detect_sheet 우회.  ``save_sprite_meta=True`` (default)
    이면 시트 hit 시 sprite_meta 자동 enrich + save → DB cross-sweep cache 활성.
    """
    if library_dir is None:
        return [], list(rows)

    sheet_results: list[tuple["AssetRow", "SheetDetection"]] = []
    sprite_rows: list["AssetRow"] = []

    for row in rows:
        detection: "SheetDetection | None"
        if cache is not None and row.id in cache:
            detection = cache[row.id]
        else:
            try:
                abs_path = (library_dir / row.path).resolve()
                detection = detect_sheet(
                    abs_path, alpha_color_weight=alpha_color_weight,
                )
            except Exception as e:  # noqa: BLE001 — file I/O 또는 detect 오류 graceful skip
                log.warning(
                    "classify_image_assets: detect_sheet failed asset_id=%d path=%s: %s",
                    row.id, row.path, e,
                )
                sprite_rows.append(row)
                if cache is not None:
                    # 예외도 cache 에 None 으로 기록 — 같은 sweep 내 재시도 방지
                    cache[row.id] = None
                continue
            if cache is not None:
                cache[row.id] = detection

        if detection is None:
            sprite_rows.append(row)
            continue

        sheet_results.append((row, detection))
        try:
            store.update_asset_kind(row.id, "spritesheet")
        except Exception as e:  # noqa: BLE001 — DB 오류여도 batch 진행
            log.warning(
                "classify_image_assets: update_asset_kind failed asset_id=%d: %s",
                row.id, e,
            )
        if save_sprite_meta:
            try:
                abs_path = (library_dir / row.path).resolve()
                base_meta = compute_sprite_meta(abs_path)
                enriched = enrich_sprite_meta_with_sheet(base_meta, detection)
                store.save_sprite_meta(row.id, enriched)
            except Exception as e:  # noqa: BLE001 — meta 계산/저장 오류여도 batch 진행
                log.warning(
                    "classify_image_assets: sprite_meta save failed asset_id=%d: %s",
                    row.id, e,
                )
    return sheet_results, sprite_rows
