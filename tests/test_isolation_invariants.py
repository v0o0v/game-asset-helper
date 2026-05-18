"""M7 — 라이브러리 ↔ Unity 후보 격리 (I-1~I-4) + 프로젝트 간 선호도 격리 (I-5)."""
from __future__ import annotations

import inspect
import time
from pathlib import Path

import pytest

from gah.core.unity_import.scanner import UnityAssetStoreScanner
from gah.core.unity_import.unitypackage import parse_pathnames
from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage


@pytest.fixture
def cache_with_one_pkg(tmp_path):
    pub = tmp_path / "Pub" / "Cat"
    pub.mkdir(parents=True)
    make_fixture_unitypackage(pub / "X.unitypackage")
    return tmp_path


def test_i1_discovered_not_in_assets(cache_with_one_pkg, store):
    """I-1: discovered/previewed 패키지의 자산은 assets 테이블에 없음."""
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_with_one_pkg)

    rows = store.list_unity_imports()
    assert rows, "스캔 후 unity_imports 에 최소 1개 존재해야 함"
    # 모두 imported 상태가 아닌지 확인
    assert all(r.import_state != "imported" for r in rows)

    # assets 테이블에는 해당 .unitypackage 경로를 path 로 가진 row 가 없어야 함
    assets = store.list_assets()
    pkg_paths = {str(r.package_path) for r in rows}
    for a in assets:
        assert str(a.path) not in pkg_paths, (
            f"assets 테이블에 .unitypackage 경로가 직접 등록됨: {a.path}"
        )


def test_i2_preview_no_side_effects(cache_with_one_pkg, store):
    """I-2: preview 는 unity_imports.preview_* 만 갱신 — library/assets 부작용 0."""
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_with_one_pkg)

    uid = store.list_unity_imports()[0].id
    row = store.get_unity_import_by_id(uid)

    # 기존 packs / assets 카운트 스냅샷
    packs_before = len(store.list_packs())
    assets_before = len(store.list_assets())

    # preview 시뮬레이션: parse_pathnames + update_unity_preview
    entries = parse_pathnames(row.package_path)
    store.update_unity_preview(
        uid,
        asset_count=len(entries),
        image_count=sum(1 for e in entries.values() if e.internal_kind == "image"),
        sound_count=sum(1 for e in entries.values() if e.internal_kind == "sound"),
    )

    # packs / assets 카운트 변동 없음
    packs_after = len(store.list_packs())
    assets_after = len(store.list_assets())
    assert packs_before == packs_after, (
        f"preview 후 packs 카운트 변동: {packs_before} → {packs_after}"
    )
    assert assets_before == assets_after, (
        f"preview 후 assets 카운트 변동: {assets_before} → {assets_after}"
    )


def test_i3_library_router_does_not_query_unity_imports():
    """I-3: 라이브러리 라우터가 unity_imports 테이블을 조회하지 않는다."""
    import gah.web.routers.library as lib_router

    src = inspect.getsource(lib_router)
    assert "unity_imports" not in src, (
        "library router 가 unity_imports 테이블을 직접 참조: I-3 위반"
    )


def test_i4_unity_router_does_not_call_library_api():
    """I-4: Unity 라우터가 라이브러리 API (list_assets/find_asset 등) 를 호출하지 않는다."""
    import gah.web.routers.unity_asset_store as unity_router

    src = inspect.getsource(unity_router)
    # 라이브러리 검색 / 자산 조회 API 호출 금지
    forbidden = ["list_assets", "find_asset", "tool_find_asset", "tool_list_assets"]
    for name in forbidden:
        assert name not in src, (
            f"unity_asset_store router 가 {name} 호출: I-4 위반"
        )


def test_i5_project_preferences_isolated(store, asset_factory):
    """I-5: project_A 의 weight/usage 가 project_B 점수에 미반영."""
    pa = store.upsert_project_id(external_id="D:/A", display_name="A")
    pb = store.upsert_project_id(external_id="D:/B", display_name="B")
    aid = asset_factory()
    asset = store.get_asset_by_id(aid)

    # A 에 negative feedback 3회 + 사용 5회
    for _ in range(3):
        store.insert_feedback_record(
            pa, aid, None,
            reason="negative", weight=-0.5,
        )
    for _ in range(5):
        store.record_asset_use(
            pa, aid, asset.pack_id,
            source="explicit", used_at=int(time.time()),
        )

    # B 의 선호도 응답에서 해당 자산은 점수 0 또는 row 없음
    rows_b = store.get_project_asset_preferences(project_id=pb)
    matching_b = [r for r in rows_b if r.asset_id == aid]
    if matching_b:
        assert matching_b[0].composite_score == pytest.approx(0.0), (
            f"I-5 위반: project B 에서 asset {aid} 의 composite_score = "
            f"{matching_b[0].composite_score} (0 이어야 함)"
        )
        assert matching_b[0].usage_count == 0, (
            f"I-5 위반: project B 에서 asset {aid} 의 usage_count = "
            f"{matching_b[0].usage_count} (0 이어야 함)"
        )
