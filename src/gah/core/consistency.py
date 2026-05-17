"""ConsistencyScorer — 프로젝트 통일성 가중치 (DESIGN §4.6).

검색 결과가 같은 프로젝트 내에서 점점 한 팩(또는 같은 벤더의 팩들)으로
수렴하도록 가중치를 만든다. 점수 산정 표는 DESIGN §4.6 + 본 모듈의
docstring 표를 보면 일치한다.

| 신호                       | 가중   | 조건                                                |
|----------------------------|-------:|-----------------------------------------------------|
| 같은 팩 사용 이력          | +0.6   | summary.pack_uses[pack_id] >= 1                     |
| 같은 벤더 사용 이력        | +0.3   | summary.vendor_uses[vendor] >= 1 AND 같은 팩 아님   |
| 스타일 일치                | +0.2   | summary.dominant_style == pack_aggregate.main_style |
| 팔레트 근접                | +0.1   | LAB ΔE 평균 ≤ config.palette_delta_e_threshold      |
| 굳음(locked) + 이질 팩     | -0.2   | is_locked AND pack_id ∉ summary.pack_uses           |
| pinned_pack_id == pack_id  | 1.0    | short-circuit                                       |
| pack_id ∈ blocked_packs    | 0.0    | short-circuit                                       |
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .store import PackRow, ProjectUsageSummary, Store

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsistencyResult:
    score: float                                   # 0..1 클램프
    signals: list[tuple[str, float]] = field(default_factory=list)
    locked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# ── ΔE — hex → LAB 평균 거리 ────────────────────────────────────────


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    if len(h) != 6:
        return (0.0, 0.0, 0.0)
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
    except ValueError:
        return (0.0, 0.0, 0.0)
    return (r, g, b)


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb_to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    # D65 XYZ
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def _f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = _f(x), _f(y), _f(z)
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    bb = 200 * (fy - fz)
    return (L, a, bb)


def _mean_lab(palette: list[str]) -> np.ndarray:
    if not palette:
        return np.zeros(3)
    labs = np.array([_rgb_to_lab(_hex_to_rgb(c)) for c in palette])
    return labs.mean(axis=0)


def _palette_delta_e(p1: list[str], p2: list[str]) -> float:
    """두 팔레트의 평균 LAB 사이 유클리드. 빈 팔레트 → inf (보너스 없음)."""
    if not p1 or not p2:
        return float("inf")
    return float(np.linalg.norm(_mean_lab(p1) - _mean_lab(p2)))


# ── Scorer ──────────────────────────────────────────────────────────


class ConsistencyScorer:
    def __init__(self, store: Store, config) -> None:
        self.store = store
        self.config = config

    # ----- 굳음 판정 -------------------------------------------------

    def is_locked(self, summary: ProjectUsageSummary) -> bool:
        max_packs = int(self.config.consistency_locked_max_packs)
        min_uses = int(self.config.consistency_locked_min_uses)
        return summary.distinct_packs <= max_packs and summary.total_uses >= min_uses

    # ----- 팩 단위 점수 ---------------------------------------------

    def score_pack(
        self,
        *,
        project_id: int,
        pack: PackRow,
        summary: ProjectUsageSummary,
        blocked_packs: set[int],
        pinned_pack_id: int | None,
    ) -> ConsistencyResult:
        return self._score(
            pack_id=pack.id,
            vendor=pack.vendor,
            pack_aggregate=self.store.pack_aggregate(pack.id),
            summary=summary,
            blocked_packs=blocked_packs,
            pinned_pack_id=pinned_pack_id,
        )

    # ----- 자산 단위 점수 -------------------------------------------

    def score_asset(
        self,
        *,
        project_id: int,
        asset,                                  # AssetRow or None (only pack_id is used)
        pack_aggregate: dict,
        summary: ProjectUsageSummary,
        blocked_packs: set[int],
        pinned_pack_id: int | None,
        pack: PackRow | None = None,
    ) -> ConsistencyResult:
        if pack is not None:
            pack_id = pack.id
            vendor = pack.vendor
        else:
            pack_id = int(getattr(asset, "pack_id", 0))
            vendor = None
        return self._score(
            pack_id=pack_id,
            vendor=vendor,
            pack_aggregate=pack_aggregate,
            summary=summary,
            blocked_packs=blocked_packs,
            pinned_pack_id=pinned_pack_id,
        )

    # ----- 공통 채점 ------------------------------------------------

    def _score(
        self,
        *,
        pack_id: int,
        vendor: str | None,
        pack_aggregate: dict | None,
        summary: ProjectUsageSummary,
        blocked_packs: set[int],
        pinned_pack_id: int | None,
    ) -> ConsistencyResult:
        # short-circuit: pin / block
        if pinned_pack_id is not None and pinned_pack_id == pack_id:
            return ConsistencyResult(score=1.0, signals=[("pinned", 1.0)])
        if pack_id in blocked_packs:
            return ConsistencyResult(score=0.0, signals=[("blocked", -1.0)])

        signals: list[tuple[str, float]] = []
        score = 0.0
        locked = self.is_locked(summary)

        same_pack_count = summary.pack_uses.get(int(pack_id), 0)
        same_vendor_count = summary.vendor_uses.get(vendor, 0) if vendor else 0

        if same_pack_count >= 1:
            score += 0.6
            signals.append(("same_pack_used", 0.6))
        elif same_vendor_count >= 1:
            score += 0.3
            signals.append(("same_vendor_used", 0.3))

        agg = pack_aggregate or {}
        if summary.dominant_style and agg.get("main_style") == summary.dominant_style:
            score += 0.2
            signals.append(("style_match", 0.2))

        pal = agg.get("palette") or []
        if isinstance(pal, list) and pal and summary.dominant_palette:
            delta = _palette_delta_e(summary.dominant_palette, [str(x) for x in pal])
            if delta <= float(self.config.palette_delta_e_threshold):
                score += 0.1
                signals.append(("palette_close", 0.1))

        # locked + foreign pack penalty
        if locked and same_pack_count == 0:
            score -= 0.2
            signals.append(("locked_penalty", -0.2))

        clamped = max(0.0, min(1.0, score))
        return ConsistencyResult(
            score=clamped,
            signals=signals,
            locked=locked,
            metadata={
                "same_pack_use_count": same_pack_count,
                "same_vendor_use_count": same_vendor_count,
            },
        )

    # ----- 응답 텍스트 ----------------------------------------------

    def format_why(self, result: ConsistencyResult, pack_name: str) -> str:
        """한국어 한 줄. summary 가 비어 있으면 빈 문자열 반환."""
        if result.score == 1.0 and any(name == "pinned" for name, _ in result.signals):
            return f"{pack_name} 이 이 프로젝트의 pinned 팩으로 지정되어 있음"
        same_pack = int(result.metadata.get("same_pack_use_count", 0))
        if same_pack >= 1:
            return f"이 프로젝트가 {pack_name} 을 {same_pack}회 채택했음"
        same_vendor = int(result.metadata.get("same_vendor_use_count", 0))
        if same_vendor >= 1:
            return f"이 프로젝트가 같은 벤더의 팩을 {same_vendor}회 채택했음"
        if any(name == "locked_penalty" for name, _ in result.signals):
            return "이 프로젝트가 이미 다른 팩으로 굳어 있어 통일성이 낮음"
        return ""
