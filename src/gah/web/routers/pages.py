"""M5 — HTML 페이지 라우트 (라우터 prefix 없음).

`/` 는 `/library` 로 redirect. 각 페이지가 `base.html` 을 extend.
"""
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse


router = APIRouter(tags=["pages"])


@router.get("/", include_in_schema=False)
def page_root():
    """루트 경로 → 라이브러리 페이지로 리다이렉트."""
    return RedirectResponse(url="/library", status_code=307)


@router.get("/library", response_class=HTMLResponse)
def page_library(request: Request) -> HTMLResponse:
    """라이브러리 페이지 — 검색 바 + 결과 영역 + 사이드 패널 placeholder."""
    templates = request.app.state.templates
    deps = request.app.state.deps
    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={"deps": deps, "page": "library"},
    )


@router.get("/packs", response_class=HTMLResponse)
def page_packs(request: Request) -> HTMLResponse:
    """팩 페이지 — 팩 카드 그리드 + enable/disable 토글.

    packs 를 인라인으로 렌더해 초기 로드 시 추가 왕복을 없앤다.
    """
    from .packs import _list_packs_dicts  # 순환 import 방지용 지연 import

    templates = request.app.state.templates
    deps = request.app.state.deps
    packs = _list_packs_dicts(deps.store)
    return templates.TemplateResponse(
        request=request,
        name="packs.html",
        context={"packs": packs, "page": "packs"},
    )


# /labels/admin 은 Phase 5B 가 채움
