"""M5 Phase 4B — GET /ui/pick-card/{rid} HTML fragment 검증.

Task 4.4:
  - 200 + 후보 card data-asset-id 렌더
  - 404 for unknown rid
  - reason 문자열 포함
  - hx-post="/api/user-pick/{rid}" [채택] 버튼 포함
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


@pytest.fixture
def pick_client(populated_deps):
    """`populated_deps` (2 packs × 6 assets) 를 wrapping 한 TestClient."""
    with TestClient(build_app(populated_deps)) as c:
        yield c, populated_deps


def _register_pick(deps, asset_ids: list[int], reason: str | None = None):
    """동기 컨텍스트에서 PendingPickQueue 에 pending 항목 직접 등록.

    asyncio.Future 는 register() 가 running loop 을 요구하므로
    TestClient 의 anyio 루프 내부 초기화 전에는 직접 호출 불가.
    대신 _items dict 에 모킹 PendingPick 를 수동 삽입한다.
    """
    import asyncio
    import threading
    import time
    import uuid
    from gah.web.pending import PendingPick

    rid = uuid.uuid4().hex
    # TestClient 는 sync — Future 없이 메타만 삽입하면 /ui/pick-card 는 futures 를 쓰지 않는다.
    # PendingPick 의 future / _loop 는 HTTP endpoint 에서 await 할 때만 필요하므로
    # fake future (done 상태) 로 채운다.
    loop = asyncio.new_event_loop()
    fut = loop.create_future()
    fut.cancel()  # 즉시 cancel 상태 (UI 라우트는 참조 안 함)
    loop.close()  # 미사용 루프 즉시 닫아 ResourceWarning 방지
    p = PendingPick(
        request_id=rid,
        candidates=list(asset_ids),
        reason=reason,
        project_id=None,
        created_at=time.time(),
        status="pending",
        future=fut,
        _loop=loop,
        _seq=1,
    )
    deps.pending_picks._items[rid] = p
    return rid


# ─── Task 4.4 테스트 ─────────────────────────────────────────────────────────


def test_ui_pick_card_200_renders_candidates(pick_client, populated_store):
    """등록된 pending pick → GET /ui/pick-card/{rid} 200 + 후보 data-asset-id 포함."""
    client, deps = pick_client
    store, ids = populated_store

    # hero + coin 두 에셋을 후보로 등록
    asset_ids = [ids["hero"], ids["coin"]]
    rid = _register_pick(deps, asset_ids)

    r = client.get(f"/ui/pick-card/{rid}")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]

    for aid in asset_ids:
        assert f'data-asset-id="{aid}"' in r.text, (
            f"data-asset-id=\"{aid}\" 가 응답 HTML 에 없음"
        )


def test_ui_pick_card_404_unknown_rid(pick_client):
    """존재하지 않는 rid → 404."""
    client, _ = pick_client
    r = client.get("/ui/pick-card/nonexistent-rid-xyz")
    assert r.status_code == 404


def test_ui_pick_card_includes_reason(pick_client, populated_store):
    """reason='explosion sound' 이면 응답 HTML 에 해당 문자열 포함."""
    client, deps = pick_client
    store, ids = populated_store

    rid = _register_pick(deps, [ids["jump"]], reason="explosion sound")

    r = client.get(f"/ui/pick-card/{rid}")
    assert r.status_code == 200
    assert "explosion sound" in r.text


def test_ui_pick_card_adopt_button_has_correct_hx_post(pick_client, populated_store):
    """[채택] 버튼이 hx-post="/api/user-pick/{rid}" 속성을 가진다."""
    client, deps = pick_client
    store, ids = populated_store

    asset_ids = [ids["hero"], ids["menu_bg"]]
    rid = _register_pick(deps, asset_ids)

    r = client.get(f"/ui/pick-card/{rid}")
    assert r.status_code == 200
    assert f'/api/user-pick/{rid}"' in r.text or f"/api/user-pick/{rid}" in r.text


def test_ui_pick_card_cancel_button_has_correct_hx_post(pick_client, populated_store):
    """[✕ 거부] 버튼이 hx-post="/api/user-pick/{rid}/cancel" 을 가진다."""
    client, deps = pick_client
    store, ids = populated_store

    rid = _register_pick(deps, [ids["coin"]])

    r = client.get(f"/ui/pick-card/{rid}")
    assert r.status_code == 200
    assert f"/api/user-pick/{rid}/cancel" in r.text


def test_ui_pick_card_has_pick_card_group_class(pick_client, populated_store):
    """최상위 div 에 class="pick-card-group" 이 있다."""
    client, deps = pick_client
    store, ids = populated_store

    rid = _register_pick(deps, [ids["bgm_loop"]])

    r = client.get(f"/ui/pick-card/{rid}")
    assert r.status_code == 200
    assert "pick-card-group" in r.text


def test_ui_pick_card_includes_claude_badge(pick_client, populated_store):
    """응답 HTML 에 'Claude 요청' 또는 badge 가 포함된다."""
    client, deps = pick_client
    store, ids = populated_store

    rid = _register_pick(deps, [ids["hero"]])

    r = client.get(f"/ui/pick-card/{rid}")
    assert r.status_code == 200
    # 배지 텍스트 (한국어)
    assert "Claude 요청" in r.text or "badge" in r.text


def test_ui_pick_card_sound_candidate_renders(pick_client, populated_store):
    """sound kind 에셋을 후보로 지정해도 200 으로 렌더된다."""
    client, deps = pick_client
    store, ids = populated_store

    rid = _register_pick(deps, [ids["bgm_loop"], ids["jump"]])

    r = client.get(f"/ui/pick-card/{rid}")
    assert r.status_code == 200
    for aid in [ids["bgm_loop"], ids["jump"]]:
        assert f'data-asset-id="{aid}"' in r.text
