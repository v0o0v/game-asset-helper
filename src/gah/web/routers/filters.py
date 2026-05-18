"""M5 — 검색 필터 라우터.

Phase 3B-1 에서 구현:
  - ``_classify_axis(axis_id)`` : axis prefix 기반 sprite/sheet/sound 분류
  - ``GET /api/filters/labels`` : 라벨 카탈로그를 sprite/sheet/sound 버킷으로 분류해 반환
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["filters"])


# ── axis 분류 ──────────────────────────────────────────────────────────


def _classify_axis(axis_id: str) -> str:
    """axis 식별자를 sprite / sheet / sound 버킷으로 분류한다.

    분류 규칙:
    - ``sound_`` 접두어 → "sound"
    - ``sheet_`` 접두어 → "sheet"
    - 그 외 → "sprite"
    """
    if axis_id.startswith("sound_"):
        return "sound"
    if axis_id.startswith("sheet_"):
        return "sheet"
    return "sprite"


# ── 엔드포인트 ──────────────────────────────────────────────────────────


@router.get("/filters/packs")
def api_filters_packs(request: Request) -> dict:
    """팩 카탈로그 + 벤더/라이선스 distinct 값 반환.

    응답 형태::

        {
          "packs": [
            {
              "id": 1,
              "name": "pack_a",
              "display_name": "Pack A",
              "vendor": "kenney",
              "license": "CC0",
              "enabled": true,
              "asset_count": 42,
            },
            ...
          ],
          "vendors": ["craftpix", "kenney"],
          "licenses": ["CC0", "MIT"],
        }

    ``vendors`` / ``licenses`` 는 packs 에서 추출한 distinct 정렬 목록.
    빈 카탈로그 → ``packs: []``, ``vendors: []``, ``licenses: []``.
    """
    deps = request.app.state.deps
    packs = deps.store.list_packs(include_disabled=True)
    items = []
    for p in packs:
        items.append(
            {
                "id": p.id,
                "name": p.name,
                "display_name": p.display_name or p.name,
                "vendor": p.vendor or "",
                "license": p.license or "",
                "enabled": bool(p.enabled),
                "asset_count": deps.store.count_assets_in_pack(p.id),
            }
        )
    # vendor / license distinct 값
    vendors = sorted({i["vendor"] for i in items if i["vendor"]})
    licenses = sorted({i["license"] for i in items if i["license"]})
    return {
        "packs": items,
        "vendors": vendors,
        "licenses": licenses,
    }


@router.get("/filters/labels")
def get_filters_labels(request: Request) -> dict:
    """라벨 카탈로그를 sprite / sheet / sound 버킷으로 분류해 반환한다.

    응답 형태::

        {
          "sprite": [
            {
              "axis": "category",
              "label_ko": "category",
              "labels": [
                {"id": 1, "label": "character", "label_ko": "character"},
                ...
              ]
            },
            ...
          ],
          "sheet": [],
          "sound": [
            {
              "axis": "sound_category",
              "label_ko": "sound_category",
              "labels": [...]
            },
            ...
          ]
        }

    ``label_ko`` 는 v1 에서 영어 label 그대로다 (한글 매핑은 M8 i18n).
    ``enabled_only=True`` 기본값으로 비활성 라벨은 제외한다.
    """
    deps = request.app.state.deps
    store = deps.store

    # 모든 활성 라벨 로드
    all_labels = store.list_labels_raw(axis=None, enabled_only=True)

    # axis 별로 그룹핑 (dict[axis_id, list[LabelRow]])
    by_axis: dict[str, list] = defaultdict(list)
    for row in all_labels:
        by_axis[row.axis].append(row)

    # 버킷 초기화
    buckets: dict[str, list] = {"sprite": [], "sheet": [], "sound": []}

    for axis_id, rows in by_axis.items():
        kind = _classify_axis(axis_id)
        group = {
            "axis": axis_id,
            "label_ko": axis_id,  # v1: 영어 그대로, M8 에서 한글 매핑
            "labels": [
                {
                    "id": r.id,
                    "label": r.label,
                    "label_ko": r.label,  # v1: 영어 그대로
                }
                for r in rows
            ],
        }
        buckets[kind].append(group)

    return buckets
