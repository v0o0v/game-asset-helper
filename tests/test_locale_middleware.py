"""M8 — LocaleMiddleware 5단계 결정 + ContextVar 격리 테스트."""
from __future__ import annotations

from contextvars import copy_context

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from assetcache.config import Config
from assetcache.web.locale_middleware import LocaleMiddleware, current_locale


@pytest.fixture
def app_with_locale(tmp_path):
    app = FastAPI()
    cfg = Config()
    app.state.config = cfg
    app.add_middleware(LocaleMiddleware)

    @app.get("/probe")
    async def probe(request: Request):
        return JSONResponse({"locale": request.state.locale,
                             "ctx": current_locale.get()})
    return app, cfg


def test_locale_url_overrides_all(app_with_locale):
    app, cfg = app_with_locale
    cfg.ui_language = "ko"
    c = TestClient(app)
    r = c.get("/probe?lang=en", headers={"accept-language": "ko"},
              cookies={"assetcache_locale": "ko"})
    assert r.json() == {"locale": "en", "ctx": "en"}


def test_locale_cookie_overrides_config_and_header(app_with_locale):
    app, cfg = app_with_locale
    cfg.ui_language = "ko"
    c = TestClient(app)
    r = c.get("/probe", headers={"accept-language": "ko"},
              cookies={"assetcache_locale": "en"})
    assert r.json()["locale"] == "en"


def test_locale_config_overrides_header(app_with_locale):
    app, cfg = app_with_locale
    cfg.ui_language = "en"
    c = TestClient(app)
    r = c.get("/probe", headers={"accept-language": "ko"})
    assert r.json()["locale"] == "en"


def test_locale_accept_language_used_when_config_auto(app_with_locale):
    app, cfg = app_with_locale
    cfg.ui_language = "auto"
    c = TestClient(app)
    r1 = c.get("/probe", headers={"accept-language": "en-US,en;q=0.9,ko;q=0.5"})
    assert r1.json()["locale"] == "en"
    r2 = c.get("/probe", headers={"accept-language": "ko-KR,ko;q=0.9"})
    assert r2.json()["locale"] == "ko"


def test_locale_falls_back_to_ko(app_with_locale):
    app, cfg = app_with_locale
    cfg.ui_language = "auto"
    c = TestClient(app)
    r = c.get("/probe")
    assert r.json()["locale"] == "ko"


def test_locale_invalid_url_param_ignored(app_with_locale):
    app, cfg = app_with_locale
    cfg.ui_language = "ko"
    c = TestClient(app)
    r = c.get("/probe?lang=klingon")
    assert r.json()["locale"] == "ko"


def test_locale_contextvar_resets_between_requests(app_with_locale):
    app, cfg = app_with_locale
    cfg.ui_language = "ko"
    c = TestClient(app)
    c.get("/probe?lang=en")
    ctx = copy_context()
    assert ctx.run(lambda: current_locale.get("ko")) == "ko"


def test_locale_invalid_cookie_value_ignored(app_with_locale):
    app, cfg = app_with_locale
    cfg.ui_language = "ko"
    c = TestClient(app)
    r = c.get("/probe", cookies={"assetcache_locale": "klingon"})
    assert r.json()["locale"] == "ko"
