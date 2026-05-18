"""M5 Phase 4C — request_user_pick MCP 도구 유닛 테스트.

Task 4.7 / 4.8 / 4.9 를 커버 (10 케이스).
respx 로 httpx 호출을 모킹하므로 실제 서버가 필요 없다.
"""

from __future__ import annotations

import httpx
import pytest
import respx


# ── 헬퍼 픽스처 ─────────────────────────────────────────────────────────


@pytest.fixture
def pick_deps(populated_store, fake_embedder, tmp_path):
    """web.port 파일이 미리 쓰여진 AppPaths + 실 Store 를 가진 ToolDeps.

    ``port=9874`` 를 가리키는 ``web.port`` 파일을 tmp_path 에 미리 만들어둔다.
    httpx 는 respx 로 모킹되므로 실제 연결은 일어나지 않는다.
    """
    from gah.config import AppPaths, Config
    from gah.core.consistency import ConsistencyScorer
    from gah.core.labels import LabelRegistry
    from gah.core.search import HybridSearcher
    from gah.core.usage_tracker import UsageTracker
    from gah.mcp.tools import ToolDeps
    from gah.web.url import write_web_port

    store, _ids = populated_store
    config = Config()
    registry = LabelRegistry(store)
    registry.bootstrap()
    consistency = ConsistencyScorer(store, config)
    usage = UsageTracker(store, config)
    search = HybridSearcher(store, fake_embedder, consistency, registry, config)

    # tmp_path 를 data_dir 로 쓰는 가짜 AppPaths
    paths = AppPaths(
        data_dir=tmp_path,
        config_path=tmp_path / "config.toml",
        db_path=tmp_path / "gah.db",
        log_path=tmp_path / "gah.log",
        lock_path=tmp_path / "gah.lock",
        cache_dir=tmp_path / "cache",
        library_dir=tmp_path / "library",
    )
    write_web_port(tmp_path, 9874)

    deps = ToolDeps(
        store=store,
        search=search,
        usage=usage,
        registry=registry,
        queue=None,
        config=config,
        paths=paths,
    )
    return deps, store, _ids


@pytest.fixture
def no_port_deps(populated_store, fake_embedder, tmp_path):
    """web.port 파일이 없는 ToolDeps (503 케이스 전용)."""
    from gah.config import AppPaths, Config
    from gah.core.consistency import ConsistencyScorer
    from gah.core.labels import LabelRegistry
    from gah.core.search import HybridSearcher
    from gah.core.usage_tracker import UsageTracker
    from gah.mcp.tools import ToolDeps

    store, _ids = populated_store
    config = Config()
    registry = LabelRegistry(store)
    registry.bootstrap()
    consistency = ConsistencyScorer(store, config)
    usage = UsageTracker(store, config)
    search = HybridSearcher(store, fake_embedder, consistency, registry, config)

    paths = AppPaths(
        data_dir=tmp_path,  # web.port 를 쓰지 않음
        config_path=tmp_path / "config.toml",
        db_path=tmp_path / "gah.db",
        log_path=tmp_path / "gah.log",
        lock_path=tmp_path / "gah.lock",
        cache_dir=tmp_path / "cache",
        library_dir=tmp_path / "library",
    )

    deps = ToolDeps(
        store=store,
        search=search,
        usage=usage,
        registry=registry,
        queue=None,
        config=config,
        paths=paths,
    )
    return deps


# ── 테스트 10개 ─────────────────────────────────────────────────────────


def test_no_paths_raises_503(populated_store, fake_embedder):
    """Task 4.9 — ToolDeps.paths=None 이면 503_no_ui_available."""
    from gah.config import Config
    from gah.core.consistency import ConsistencyScorer
    from gah.core.labels import LabelRegistry
    from gah.core.search import HybridSearcher
    from gah.core.usage_tracker import UsageTracker
    from gah.mcp.models import RequestUserPickRequest
    from gah.mcp.tools import McpToolError, ToolDeps, tool_request_user_pick

    store, _ = populated_store
    config = Config()
    registry = LabelRegistry(store)
    registry.bootstrap()
    consistency = ConsistencyScorer(store, config)
    usage = UsageTracker(store, config)
    search = HybridSearcher(store, fake_embedder, consistency, registry, config)

    deps = ToolDeps(
        store=store, search=search, usage=usage,
        registry=registry, queue=None, config=config, paths=None,
    )
    req = RequestUserPickRequest(candidates=[1])
    with pytest.raises(McpToolError) as exc_info:
        tool_request_user_pick(deps, req)
    assert exc_info.value.code == "503_no_ui_available"


def test_no_web_port_file_raises_503(no_port_deps):
    """Task 4.9 — data_dir 에 web.port 파일이 없으면 503_no_ui_available."""
    from gah.mcp.models import RequestUserPickRequest
    from gah.mcp.tools import McpToolError, tool_request_user_pick

    req = RequestUserPickRequest(candidates=[1])
    with pytest.raises(McpToolError) as exc_info:
        tool_request_user_pick(no_port_deps, req)
    assert exc_info.value.code == "503_no_ui_available"


def test_connect_error_raises_503(pick_deps):
    """Task 4.8 — 포트 파일은 있지만 서버가 응답 없음 → 503_no_ui_available."""
    from gah.mcp.models import RequestUserPickRequest
    from gah.mcp.tools import McpToolError, tool_request_user_pick

    deps, _store, _ids = pick_deps
    req = RequestUserPickRequest(candidates=[1])

    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.post("http://127.0.0.1:9874/internal/user-pick").mock(
            side_effect=httpx.ConnectError("연결 거부")
        )
        with pytest.raises(McpToolError) as exc_info:
            tool_request_user_pick(deps, req)
    assert exc_info.value.code == "503_no_ui_available"


