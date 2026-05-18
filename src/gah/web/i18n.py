"""M5 — i18n placeholder.

v1 (M5) 은 한국어 하드코딩 + `_t()` passthrough. 본격 i18n 백엔드 (babel
또는 단순 JSON 변환기) 는 M8 에서 도입.
"""
from __future__ import annotations
from typing import Any


def _t(text: str) -> str:
    """현재는 인자를 그대로 반환 (placeholder)."""
    return text


def setup_jinja_i18n(env: Any) -> None:
    """Jinja2 환경에 `_` 글로벌 함수 등록 → 템플릿에서 `{{ _("...") }}`."""
    env.globals["_"] = _t
