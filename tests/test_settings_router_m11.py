"""M11 Phase 5 — /api/settings/backends/<name> + /test + /chains 라우터.

기존 M8 settings 라우터 (`/api/settings`) 와 별개로, multi-backend LLM 설정용
3 endpoint 추가:

- POST /api/settings/backends/<name>  — backend 설정 갱신 (JSON body)
- POST /api/settings/backends/<name>/test  — backend.test_connection 호출
- POST /api/settings/chains  — chain 순서 갱신
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def web_deps(deps_fixture):
    return deps_fixture


@pytest.fixture
def web_app(web_deps):
    from assetcache.web.app import build_app

    return build_app(web_deps)


@pytest.fixture
def client(web_app):
    return TestClient(web_app)


# ---- POST /api/settings/backends/<name> ----


def test_post_backend_update_enables_and_saves(client, web_deps):
    """gemini enabled + api_key + 모델 갱신."""
    r = client.post(
        "/api/settings/backends/gemini",
        json={
            "enabled": True,
            "api_key": "AIzaTest",
            "model_image": "gemini-2.5-flash",
            "model_audio": "gemini-2.5-flash",
            "model_embed": "gemini-embedding-001",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert web_deps.config.backends["gemini"]["enabled"] is True
    assert web_deps.config.backends["gemini"]["api_key"] == "AIzaTest"


def test_post_backend_update_partial_keeps_others(client, web_deps):
    """api_key 만 변경 — 다른 필드는 유지."""
    web_deps.config.backends["gemini"]["enabled"] = True
    web_deps.config.backends["gemini"]["model_image"] = "old-model"
    r = client.post(
        "/api/settings/backends/gemini",
        json={"api_key": "AIzaNew"},
    )
    assert r.status_code == 200
    assert web_deps.config.backends["gemini"]["api_key"] == "AIzaNew"
    # enabled / model_image 그대로 유지
    assert web_deps.config.backends["gemini"]["enabled"] is True
    assert web_deps.config.backends["gemini"]["model_image"] == "old-model"


def test_post_backend_update_unknown_backend_404(client):
    r = client.post(
        "/api/settings/backends/wat",
        json={"enabled": True},
    )
    assert r.status_code == 404


def test_post_backend_update_persists_to_file(client, web_deps, monkeypatch):
    """save_config 가 호출되어 cfg 가 영속."""
    from assetcache.web.routers import settings as settings_mod

    saved = []
    real_save = settings_mod.save_config

    def _spy(cfg, path):
        saved.append((cfg.backends["openai"]["api_key"], str(path)))
        return real_save(cfg, path)

    monkeypatch.setattr(settings_mod, "save_config", _spy)
    r = client.post(
        "/api/settings/backends/openai",
        json={"enabled": True, "api_key": "sk-saved"},
    )
    assert r.status_code == 200
    assert len(saved) == 1
    assert saved[0][0] == "sk-saved"


def test_post_backend_update_rejects_unknown_fields(client, web_deps):
    """알려진 필드만 갱신 — `evil` 같은 임의 키는 무시. M11.9: claude→openai 로 backend swap."""
    r = client.post(
        "/api/settings/backends/openai",
        json={"api_key": "sk-x", "evil": "injected"},
    )
    assert r.status_code == 200
    assert "evil" not in web_deps.config.backends["openai"]


# ---- POST /api/settings/backends/<name>/test ----


def test_post_backend_test_returns_ok(client, web_deps, monkeypatch):
    """test_connection 이 True 반환 시 {ok: True} JSON."""
    # ollama 가 기본 enabled → registry rebuild 후 backend.test_connection 호출
    from assetcache.web.routers import settings as settings_mod

    fake_backend = MagicMock()
    fake_backend.test_connection.return_value = True
    fake_registry = MagicMock()
    fake_registry.get_backend.return_value = fake_backend

    monkeypatch.setattr(
        settings_mod, "_build_registry_for_test",
        lambda cfg: fake_registry,
    )
    r = client.post("/api/settings/backends/ollama/test")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    fake_backend.test_connection.assert_called_once()


def test_post_backend_test_returns_failure(client, web_deps, monkeypatch):
    """test_connection False → {ok: False}."""
    from assetcache.web.routers import settings as settings_mod

    fake_backend = MagicMock()
    fake_backend.test_connection.return_value = False
    fake_registry = MagicMock()
    fake_registry.get_backend.return_value = fake_backend

    monkeypatch.setattr(
        settings_mod, "_build_registry_for_test",
        lambda cfg: fake_registry,
    )
    r = client.post("/api/settings/backends/gemini/test")
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_post_backend_test_unknown_backend_404(client):
    r = client.post("/api/settings/backends/wat/test")
    assert r.status_code == 404


def test_post_backend_test_disabled_backend_returns_message(
    client, web_deps, monkeypatch
):
    """비활성 backend — registry 가 instantiation 안 해 None 반환 → {ok: False, message}.

    M11.9: openrouter→openai 로 swap (openai 도 default disabled).
    """
    from assetcache.web.routers import settings as settings_mod

    fake_registry = MagicMock()
    fake_registry.get_backend.return_value = None  # disabled / not configured
    monkeypatch.setattr(
        settings_mod, "_build_registry_for_test",
        lambda cfg: fake_registry,
    )
    r = client.post("/api/settings/backends/openai/test")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "message" in body or "error" in body


# ---- POST /api/settings/chains ----


def test_post_chains_reorder_chat_image(client, web_deps):
    """chat_image 순서 변경."""
    r = client.post(
        "/api/settings/chains",
        json={"chat_image": ["gemini", "ollama"]},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert web_deps.config.chains["chat_image"] == ["gemini", "ollama"]


def test_post_chains_reorder_all_modalities(client, web_deps):
    """3 modality 동시 변경."""
    r = client.post(
        "/api/settings/chains",
        json={
            "chat_image": ["openai", "ollama"],
            "chat_audio": ["openai", "ollama"],
            "text_embed": ["openai", "ollama"],
        },
    )
    assert r.status_code == 200
    assert web_deps.config.chains["chat_image"] == ["openai", "ollama"]
    assert web_deps.config.chains["chat_audio"] == ["openai", "ollama"]
    assert web_deps.config.chains["text_embed"] == ["openai", "ollama"]


def test_post_chains_unknown_modality_rejected(client, web_deps):
    """알 수 없는 modality 키 → 400."""
    r = client.post(
        "/api/settings/chains",
        json={"chat_video": ["gemini"]},
    )
    assert r.status_code == 400


def test_post_chains_unknown_backend_rejected(client, web_deps):
    """알 수 없는 backend 이름 → 400."""
    r = client.post(
        "/api/settings/chains",
        json={"chat_image": ["xinference", "ollama"]},
    )
    assert r.status_code == 400


def test_post_chains_empty_list_allowed(client, web_deps):
    """빈 chain 도 허용 — UI 가 잠시 모든 backend 제거하는 중간 상태."""
    r = client.post(
        "/api/settings/chains",
        json={"chat_image": []},
    )
    assert r.status_code == 200
    assert web_deps.config.chains["chat_image"] == []


# ---- Settings 페이지 (UI) ----


def test_settings_page_includes_backends_section(client):
    """/settings 페이지가 3 backend 이름 모두 렌더링 (M11.9: 6→3)."""
    r = client.get("/settings")
    assert r.status_code == 200
    body = r.text
    for name in ("ollama", "gemini", "openai"):
        assert name in body, f"settings page missing backend: {name}"


def test_settings_page_includes_chains_section(client):
    """/settings 페이지가 4 modality (M11.2 chat_spritesheet 포함) 모두 렌더링."""
    r = client.get("/settings")
    assert r.status_code == 200
    body = r.text
    assert "chat_image" in body
    assert "chat_spritesheet" in body
    assert "chat_audio" in body
    assert "text_embed" in body


def test_settings_page_modality_order_includes_chat_spritesheet(client):
    """M11.3 patch A — modalityOrder JS 배열에 chat_spritesheet 가 명시적으로 포함."""
    r = client.get("/settings")
    assert r.status_code == 200
    body = r.text
    # JS 배열 리터럴 확인 — chat_spritesheet 가 modalityOrder 안에
    assert "modalityOrder:" in body
    # 배열 시작부터 chat_spritesheet 까지 같은 줄/구간에 등장하는지 거친 검사
    idx_order = body.index("modalityOrder:")
    idx_end = body.index("modalityLabels:", idx_order)
    order_slice = body[idx_order:idx_end]
    assert "chat_spritesheet" in order_slice, "modalityOrder 에 chat_spritesheet 누락"


def test_settings_page_chain_add_initializer_includes_chat_spritesheet(client):
    """M11.3 patch A — chainAdd 초기화 dict 에도 chat_spritesheet 키 포함."""
    r = client.get("/settings")
    assert r.status_code == 200
    body = r.text
    assert "chainAdd:" in body
    idx = body.index("chainAdd:")
    end = body.index("}", idx)
    snippet = body[idx:end]
    assert "chat_spritesheet" in snippet, "chainAdd 에 chat_spritesheet 누락"


def test_settings_page_shows_current_backend_state(client, web_deps):
    """gemini 가 enabled + api_key 셋팅된 상태가 페이지에 반영."""
    web_deps.config.backends["gemini"]["enabled"] = True
    web_deps.config.backends["gemini"]["api_key"] = "AIzaInPage"
    r = client.get("/settings")
    assert r.status_code == 200
    # Alpine 데이터 모델 또는 input value 로 표출
    assert "AIzaInPage" in r.text


def test_settings_page_ko_translates_m11_msgids(client, web_deps):
    """ko 로케일 — M11 신규 msgid 가 한글 번역으로 렌더링."""
    web_deps.config.ui_language = "ko"
    r = client.get("/settings", headers={"Accept-Language": "ko"})
    assert r.status_code == 200
    body = r.text
    # 신규 msgid 의 한글 번역어 존재 확인
    assert "백엔드" in body
    assert "이미지 체인" in body
    assert "연결 테스트" in body


def test_settings_page_en_keeps_english(client, web_deps):
    """en 로케일 — 영문 그대로 렌더링."""
    web_deps.config.ui_language = "en"
    r = client.get("/settings", headers={"Accept-Language": "en"})
    assert r.status_code == 200
    body = r.text
    assert "Backends" in body
    assert "Image chain" in body
    assert "Test connection" in body


# ---- backend-help-cards partial 통합 (M11 후속) ----


def test_settings_page_includes_ko_partial_for_gemini(client, web_deps):
    """ko locale 일 때 gemini 카드의 details block 안에 ko partial 본문 포함."""
    web_deps.config.ui_language = "ko"
    r = client.get("/settings", headers={"Accept-Language": "ko"})
    assert r.status_code == 200
    body = r.text
    # gemini ko partial 의 식별 가능한 본문
    assert "무료 tier 있음" in body
    assert "gemini-3.1-flash-lite" in body
    # setup link label (i18n msgid)
    assert "Google AI Studio" in body


def test_settings_page_includes_en_partial_for_openai(client, web_deps):
    """en locale 일 때 openai 카드의 details block 안에 en partial 본문 포함.

    M11.9: claude→openai 로 backend swap (claude help partial 6 파일 삭제됨).
    """
    web_deps.config.ui_language = "en"
    r = client.get("/settings", headers={"Accept-Language": "en"})
    assert r.status_code == 200
    body = r.text
    # openai en partial 의 식별 가능한 본문
    assert "OpenAI Platform" in body
