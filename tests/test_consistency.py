"""M3 — ConsistencyScorer (DESIGN §4.6 표를 코드로)."""

from __future__ import annotations

import pytest


@pytest.fixture
def scorer(store):
    from gah.core.consistency import ConsistencyScorer
    from gah.config import Config

    return ConsistencyScorer(store, Config())


def _pack_aggregate(main_style: str = "pixel_art", palette: list[str] | None = None) -> dict:
    return {
        "main_style": main_style,
        "palette": palette or ["#aa1122", "#22aa11", "#1122aa"],
    }


def _pack_row(pack_id: int = 1, vendor: str = "kenney"):
    from gah.core.store import PackRow

    return PackRow(
        id=pack_id,
        name=f"pack_{pack_id}",
        display_name="Pack",
        vendor=vendor,
        source_url=None,
        license=None,
        description=None,
        enabled=True,
        added_at=1_700_000_000,
        scanned_at=1_700_000_000,
    )


# ─────────────────────────────────────────────────────────────────────


def test_first_search_no_history_returns_zero_score(scorer, consistency_summary_factory):
    summary = consistency_summary_factory()  # empty
    pack = _pack_row(pack_id=1, vendor="kenney")
    result = scorer.score_pack(
        project_id=99, pack=pack, summary=summary,
        blocked_packs=set(), pinned_pack_id=None,
    )
    assert result.score == pytest.approx(0.0)


def test_same_pack_used_grants_06(scorer, consistency_summary_factory):
    summary = consistency_summary_factory(pack_uses={1: 3}, vendor_uses={"kenney": 3})
    pack = _pack_row(pack_id=1, vendor="kenney")
    result = scorer.score_pack(
        project_id=99, pack=pack, summary=summary,
        blocked_packs=set(), pinned_pack_id=None,
    )
    assert result.score >= 0.6


def test_same_vendor_different_pack_grants_03(scorer, consistency_summary_factory):
    summary = consistency_summary_factory(pack_uses={1: 3}, vendor_uses={"kenney": 3})
    pack = _pack_row(pack_id=2, vendor="kenney")  # different pack, same vendor
    result = scorer.score_pack(
        project_id=99, pack=pack, summary=summary,
        blocked_packs=set(), pinned_pack_id=None,
    )
    # +0.3 (vendor) only — no same_pack, no style, no palette
    assert 0.25 <= result.score <= 0.35


def test_style_match_adds_02(scorer, consistency_summary_factory, populated_store):
    store, ids = populated_store
    summary = consistency_summary_factory(
        pack_uses={ids["pack_a"]: 3}, vendor_uses={"kenney": 3},
        dominant_style="pixel_art", dominant_palette=["#aa1122", "#22aa11", "#1122aa"],
    )
    # Compare against a brand-new pack that shares the style.
    pack = _pack_row(pack_id=99, vendor="other")
    result = scorer.score_asset(
        project_id=1, asset=None, pack_aggregate=_pack_aggregate("pixel_art"),
        summary=summary, blocked_packs=set(), pinned_pack_id=None, pack=pack,
    )
    # +0.2 (style) + +0.1 (palette close) — but neither same pack nor vendor
    assert 0.25 <= result.score <= 0.40


def test_palette_close_under_threshold_adds_01(scorer, consistency_summary_factory):
    summary = consistency_summary_factory(
        pack_uses={1: 3}, vendor_uses={"v": 3},
        dominant_style="vector_cartoon",
        dominant_palette=["#ffffff", "#000000", "#888888"],
    )
    pack = _pack_row(pack_id=2, vendor="other")
    # Same palette family (Δ small) but different style.
    result = scorer.score_asset(
        project_id=1, asset=None,
        pack_aggregate=_pack_aggregate(
            "vector_cartoon", ["#fefefe", "#010101", "#878787"]
        ),
        summary=summary, blocked_packs=set(), pinned_pack_id=None, pack=pack,
    )
    # +0.2 style + +0.1 palette = 0.3 (no vendor, no same pack)
    assert result.score >= 0.25


