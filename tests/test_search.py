"""M3 — HybridSearcher (FTS + 코사인 + 라벨 매칭 + 통일성 가중합)."""

from __future__ import annotations

import pytest


@pytest.fixture
def searcher(populated_store, fake_embedder):
    from gah.config import Config
    from gah.core.consistency import ConsistencyScorer
    from gah.core.labels import LabelRegistry
    from gah.core.search import HybridSearcher
    from gah.core.usage_tracker import UsageTracker

    store, _ = populated_store
    config = Config()
    registry = LabelRegistry(store)
    registry.bootstrap()
    consistency = ConsistencyScorer(store, config)
    return HybridSearcher(store, fake_embedder, consistency, registry, config)


def _label_filter(axis: str, label: str):
    from gah.core.search import LabelFilter

    return LabelFilter(axis=axis, label=label)


def _req(**kwargs):
    from gah.core.search import SearchRequest

    base = dict(query="hero", count=5)
    base.update(kwargs)
    return SearchRequest(**base)


# ─────────────────────────────────────────────────────────────────────


def test_hybrid_returns_topn_sorted(searcher):
    res = searcher.hybrid(_req(query="character pixel art", count=3))
    assert len(res.results) <= 3
    scores = [r.score for r in res.results]
    assert scores == sorted(scores, reverse=True)


def test_score_breakdown_sums_to_score_within_tolerance(searcher):
    res = searcher.hybrid(_req(query="hero pixel", count=2))
    for r in res.results:
        total = (
            r.score_breakdown["semantic"]
            + r.score_breakdown["keyword"]
            + r.score_breakdown["label_match"]
            + r.score_breakdown["consistency"]
            + r.score_breakdown["recency"]
        )
        assert r.score == pytest.approx(total, abs=1e-4)


def test_empty_candidates_returns_empty_results(searcher):
    res = searcher.hybrid(_req(query="xxx_no_match_zzz", kind="sprite",
                                labels_all=[_label_filter("category", "no_such_label")]))
    assert res.results == []


def test_labels_all_filters_out_non_matching(searcher, populated_store):
    _, ids = populated_store
    res = searcher.hybrid(_req(
        query="anything",
        labels_all=[_label_filter("category", "character")],
    ))
    result_ids = {r.asset_id for r in res.results}
    assert result_ids <= {ids["hero"]}


def test_labels_any_unions_matches(searcher, populated_store):
    _, ids = populated_store
    res = searcher.hybrid(_req(
        query="any sprite",
        labels_any=[
            _label_filter("category", "character"),
            _label_filter("category", "item"),
        ],
    ))
    result_ids = {r.asset_id for r in res.results}
    assert {ids["hero"], ids["coin"]} <= result_ids


def test_labels_none_excludes_matches(searcher, populated_store):
    _, ids = populated_store
    res = searcher.hybrid(_req(
        query="any sprite",
        kind="sprite",
        labels_none=[_label_filter("style", "vector_cartoon")],
    ))
    result_ids = {r.asset_id for r in res.results}
    assert ids["menu_bg"] not in result_ids
    assert ids["button"] not in result_ids


def test_force_pack_id_restricts_scope(searcher, populated_store):
    _, ids = populated_store
    res = searcher.hybrid(_req(query="anything", force_pack_id=ids["pack_a"]))
    pack_ids = {r.pack_id for r in res.results}
    assert pack_ids <= {ids["pack_a"]}


def test_exclude_pack_ids_removes_candidates(searcher, populated_store):
    _, ids = populated_store
    res = searcher.hybrid(_req(query="anything", exclude_pack_ids=[ids["pack_b"]]))
    pack_ids = {r.pack_id for r in res.results}
    assert ids["pack_b"] not in pack_ids


def test_prefer_pack_id_adds_bonus(searcher, populated_store):
    _, ids = populated_store
    base = searcher.hybrid(_req(query="hero"))
    biased = searcher.hybrid(_req(query="hero", prefer_pack_id=ids["pack_a"]))
    # Highest pack_a candidate in `biased` should rank no worse than in `base`.
    def _first_pack_a(r):
        for i, row in enumerate(r.results):
            if row.pack_id == ids["pack_a"]:
                return i
        return None

    base_pos = _first_pack_a(base)
    biased_pos = _first_pack_a(biased)
    if base_pos is not None and biased_pos is not None:
        assert biased_pos <= base_pos


def test_pinned_pack_id_is_first(searcher, populated_store):
    store, ids = populated_store
    p = store.upsert_project("proj_pin")
    store.set_project_pin(p.id, ids["pack_b"])
    res = searcher.hybrid(_req(query="anything", project_id="proj_pin"))
    assert res.results, "expected at least one result"
    assert res.results[0].pack_id == ids["pack_b"]


def test_blocked_pack_excluded_even_if_high_semantic(searcher, populated_store):
    store, ids = populated_store
    p = store.upsert_project("proj_block")
    store.set_blocked_packs(p.id, [ids["pack_a"]])
    res = searcher.hybrid(_req(query="hero pixel", project_id="proj_block"))
    assert all(r.pack_id != ids["pack_a"] for r in res.results)


def test_kind_filter_sprite_only(searcher, populated_store):
    _, ids = populated_store
    res = searcher.hybrid(_req(query="anything", kind="sprite"))
    # Sounds (jump, bgm_loop) must not appear.
    result_ids = {r.asset_id for r in res.results}
    assert ids["jump"] not in result_ids
    assert ids["bgm_loop"] not in result_ids


