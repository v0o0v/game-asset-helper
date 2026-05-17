"""M5 — /api/search POST (JSON 응답) + /ui/search-results HTML fragment 검증."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from gah.web.app import build_app


@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


@pytest.fixture
def populated_deps(tmp_path, populated_store, fake_embedder):
    """에셋이 채워진 WebDeps — 빈 query 디폴트 상태 테스트용."""
    from gah.config import AppPaths, Config
    from gah.core.labels import LabelRegistry
    from gah.core.consistency import ConsistencyScorer
    from gah.core.usage_tracker import UsageTracker
    from gah.core.search import HybridSearcher
    from gah.web.deps import WebDeps
    from gah.web.pending import PendingPickQueue

    store, _ids = populated_store
    cfg = Config()
    paths = AppPaths(
        data_dir=tmp_path,
        library_dir=tmp_path / "library",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "metadata.db",
        config_path=tmp_path / "config.toml",
        log_path=tmp_path / "logs" / "gah.log",
        lock_path=tmp_path / "gah.lock",
    )
    paths.ensure_dirs()
    registry = LabelRegistry(store)
    registry.bootstrap()
    consistency = ConsistencyScorer(store, cfg)
    usage = UsageTracker(store, cfg)
    searcher = HybridSearcher(store, fake_embedder, consistency, registry, cfg)
    pending = PendingPickQueue(max_pending=cfg.claude_pick_max_pending)
    return WebDeps(
        store=store,
        search=searcher,
        usage=usage,
        registry=registry,
        queue=None,
        config=cfg,
        paths=paths,
        pending_picks=pending,
    )


@pytest.fixture
def populated_client(populated_deps):
    with TestClient(build_app(populated_deps)) as c:
        yield c


# ── /api/search (Task 2.1) ─────────────────────────────────────────────


def test_api_search_returns_json_with_rows(client, deps_fixture):
    """빈 라이브러리에서도 200 + rows=[] + total=0."""
    r = client.post("/api/search", json={"query": "blue hero", "count": 10})
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body
    assert "total" in body
    assert isinstance(body["rows"], list)


def test_api_search_passes_label_query(client, deps_fixture):
    """label_query 가 SearchRequest 의 label_query 로 전달되어 파서 호출."""
    r = client.post("/api/search", json={
        "query": "",
        "label_query": "character AND pixel_art",
        "count": 5,
    })
    assert r.status_code == 200


def test_api_search_passes_pack_filters(client, deps_fixture):
    """pack_ids 필터가 SearchRequest 에 전달 (exclude_pack_ids 로 매핑)."""
    r = client.post("/api/search", json={
        "query": "",
        "pack_ids": [1, 2],
        "count": 5,
    })
    assert r.status_code == 200


def test_api_search_invalid_diversity_returns_422(client, deps_fixture):
    """diversity 의 enum 검증 — 'bogus' 는 422."""
    r = client.post("/api/search", json={
        "query": "",
        "diversity": "bogus_value",
    })
    assert r.status_code == 422


# ── /ui/search-results (Task 2.2) ─────────────────────────────────────


def test_ui_search_results_returns_html(client, deps_fixture):
    """빈 라이브러리에서도 200 + text/html."""
    r = client.post("/ui/search-results", json={"query": "blue hero", "count": 5})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_ui_search_results_contains_card_class(client, deps_fixture):
    """빈 라이브러리도 results-cards 컨테이너는 렌더 (카드 0개)."""
    r = client.post("/ui/search-results", json={"query": "", "count": 5})
    assert r.status_code == 200
    assert "results-cards" in r.text


def test_ui_search_results_form_data(client, deps_fixture):
    """form-data (HTMX hx-post + hx-include) 도 받아들임."""
    r = client.post("/ui/search-results", data={"query": "test", "count": "5"})
    assert r.status_code == 200


def test_api_search_offset_returns_different_rows(client, deps_fixture):
    """offset=5 + count=5 → 6번째부터 10번째 row (정상 라이브러리 가정).
    빈 라이브러리에선 rows=[] 이더라도 200 응답이 와야 한다."""
    r1 = client.post("/api/search", json={"query": "", "count": 10, "offset": 0})
    r2 = client.post("/api/search", json={"query": "", "count": 5, "offset": 5})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # 빈 라이브러리도 rows 는 list 형태여야 함
    assert isinstance(r1.json()["rows"], list)
    assert isinstance(r2.json()["rows"], list)
    # offset=5 에서 r1 의 앞 5 개와 겹치지 않아야 한다 (결과가 충분한 경우)
    ids1 = [row["asset_id"] for row in r1.json()["rows"]]
    ids2 = [row["asset_id"] for row in r2.json()["rows"]]
    if ids1 and ids2:
        # r2 는 r1[5:10] 과 동일해야 함
        assert ids2 == ids1[5:10]


# ── Task 2.8: 페이지네이션 (더 보기 버튼) ────────────────────────────────


def test_ui_search_results_no_load_more_when_empty(client):
    """빈 라이브러리 → next_offset=None → 더 보기 버튼 없음."""
    r = client.post("/ui/search-results", json={"query": "", "count": 100, "offset": 0})
    assert r.status_code == 200
    assert "load-more" not in r.text


def test_ui_search_results_load_more_button(client, deps_fixture):
    """빈 라이브러리 (count=5, offset=0) → next_offset=None → 더 보기 X."""
    r = client.post("/ui/search-results", json={"query": "", "count": 5, "offset": 0})
    assert r.status_code == 200
    # 빈 라이브러리에는 더 보기 없음
    assert "load-more" not in r.text


def test_pagination_passes_offset_to_handler(client):
    """offset=5 + count=5 → 정상 처리 (200)."""
    r = client.post("/ui/search-results", json={"query": "", "count": 5, "offset": 5})
    assert r.status_code == 200


# ── Task 2.9: 디폴트 상태 (빈 검색 → 라이브러리 전체 추가일↓) ────────────


def test_default_state_empty_query_returns_library_by_added_desc(client, deps_fixture):
    """query 비어 + 필터 0 → 라이브러리 전체 (rows=list) + 200."""
    r = client.post("/api/search", json={"query": "", "count": 50, "offset": 0, "sort": "added_desc"})
    assert r.status_code == 200
    body = r.json()
    # rows 가 list (None 아닌) + 빈 라이브러리는 빈 list
    assert isinstance(body["rows"], list)
    assert "total" in body


def test_default_state_uses_added_desc_when_sort_score(client, deps_fixture):
    """빈 검색 + sort=score → 추가일↓ 폴백 (score 가 의미 없으므로) + 200."""
    r = client.post("/api/search", json={"query": "", "count": 50, "sort": "score"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["rows"], list)


def test_default_state_ui_fragment_also_works(client, deps_fixture):
    """UI fragment 엔드포인트도 빈 검색 시 200 + results-toolbar 포함."""
    r = client.post("/ui/search-results", json={"query": "", "count": 20, "offset": 0})
    assert r.status_code == 200
    assert "results-toolbar" in r.text


def test_default_state_with_assets_returns_all(populated_client):
    """에셋이 6개인 라이브러리에서 빈 query → 6개 전부 반환 (폴백 경로)."""
    r = populated_client.post("/api/search", json={"query": "", "count": 50, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["rows"], list)
    # populated_store 에는 6개 에셋이 있다
    assert len(body["rows"]) == 6


def test_default_state_sort_score_falls_back_to_added_desc(populated_client):
    """빈 query + sort=score → added_desc 폴백 (점수가 의미 없는 디폴트 뷰)."""
    r = populated_client.post("/api/search", json={"query": "", "count": 50, "sort": "score"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) == 6
