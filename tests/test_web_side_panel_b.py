"""M5 Phase 3B — B 탭 사이드 패널 검증 (Task 3.4 / 3.5 / 3.6)."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


# ── 공통 fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


@pytest.fixture
def populated_deps(tmp_path, populated_store, fake_embedder):
    """에셋 + 라벨이 채워진 WebDeps (bootstrap 포함)."""
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
    registry.bootstrap()  # 24축 시드 라벨 주입
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


# ── Task 3.4: 매칭 모드 라디오 ─────────────────────────────────────────


def test_b_tab_has_match_mode_fieldset(client):
    """B 탭 콘텐츠에 match-mode fieldset 이 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "match-mode" in r.text


def test_b_tab_match_mode_has_and(client):
    """매칭 모드 AND 라디오가 존재한다."""
    r = client.get("/library")
    assert "AND" in r.text


def test_b_tab_match_mode_has_or(client):
    """매칭 모드 OR 라디오가 존재한다."""
    r = client.get("/library")
    assert "OR" in r.text


def test_b_tab_match_mode_has_not(client):
    """매칭 모드 NOT 라디오가 존재한다."""
    r = client.get("/library")
    assert "NOT" in r.text


def test_b_tab_match_mode_xmodel(client):
    """라디오가 $store.search.matchMode 를 x-model 로 바인딩한다."""
    r = client.get("/library")
    assert "$store.search.matchMode" in r.text


def test_b_tab_match_mode_triggers_search(client):
    """라디오 @change 가 검색을 트리거한다 (htmx.trigger 또는 Alpine watcher)."""
    r = client.get("/library")
    # htmx.trigger 또는 $watch 방식 중 하나
    assert "htmx.trigger" in r.text or "$watch" in r.text


# ── Task 3.5: 라벨 검색 input + 매칭 칩 CSS ───────────────────────────


def test_b_tab_has_label_filter_input(client):
    """B 탭에 type='search' 라벨 검색 input 이 존재한다."""
    r = client.get("/library")
    assert 'type="search"' in r.text


def test_b_tab_label_filter_xmodel(client):
    """라벨 검색 input 이 $store.b.labelFilter 를 x-model 로 바인딩한다."""
    r = client.get("/library")
    assert "$store.b.labelFilter" in r.text


def test_b_tab_label_filter_placeholder(client):
    """라벨 검색 input 에 placeholder 가 있다."""
    r = client.get("/library")
    assert "라벨 검색" in r.text


def test_main_css_has_chip_matched():
    """main.css 에 .chip.matched 스타일이 정의되어 있다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".chip.matched" in css


def test_main_css_chip_matched_uses_var(client):
    """main.css 의 .chip.matched 가 CSS 변수를 사용한다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    # --chip-matched 변수 참조
    assert "--chip-matched" in css


# ── Task 3.6: 종류 탭 (sprite/sheet/sound) ────────────────────────────


def test_b_tab_has_kind_tabs_nav(client):
    """B 탭에 class='kind-tabs' nav 가 존재한다."""
    r = client.get("/library")
    assert "kind-tabs" in r.text


def test_b_tab_kind_tab_sprite(client):
    """종류 탭에 스프라이트 버튼이 존재한다."""
    r = client.get("/library")
    assert "스프라이트" in r.text


def test_b_tab_kind_tab_sheet(client):
    """종류 탭에 시트 버튼이 존재한다."""
    r = client.get("/library")
    assert "시트" in r.text


def test_b_tab_kind_tab_sound(client):
    """종류 탭에 사운드 버튼이 존재한다."""
    r = client.get("/library")
    assert "사운드" in r.text


def test_b_tab_kind_tab_xclick_binding(client):
    """종류 탭 버튼이 $store.b.kindTab 을 @click 으로 변경한다."""
    r = client.get("/library")
    assert "$store.b.kindTab" in r.text


def test_kind_tabs_has_active_class_binding(client):
    """종류 탭 버튼에 :class='{active: ...}' 바인딩이 존재한다."""
    r = client.get("/library")
    assert "active" in r.text and "kindTab" in r.text


def test_main_css_has_kind_tabs():
    """main.css 에 .kind-tabs 스타일이 정의되어 있다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".kind-tabs" in css


# ── Task 3.6: _classify_axis 단위 테스트 ─────────────────────────────


def test_classify_axis_sound_category():
    from gah.web.routers.filters import _classify_axis
    assert _classify_axis("sound_category") == "sound"


def test_classify_axis_sound_tempo():
    from gah.web.routers.filters import _classify_axis
    assert _classify_axis("sound_tempo") == "sound"


def test_classify_axis_sheet_grid():
    from gah.web.routers.filters import _classify_axis
    assert _classify_axis("sheet_grid") == "sheet"


def test_classify_axis_category_is_sprite():
    from gah.web.routers.filters import _classify_axis
    assert _classify_axis("category") == "sprite"


def test_classify_axis_style_is_sprite():
    from gah.web.routers.filters import _classify_axis
    assert _classify_axis("style") == "sprite"


# ── Task 3.6: /api/filters/labels 엔드포인트 ──────────────────────────


def test_filters_labels_returns_200(populated_client):
    """/api/filters/labels GET → 200."""
    r = populated_client.get("/api/filters/labels")
    assert r.status_code == 200


def test_filters_labels_has_three_keys(populated_client):
    """/api/filters/labels 응답에 sprite/sheet/sound 키가 있다."""
    r = populated_client.get("/api/filters/labels")
    body = r.json()
    assert "sprite" in body
    assert "sheet" in body
    assert "sound" in body


def test_filters_labels_sprite_is_list(populated_client):
    """sprite 키 값이 list 다."""
    r = populated_client.get("/api/filters/labels")
    assert isinstance(r.json()["sprite"], list)


def test_filters_labels_sheet_is_empty_list(populated_client):
    """SEED 에 sheet_* axis 없음 → sheet 는 빈 list."""
    r = populated_client.get("/api/filters/labels")
    assert r.json()["sheet"] == []


def test_filters_labels_sprite_has_category_axis(populated_client):
    """sprite 버킷에 'category' axis 가 존재한다."""
    r = populated_client.get("/api/filters/labels")
    sprite = r.json()["sprite"]
    axes = [g["axis"] for g in sprite]
    assert "category" in axes


def test_filters_labels_sprite_has_style_axis(populated_client):
    """sprite 버킷에 'style' axis 가 존재한다."""
    r = populated_client.get("/api/filters/labels")
    sprite = r.json()["sprite"]
    axes = [g["axis"] for g in sprite]
    assert "style" in axes


def test_filters_labels_sound_has_sound_category_axis(populated_client):
    """sound 버킷에 'sound_category' axis 가 존재한다."""
    r = populated_client.get("/api/filters/labels")
    sound = r.json()["sound"]
    axes = [g["axis"] for g in sound]
    assert "sound_category" in axes


def test_filters_labels_group_has_labels_list(populated_client):
    """각 axis 그룹에 'labels' 리스트가 있다."""
    r = populated_client.get("/api/filters/labels")
    sprite = r.json()["sprite"]
    assert len(sprite) > 0
    for group in sprite:
        assert "axis" in group
        assert "labels" in group
        assert isinstance(group["labels"], list)


def test_filters_labels_empty_store(client):
    """/api/filters/labels — 빈 DB (bootstrap 없음) → 빈 버킷 3개."""
    r = client.get("/api/filters/labels")
    assert r.status_code == 200
    body = r.json()
    assert body["sprite"] == []
    assert body["sheet"] == []
    assert body["sound"] == []