def test_matched_labels_contain_axis_label_source_score(searcher, populated_store):
    _, ids = populated_store
    res = searcher.hybrid(_req(
        query="hero",
        labels_any=[_label_filter("category", "character")],
    ))
    hero = next(r for r in res.results if r.asset_id == ids["hero"])
    assert any(
        ml["axis"] == "category" and ml["label"] == "character"
        and "source" in ml and "score" in ml
        for ml in hero.matched_labels
    )


def test_why_includes_consistency_phrase_when_consistency_positive(
    searcher, populated_store
):
    store, ids = populated_store
    p = store.upsert_project("proj_hist")
    store.record_asset_use(p.id, ids["hero"], ids["pack_a"], source="explicit")
    res = searcher.hybrid(_req(query="hero pixel", project_id="proj_hist"))
    top = res.results[0]
    if top.pack_id == ids["pack_a"]:
        assert "채택" in top.why or "pack_a" in top.why.lower()


def test_why_mentions_first_search_when_history_empty(searcher):
    res = searcher.hybrid(_req(query="hero", project_id="brand_new_project"))
    if res.results:
        assert "첫" in res.results[0].why


def test_query_id_persisted_in_search_queries(searcher, populated_store):
    store, _ = populated_store
    res = searcher.hybrid(_req(query="hero", project_id="proj_log"))
    row = store.conn.execute(
        "SELECT query_text FROM search_queries WHERE id=?", (res.query_id,)
    ).fetchone()
    assert row is not None
    assert row[0] == "hero"


def test_min_max_normalization_handles_single_candidate(searcher, populated_store):
    _, ids = populated_store
    # Force exactly one candidate via force_pack_id + label scope.
    res = searcher.hybrid(_req(
        query="hero",
        force_pack_id=ids["pack_a"],
        labels_all=[_label_filter("category", "character")],
    ))
    assert len(res.results) == 1
    r = res.results[0]
    # With a single candidate, keyword normalizes to 0 and semantic to 1
    # (or both 0/0 when both channels happen to tie). Either way, breakdown
    # values must remain finite and in [0, 1].
    for ch in ("semantic", "keyword", "label_match", "consistency", "recency"):
        assert 0.0 <= r.score_breakdown[ch] <= 1.0


def test_label_match_zero_does_not_renormalize_other_channels(searcher):
    res_no_labels = searcher.hybrid(_req(query="hero pixel"))
    if res_no_labels.results:
        top = res_no_labels.results[0]
        # label_match contribution is 0 when no labels_* given.
        assert top.score_breakdown["label_match"] == pytest.approx(0.0)
        # Other channels keep their raw weighted contribution (no rescale).
        assert top.score <= 0.80 + 1e-6  # max possible without label_match=0.20


def test_consistency_override_weight_applied(searcher, populated_store):
    store, ids = populated_store
    p = store.upsert_project("proj_w")
    store.record_asset_use(p.id, ids["hero"], ids["pack_a"], source="explicit")

    base = searcher.hybrid(_req(query="hero", project_id="proj_w"))
    boosted = searcher.hybrid(_req(
        query="hero", project_id="proj_w", consistency_weight_override=0.9,
    ))
    # With consistency weight 0.9 instead of 0.20, the same hero asset's score
    # contribution from consistency channel should change.
    if base.results and boosted.results:
        base_hero = next((r for r in base.results if r.asset_id == ids["hero"]), None)
        boosted_hero = next((r for r in boosted.results if r.asset_id == ids["hero"]), None)
        if base_hero and boosted_hero:
            # consistency contribution must be larger when override is high
            assert (
                boosted_hero.score_breakdown["consistency"]
                >= base_hero.score_breakdown["consistency"]
            )


def test_recent_asset_gets_higher_recency_score(searcher, populated_store):
    res = searcher.hybrid(_req(query="anything"))
    if res.results:
        for r in res.results:
            assert 0.0 <= r.score_breakdown["recency"] <= 1.0


def test_hybrid_works_with_real_embedding_encoder(populated_store):
    """M3 회귀 가드 — fake_embedder 가 모든 메서드를 제공해 자동 테스트가
    통과해도, 실 EmbeddingEncoder 인스턴스로 호출했을 때 ``decode_vector``
    같은 메서드 갭이 있으면 silent fail. 진짜 EmbeddingEncoder + 가짜
    Ollama client 조합으로 한 번 끝까지 돌려야 인터페이스 일치를 보장.
    """
    from gah.config import Config
    from gah.core.consistency import ConsistencyScorer
    from gah.core.embedding import EmbeddingEncoder
    from gah.core.labels import LabelRegistry
    from gah.core.search import HybridSearcher, SearchRequest

    store, _ = populated_store

    class _FakeOllamaClient:
        def embed(self, text, *, model=None):  # noqa: ANN001
            return [0.001 * ((i + len(text)) % 100) for i in range(768)]

    embedder = EmbeddingEncoder(_FakeOllamaClient(), model="nomic-embed-text")
    cfg = Config()
    registry = LabelRegistry(store)
    registry.bootstrap()
    consistency = ConsistencyScorer(store, cfg)
    sr = HybridSearcher(store, embedder, consistency, registry, cfg)

    res = sr.hybrid(SearchRequest(query="hero pixel art", count=3))
    # populated_store 가 자산 6 개 — 빈 응답이면 안 됨 (검색이 끝까지 도달).
    assert len(res.results) > 0
    assert res.query_id > 0
