"""M5 — Ollama 미가용 시 graceful degradation 회귀 테스트.

- ui_search_results: OllamaError → 200 + 친화 메시지 fragment
- api_search: OllamaError → 503 + {"code": "503_ollama_unavailable"}
- 빈 query: _list_all_assets 폴백이라 Ollama 무관하게 200 + 정상 결과
"""
from __future__ import annotations

import pytest


# ── 케이스 1: /ui/search-results — OllamaError → 200 + 친화 fragment ─────────


def test_ui_search_results_returns_error_fragment_when_ollama_down(
    populated_client, populated_deps, monkeypatch
):
    """HybridSearcher.hybrid 가 OllamaError 를 던지면
    /ui/search-results 는 200 + 검색 실패 친화 메시지를 반환한다."""
    from gah.core.ollama_client import OllamaError

    def _fake_hybrid(sr):
        raise OllamaError(
            stage="embed", path="native", cause=ConnectionError("connection refused")
        )

    monkeypatch.setattr(populated_deps.search, "hybrid", _fake_hybrid)
    r = populated_client.post(
        "/ui/search-results",
        data={"query": "blue hero", "count": "5", "offset": "0", "sort": "added_desc"},
    )
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "검색 서비스를 사용할 수 없습니다" in r.text


# ── 케이스 2: /api/search — OllamaError → 503 + JSON ────────────────────────


def test_api_search_returns_503_when_ollama_down(
    populated_client, populated_deps, monkeypatch
):
    """HybridSearcher.hybrid 가 OllamaError 를 던지면
    /api/search 는 503 + code=503_ollama_unavailable JSON 을 반환한다."""
    from gah.core.ollama_client import OllamaError

    def _fake_hybrid(sr):
        raise OllamaError(stage="embed", path="native")

    monkeypatch.setattr(populated_deps.search, "hybrid", _fake_hybrid)
    r = populated_client.post(
        "/api/search", json={"query": "blue hero", "count": 5}
    )
    assert r.status_code == 503
    body = r.json()
    assert body["detail"]["code"] == "503_ollama_unavailable"
    assert "message" in body["detail"]


# ── 케이스 3: 빈 query → _list_all_assets 폴백 — Ollama 무관하게 정상 ────────


def test_empty_query_still_works_when_ollama_down(
    populated_client, populated_deps, monkeypatch
):
    """빈 query 는 _list_all_assets 폴백 경로라 OllamaError 가 발생해도
    /ui/search-results 가 200 + 정상 결과 그리드를 반환한다."""
    from gah.core.ollama_client import OllamaError

    def _fake_hybrid(sr):
        raise OllamaError(stage="embed", path="native")

    monkeypatch.setattr(populated_deps.search, "hybrid", _fake_hybrid)
    r = populated_client.post(
        "/ui/search-results",
        data={"query": "", "count": "20", "offset": "0", "sort": "added_desc"},
    )
    assert r.status_code == 200
    # 정상 그리드 — 결과 toolbar 포함, 에러 fragment 아님
    assert "results-toolbar" in r.text
    assert "검색 서비스를 사용할 수 없습니다" not in r.text
