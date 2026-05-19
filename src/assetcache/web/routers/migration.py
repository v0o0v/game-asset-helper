"""마이그레이션 endpoint — /api/migration/{status,run,progress,dismiss}."""

from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from assetcache.core.migration import (
    MigrationCandidate,
    MigrationRunner,
    MigrationState,
    detect_v001_candidate,
)

router = APIRouter(prefix="/api/migration", tags=["migration"])

# task_id → MigrationRunner (in-memory, 앱 프로세스 1개 가정)
_runners: dict[str, MigrationRunner] = {}


class RunRequest(BaseModel):
    mode: Literal["copy", "move"]


def _get_app_paths(request: Request):
    """deps.paths 반환 wrapper — test monkeypatch 용 indirection."""
    return request.app.state.deps.paths


def _serialize_candidate(c: MigrationCandidate) -> dict:
    return {
        "source": str(c.source),
        "target": str(c.target),
        "total_files": c.total_files,
        "total_bytes": c.total_bytes,
        "has_db": c.has_db,
        "has_library": c.has_library,
    }


@router.get("/status")
def status(request: Request):
    candidate = detect_v001_candidate(_get_app_paths(request))
    if candidate is None:
        return {"candidate": None}
    return _serialize_candidate(candidate)


@router.post("/run", status_code=202)
async def run_migration(req: RunRequest, request: Request):
    candidate = detect_v001_candidate(_get_app_paths(request))
    if candidate is None:
        raise HTTPException(status_code=404, detail="no migration candidate")

    runner = MigrationRunner()
    task_id = str(uuid.uuid4())
    _runners[task_id] = runner

    async def _do():
        await runner.run(candidate, mode=req.mode)
        # runner.run 이 마커 + path rewrite 모두 처리 (Task 1.3 통합)

    asyncio.create_task(_do())

    return {"task_id": task_id}


@router.get("/progress")
async def progress(task_id: str):
    runner = _runners.get(task_id)
    if runner is None:
        raise HTTPException(status_code=404, detail="unknown task_id")

    async def event_stream():
        while runner.state in (MigrationState.PENDING, MigrationState.RUNNING):
            yield f'data: {{"state":"{runner.state}","progress":{runner.progress}}}\n\n'
            await asyncio.sleep(0.5)
        if runner.state == MigrationState.DONE:
            yield 'event: done\ndata: {}\n\n'
        else:
            yield f'event: error\ndata: {{"error":"{runner.error}"}}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/dismiss")
def dismiss():
    # 단순 cookie 기반 — 클라이언트에서 처리. 서버는 200 만 반환.
    return JSONResponse({"dismissed": True})