def test_palette_far_above_threshold_no_bonus(scorer, consistency_summary_factory):
    summary = consistency_summary_factory(
        pack_uses={1: 3}, vendor_uses={"v": 3},
        dominant_style="vector_cartoon",
        dominant_palette=["#ffffff", "#000000", "#888888"],
    )
    pack = _pack_row(pack_id=2, vendor="other")
    # Wildly different palette.
    result = scorer.score_asset(
        project_id=1, asset=None,
        pack_aggregate=_pack_aggregate(
            "different_style", ["#ff00ff", "#00ffff", "#ffff00"]
        ),
        summary=summary, blocked_packs=set(), pinned_pack_id=None, pack=pack,
    )
    assert result.score < 0.2  # no style, no palette → could even be locked penalty


def test_locked_project_with_foreign_pack_gets_minus_02(scorer, consistency_summary_factory):
    # distinct=1, uses=5 → locked under default threshold (max_packs=2, min_uses=5)
    summary = consistency_summary_factory(
        pack_uses={1: 5}, vendor_uses={"kenney": 5}, dominant_style="pixel_art",
    )
    pack = _pack_row(pack_id=99, vendor="other")  # foreign vendor + foreign pack
    result = scorer.score_pack(
        project_id=1, pack=pack, summary=summary,
        blocked_packs=set(), pinned_pack_id=None,
    )
    # No bonuses, and -0.2 penalty (clamped at 0)
    assert result.score == pytest.approx(0.0)
    assert any(name == "locked_penalty" for name, _ in result.signals)


def test_pinned_pack_short_circuits_to_one(scorer, consistency_summary_factory):
    summary = consistency_summary_factory()
    pack = _pack_row(pack_id=42)
    result = scorer.score_pack(
        project_id=1, pack=pack, summary=summary,
        blocked_packs=set(), pinned_pack_id=42,
    )
    assert result.score == pytest.approx(1.0)


def test_blocked_pack_short_circuits_to_zero(scorer, consistency_summary_factory):
    summary = consistency_summary_factory(pack_uses={42: 10}, vendor_uses={"kenney": 10})
    pack = _pack_row(pack_id=42, vendor="kenney")
    result = scorer.score_pack(
        project_id=1, pack=pack, summary=summary,
        blocked_packs={42}, pinned_pack_id=None,
    )
    assert result.score == pytest.approx(0.0)


def test_score_clamps_to_zero_one_range(scorer, consistency_summary_factory):
    summary = consistency_summary_factory(
        pack_uses={1: 50}, vendor_uses={"kenney": 50}, dominant_style="pixel_art",
        dominant_palette=["#aa1122", "#22aa11", "#1122aa"],
    )
    pack = _pack_row(pack_id=1, vendor="kenney")
    result = scorer.score_pack(
        project_id=1, pack=pack, summary=summary,
        blocked_packs=set(), pinned_pack_id=None,
    )
    assert 0.0 <= result.score <= 1.0


def test_is_locked_threshold_exactly_at_min_uses(scorer, consistency_summary_factory):
    just_below = consistency_summary_factory(pack_uses={1: 4})
    just_at = consistency_summary_factory(pack_uses={1: 5})
    assert scorer.is_locked(just_below) is False
    assert scorer.is_locked(just_at) is True


def test_format_why_includes_use_count_korean(scorer, consistency_summary_factory):
    summary = consistency_summary_factory(pack_uses={7: 12}, vendor_uses={"kenney": 12})
    pack = _pack_row(pack_id=7, vendor="kenney")
    result = scorer.score_pack(
        project_id=1, pack=pack, summary=summary,
        blocked_packs=set(), pinned_pack_id=None,
    )
    why = scorer.format_why(result, "Kenney Platformer")
    assert "12" in why
    assert "Kenney Platformer" in why
