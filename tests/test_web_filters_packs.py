"""M5 Phase 3B-2 — Task 3.8: /api/filters/packs + 다축 필터 검증."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


# ── 공통 fixtures ──────────────────────────────────────────────────────
# populated_deps / populated_client → conftest.py 공통 fixture 사용

@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# ── /api/filters/packs 엔드포인트 ─────────────────────────────────────


def test_filters_packs_returns_200(client):
    """/api/filters/packs GET → 200."""
    r = client.get("/api/filters/packs")
    assert r.status_code == 200


def test_filters_packs_has_packs_key(client):
    """응답에 'packs' 키가 있다."""
    r = client.get("/api/filters/packs")
    assert "packs" in r.json()


def test_filters_packs_has_vendors_key(client):
    """응답에 'vendors' 키가 있다."""
    r = client.get("/api/filters/packs")
    assert "vendors" in r.json()


def test_filters_packs_has_licenses_key(client):
    """응답에 'licenses' 키가 있다."""
    r = client.get("/api/filters/packs")
    assert "licenses" in r.json()


def test_filters_packs_empty_catalog(client):
    """빈 카탈로그 → packs=[], vendors=[], licenses=[]."""
    r = client.get("/api/filters/packs")
    body = r.json()
    assert body["packs"] == []
    assert body["vendors"] == []
    assert body["licenses"] == []


def test_filters_packs_populated_returns_two_packs(populated_client):
    """populated DB → 2개 팩 반환."""
    r = populated_client.get("/api/filters/packs")
    body = r.json()
    assert len(body["packs"]) == 2


def test_filters_packs_item_has_required_fields(populated_client):
    """각 팩 항목에 id/name/display_name/vendor/license/enabled/asset_count 키 존재."""
    r = populated_client.get("/api/filters/packs")
    for item in r.json()["packs"]:
        assert "id" in item
        assert "name" in item
        assert "display_name" in item
        assert "vendor" in item
        assert "license" in item
        assert "enabled" in item
        assert "asset_count" in item


def test_filters_packs_asset_count_correct(populated_client):
    """각 팩의 asset_count 가 실제 자산 수와 일치한다 (pack_a = 3, pack_b = 3)."""
    r = populated_client.get("/api/filters/packs")
    counts = {item["name"]: item["asset_count"] for item in r.json()["packs"]}
    assert counts.get("pack_a") == 3
    assert counts.get("pack_b") == 3


def test_filters_packs_vendors_are_distinct_sorted(populated_client):
    """vendors 는 distinct + 정렬된 list."""
    r = populated_client.get("/api/filters/packs")
    vendors = r.json()["vendors"]
    assert isinstance(vendors, list)
    assert vendors == sorted(set(vendors))
    # populated_store 에는 kenney, craftpix 두 벤더
    assert "kenney" in vendors
    assert "craftpix" in vendors


def test_filters_packs_enabled_field_is_bool(populated_client):
    """enabled 필드가 bool 타입이다."""
    r = populated_client.get("/api/filters/packs")
    for item in r.json()["packs"]:
        assert isinstance(item["enabled"], bool)


# ── base.html Alpine store "b" 확장 ───────────────────────────────────


def test_base_html_has_selected_pack_ids(client):
    """base.html Alpine store b 에 selectedPackIds 필드가 존재한다."""
    r = client.get("/library")
    assert "selectedPackIds" in r.text


def test_base_html_has_selected_vendors(client):
    """base.html Alpine store b 에 selectedVendors 필드가 존재한다."""
    r = client.get("/library")
    assert "selectedVendors" in r.text


def test_base_html_has_selected_licenses(client):
    """base.html Alpine store b 에 selectedLicenses 필드가 존재한다."""
    r = client.get("/library")
    assert "selectedLicenses" in r.text


def test_base_html_has_selected_state(client):
    """base.html Alpine store b 에 selectedState 필드가 존재한다."""
    r = client.get("/library")
    assert "selectedState" in r.text


# ── _side_panel_b.html 다축 필터 HTML ─────────────────────────────────


def test_b_tab_has_multi_filters(client):
    """B 탭에 multi-filters 영역이 존재한다."""
    r = client.get("/library")
    assert "multi-filters" in r.text


def test_b_tab_has_filter_group_details(client):
    """B 탭에 filter-group <details> 드롭다운이 존재한다."""
    r = client.get("/library")
    assert "filter-group" in r.text


def test_b_tab_has_pack_filter_label(client):
    """B 탭에 '팩' 필터 레이블이 존재한다."""
    r = client.get("/library")
    assert "팩" in r.text


def test_b_tab_has_vendor_filter_label(client):
    """B 탭에 '벤더' 필터 레이블이 존재한다."""
    r = client.get("/library")
    assert "벤더" in r.text


def test_b_tab_has_license_filter_label(client):
    """B 탭에 '라이선스' 필터 레이블이 존재한다."""
    r = client.get("/library")
    assert "라이선스" in r.text


def test_b_tab_has_state_filter_label(client):
    """B 탭에 '상태' 필터 레이블이 존재한다."""
    r = client.get("/library")
    assert "상태" in r.text


def test_b_tab_state_filter_has_all_option(client):
    """상태 필터에 '전체' 옵션이 있다."""
    r = client.get("/library")
    assert "전체" in r.text


def test_b_tab_state_filter_has_ok_option(client):
    """상태 필터에 '완료' 옵션이 있다."""
    r = client.get("/library")
    assert "완료" in r.text


def test_b_tab_multi_filters_fetches_packs_api(client):
    """다축 필터가 /api/filters/packs 를 fetch 한다."""
    r = client.get("/library")
    assert "/api/filters/packs" in r.text


def test_main_css_has_multi_filters():
    """main.css 에 .multi-filters 스타일이 정의되어 있다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".multi-filters" in css


def test_main_css_has_filter_group():
    """main.css 에 .filter-group 스타일이 정의되어 있다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".filter-group" in css


def test_main_css_has_filter_label():
    """main.css 에 .filter-label 스타일이 정의되어 있다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".filter-label" in css
