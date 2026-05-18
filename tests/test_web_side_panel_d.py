"""M5 Phase 3D-1 — D 탭 프리셋 3버튼 + 슬라이더 6개 검증 (Task 3.12 / 3.13)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


# ── 공통 fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# ── Task 3.12: D 탭 프리셋 3 버튼 ─────────────────────────────────────


def test_d_tab_has_preset_section(client):
    """D 탭에 가중치 프리셋 섹션이 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "프리셋" in r.text


def test_d_tab_has_three_preset_buttons(client):
    """D 탭에 균형/통일성 우선/참신성 버튼이 존재한다."""
    r = client.get("/library")
    assert "균형" in r.text
    assert "통일성 우선" in r.text
    assert "참신성" in r.text


def test_d_tab_preset_buttons_call_apply_preset(client):
    """D 탭 프리셋 버튼이 applyPreset() 함수를 호출한다."""
    r = client.get("/library")
    assert "applyPreset" in r.text
    assert "applyPreset('balanced')" in r.text or 'applyPreset("balanced")' in r.text
    assert "applyPreset('consistency')" in r.text or 'applyPreset("consistency")' in r.text
    assert "applyPreset('novelty')" in r.text or 'applyPreset("novelty")' in r.text


def test_d_tab_preset_buttons_bind_active_state(client):
    """D 탭 프리셋 버튼이 $store.d.activePreset 에 바인딩된다."""
    r = client.get("/library")
    assert "$store.d.activePreset" in r.text


def test_d_tab_no_phase3d_placeholder(client):
    """Phase 3D placeholder 가 더 이상 없다 (실 구현으로 교체됨)."""
    r = client.get("/library")
    assert "Phase 3D 에서" not in r.text


def test_api_preset_balanced_returns_200(client):
    """POST /api/preset/balanced → 200 + weights 반환."""
    r = client.post("/api/preset/balanced")
    assert r.status_code == 200
    data = r.json()
    assert data["preset"] == "balanced"
    assert "weights" in data
    weights = data["weights"]
    assert abs(weights["semantic"] - 0.35) < 1e-6
    assert abs(weights["keyword"] - 0.10) < 1e-6
    assert abs(weights["label_match"] - 0.20) < 1e-6
    assert abs(weights["consistency"] - 0.20) < 1e-6
    assert abs(weights["recency"] - 0.05) < 1e-6
    assert abs(weights["feedback"] - 0.10) < 1e-6


def test_api_preset_consistency_returns_high_consistency_weight(client):
    """POST /api/preset/consistency → consistency=0.40 확인."""
    r = client.post("/api/preset/consistency")
    assert r.status_code == 200
    data = r.json()
    assert data["preset"] == "consistency"
    weights = data["weights"]
    assert abs(weights["consistency"] - 0.40) < 1e-6
    assert abs(weights["semantic"] - 0.25) < 1e-6
    assert abs(weights["feedback"] - 0.05) < 1e-6


def test_api_preset_novelty_returns_low_consistency_weight(client):
    """POST /api/preset/novelty → consistency=0.05 확인."""
    r = client.post("/api/preset/novelty")
    assert r.status_code == 200
    data = r.json()
    assert data["preset"] == "novelty"
    weights = data["weights"]
    assert abs(weights["consistency"] - 0.05) < 1e-6
    assert abs(weights["semantic"] - 0.40) < 1e-6
    assert abs(weights["keyword"] - 0.15) < 1e-6


def test_api_preset_unknown_returns_404(client):
    """POST /api/preset/unknown → 404 반환."""
    r = client.post("/api/preset/unknown_preset")
    assert r.status_code == 404


def test_api_preset_updates_config(deps_fixture):
    """POST /api/preset/consistency 후 deps.config.weight_consistency 가 0.40 으로 갱신된다."""
    from gah.web.app import build_app

    app = build_app(deps_fixture)
    with TestClient(app) as client:
        r = client.post("/api/preset/consistency")
        assert r.status_code == 200
        # app.state.deps.config 가 갱신됐는지 확인
        updated_config = app.state.deps.config
        assert abs(updated_config.weight_consistency - 0.40) < 1e-6
        assert abs(updated_config.weight_semantic - 0.25) < 1e-6


# ── Task 3.13: D 탭 슬라이더 6개 ──────────────────────────────────────


