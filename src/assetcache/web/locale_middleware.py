"""M8 — locale 결정 5단계 미들웨어 + ContextVar.

우선순위 (위가 우선):
  1. URL ?lang=ko|en
  2. 쿠키 assetcache_locale
  3. Config.ui_language (≠ "auto")
  4. Accept-Language 헤더 (Config.ui_language == "auto" 일 때)
  5. 폴백 "ko"

middleware 가 결정한 값을 `request.state.locale` + ContextVar `current_locale`
에 set. Jinja2 의 `_()` 가 ContextVar 를 읽어 현재 locale 로 번역.
"""
from __future__ import annotations

from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .i18n import SUPPORTED_LOCALES as SUPPORTED

current_locale: ContextVar[str] = ContextVar("gah_current_locale", default="ko")


class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        locale = self._resolve(request)
        request.state.locale = locale
        token = current_locale.set(locale)
        try:
            response = await call_next(request)
        finally:
            current_locale.reset(token)
        return response

    def _resolve(self, request: Request) -> str:
        # 1. URL ?lang=
        q = request.query_params.get("lang")
        if q in SUPPORTED:
            return q
        # 2. 쿠키
        c = request.cookies.get("assetcache_locale")
        if c in SUPPORTED:
            return c
        # 3. Config.ui_language
        cfg = getattr(request.app.state, "config", None)
        cfg_lang = getattr(cfg, "ui_language", "auto") if cfg else "auto"
        if cfg_lang in SUPPORTED:
            return cfg_lang
        # 4. Accept-Language
        accept = request.headers.get("accept-language", "")
        for raw in accept.split(","):
            tag = raw.split(";")[0].strip().lower()
            if tag.startswith("en"):
                return "en"
            if tag.startswith("ko"):
                return "ko"
        # 5. 폴백
        return "ko"