def test_success_200_returns_result(pick_deps):
    """Task 4.8 — 200 응답 → RequestUserPickResult 정상 반환."""
    from gah.mcp.models import RequestUserPickRequest, RequestUserPickResult
    from gah.mcp.tools import tool_request_user_pick

    deps, _store, _ids = pick_deps
    req = RequestUserPickRequest(candidates=[1, 2])

    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.post("http://127.0.0.1:9874/internal/user-pick").mock(
            return_value=httpx.Response(
                200,
                json={"picked_asset_id": 1, "picked_at": 1700000000, "user_note": None},
            )
        )
        result = tool_request_user_pick(deps, req)

    assert isinstance(result, RequestUserPickResult)
    assert result.picked_asset_id == 1
    assert result.picked_at == 1700000000
    assert result.user_note is None


def test_408_timeout(pick_deps):
    """Task 4.8 — 408 응답 → McpToolError 408_timeout."""
    from gah.mcp.models import RequestUserPickRequest
    from gah.mcp.tools import McpToolError, tool_request_user_pick

    deps, _store, _ids = pick_deps
    req = RequestUserPickRequest(candidates=[1])

    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.post("http://127.0.0.1:9874/internal/user-pick").mock(
            return_value=httpx.Response(408)
        )
        with pytest.raises(McpToolError) as exc_info:
            tool_request_user_pick(deps, req)
    assert exc_info.value.code == "408_timeout"


def test_499_user_cancelled(pick_deps):
    """Task 4.8 — 499 응답 → McpToolError 499_user_cancelled."""
    from gah.mcp.models import RequestUserPickRequest
    from gah.mcp.tools import McpToolError, tool_request_user_pick

    deps, _store, _ids = pick_deps
    req = RequestUserPickRequest(candidates=[1])

    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.post("http://127.0.0.1:9874/internal/user-pick").mock(
            return_value=httpx.Response(499)
        )
        with pytest.raises(McpToolError) as exc_info:
            tool_request_user_pick(deps, req)
    assert exc_info.value.code == "499_user_cancelled"


def test_503_too_many_pending(pick_deps):
    """Task 4.8 — 503 응답 → McpToolError 503_too_many_pending."""
    from gah.mcp.models import RequestUserPickRequest
    from gah.mcp.tools import McpToolError, tool_request_user_pick

    deps, _store, _ids = pick_deps
    req = RequestUserPickRequest(candidates=[1])

    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.post("http://127.0.0.1:9874/internal/user-pick").mock(
            return_value=httpx.Response(503)
        )
        with pytest.raises(McpToolError) as exc_info:
            tool_request_user_pick(deps, req)
    assert exc_info.value.code == "503_too_many_pending"


def test_auto_record_asset_use_skipped_when_no_project_id(pick_deps):
    """Task 4.8 — project_id=None 이면 record_asset_use 를 스킵 (DB 행 없음)."""
    from gah.mcp.models import RequestUserPickRequest
    from gah.mcp.tools import tool_request_user_pick

    deps, store, _ids = pick_deps
    req = RequestUserPickRequest(candidates=[1], project_id=None)

    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.post("http://127.0.0.1:9874/internal/user-pick").mock(
            return_value=httpx.Response(
                200,
                json={"picked_asset_id": 1, "picked_at": 1700000001, "user_note": None},
            )
        )
        result = tool_request_user_pick(deps, req)

    assert result.picked_asset_id == 1
    n = store.conn.execute(
        "SELECT COUNT(*) FROM asset_usage"
    ).fetchone()[0]
    assert n == 0


def test_auto_record_asset_use_inserts_with_claude_pick_source(pick_deps):
    """Task 4.8 — project_id 있고 200 응답 → source='claude_pick' 행 삽입."""
    from gah.mcp.models import RequestUserPickRequest
    from gah.mcp.tools import tool_request_user_pick

    deps, store, ids = pick_deps
    hero_id = ids["hero"]
    req = RequestUserPickRequest(
        candidates=[hero_id],
        project_id="D:/MyGame",
        reason="hero 스프라이트 필요",
    )

    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.post("http://127.0.0.1:9874/internal/user-pick").mock(
            return_value=httpx.Response(
                200,
                json={
                    "picked_asset_id": hero_id,
                    "picked_at": 1700000002,
                    "user_note": "마음에 듦",
                },
            )
        )
        result = tool_request_user_pick(deps, req)

    assert result.picked_asset_id == hero_id

    row = store.conn.execute(
        "SELECT source, asset_id FROM asset_usage WHERE source='claude_pick'"
    ).fetchone()
    assert row is not None, "claude_pick source 행이 없음"
    assert row[1] == hero_id


def test_request_user_pick_model_signature():
    """Task 4.7 — Pydantic 모델 유효성: 후보 없음/초과/타임아웃 범위 검증."""
    from pydantic import ValidationError

    from gah.mcp.models import RequestUserPickRequest

    # 후보 0개 (min_length=1 위반)
    with pytest.raises(ValidationError):
        RequestUserPickRequest(candidates=[])

    # 후보 11개 (max_length=10 위반)
    with pytest.raises(ValidationError):
        RequestUserPickRequest(candidates=list(range(11)))

    # 타임아웃 범위 이하 (ge=10 위반)
    with pytest.raises(ValidationError):
        RequestUserPickRequest(candidates=[1], timeout_seconds=5)

    # 타임아웃 범위 초과 (le=1800 위반)
    with pytest.raises(ValidationError):
        RequestUserPickRequest(candidates=[1], timeout_seconds=9999)

    # 정상 케이스
    req = RequestUserPickRequest(candidates=[1, 2, 3])
    assert len(req.candidates) == 3
    assert req.timeout_seconds == 300  # 기본값