def test_d_tab_has_sliders_section(client):
    """D 탭에 슬라이더 직접 조정 섹션이 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "슬라이더" in r.text


def test_d_tab_sliders_are_in_details_element(client):
    """D 탭 슬라이더 섹션이 <details> 요소 안에 있다."""
    r = client.get("/library")
    assert "<details" in r.text
    assert "syncWeights" in r.text


def test_d_tab_has_six_slider_labels(client):
    """D 탭 슬라이더에 6개 가중치 레이블 (semantic/keyword/label/consistency/recency/feedback) 이 있다."""
    r = client.get("/library")
    assert "의미" in r.text
    assert "키워드" in r.text
    assert "라벨" in r.text
    # "통일성" 은 프리셋 탭에도 있으므로 슬라이더 섹션 내 존재를 간접 확인
    assert "신선도" in r.text or "recency" in r.text.lower()
    assert "피드백" in r.text


def test_d_tab_sliders_bind_weights_store(client):
    """D 탭 슬라이더가 $store.weights.* 에 x-model 로 바인딩된다."""
    r = client.get("/library")
    assert "$store.weights.semantic" in r.text
    assert "$store.weights.keyword" in r.text
    assert "$store.weights.consistency" in r.text


def test_d_tab_sliders_are_range_type(client):
    """D 탭 슬라이더가 type='range' input 이다."""
    r = client.get("/library")
    assert 'type="range"' in r.text


def test_d_tab_sliders_have_min_max(client):
    """D 탭 슬라이더가 min=0 max=100 속성을 가진다."""
    r = client.get("/library")
    assert 'min="0"' in r.text
    assert 'max="100"' in r.text


def test_api_weights_returns_200(client):
    """POST /api/weights 정상 body → 200 + 응답 dict."""
    body = {
        "semantic": 0.35,
        "keyword": 0.10,
        "label_match": 0.20,
        "consistency": 0.20,
        "recency": 0.05,
        "feedback": 0.10,
    }
    r = client.post("/api/weights", json=body)
    assert r.status_code == 200
    data = r.json()
    assert abs(data["semantic"] - 0.35) < 1e-6
    assert abs(data["consistency"] - 0.20) < 1e-6


def test_api_weights_rejects_out_of_range(client):
    """POST /api/weights 에서 ge=0 / le=1 범위 초과 값은 422 반환 (Pydantic 검증)."""
    body = {
        "semantic": 1.5,  # le=1 위반
        "keyword": 0.10,
        "label_match": 0.20,
        "consistency": 0.20,
        "recency": 0.05,
        "feedback": 0.10,
    }
    r = client.post("/api/weights", json=body)
    assert r.status_code == 422


def test_api_weights_rejects_negative_value(client):
    """POST /api/weights 에서 음수 값은 422 반환."""
    body = {
        "semantic": -0.1,  # ge=0 위반
        "keyword": 0.10,
        "label_match": 0.20,
        "consistency": 0.20,
        "recency": 0.05,
        "feedback": 0.10,
    }
    r = client.post("/api/weights", json=body)
    assert r.status_code == 422


def test_api_weights_allows_sum_not_one(client):
    """POST /api/weights 는 합 != 1 인 body 도 허용한다 (정규화는 frontend 책임)."""
    body = {
        "semantic": 0.50,
        "keyword": 0.50,
        "label_match": 0.50,
        "consistency": 0.50,
        "recency": 0.50,
        "feedback": 0.50,
    }
    r = client.post("/api/weights", json=body)
    # 각각 0~1 범위 내이므로 허용
    assert r.status_code == 200


def test_api_weights_updates_config(deps_fixture):
    """POST /api/weights 후 deps.config.weight_consistency 가 갱신된다."""
    from gah.web.app import build_app

    app = build_app(deps_fixture)
    with TestClient(app) as client:
        body = {
            "semantic": 0.10,
            "keyword": 0.10,
            "label_match": 0.10,
            "consistency": 0.60,
            "recency": 0.05,
            "feedback": 0.05,
        }
        r = client.post("/api/weights", json=body)
        assert r.status_code == 200
        updated_config = app.state.deps.config
        assert abs(updated_config.weight_consistency - 0.60) < 1e-6
        assert abs(updated_config.weight_semantic - 0.10) < 1e-6


# ── Phase 3D-2 실 구현 확인 (Phase 3D-2 완료 후 갱신) ─────────────────


def test_d_tab_has_saved_and_usage_sections(client):
    """D 탭에 Phase 3D-2 실 구현 (저장된 검색 + 통일성/페널티) 섹션이 있다."""
    r = client.get("/library")
    assert "저장된 검색" in r.text
    assert "통일성 / 페널티" in r.text


# ── Alpine.store 초기화 확인 ────────────────────────────────────────────


def test_page_initializes_d_store(client):
    """base.html 에 Alpine.store('d', ...) 초기화가 있다."""
    r = client.get("/library")
    assert "Alpine.store" in r.text
    assert "'d'" in r.text or '"d"' in r.text


def test_page_initializes_weights_store(client):
    """base.html 에 Alpine.store('weights', ...) 초기화가 있다."""
    r = client.get("/library")
    assert "'weights'" in r.text or '"weights"' in r.text
