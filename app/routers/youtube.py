"""
YouTube script pipeline HTTP + WebSocket router.

Mirrors app/routers/linkedin.py: the pipeline runs in a Celery worker (queue
``youtube_queue``); the WebSocket polls the ``task_steps`` rows the worker
writes on a 2-second cadence.

Two routers are exported:
  - ``router``    : REST endpoints under /api/youtube
  - ``ws_router`` : the WebSocket under /api/ws/youtube/{client_id}
Both are registered in app.main.
"""

import asyncio
import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import (
    WS_FORBIDDEN,
    WebSocketAuthError,
    get_current_user,
    get_current_user_ws,
)
from app.db import queries
from app.db.session import get_session
from app.services.dispatch import dispatch_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/youtube", tags=["youtube"])
ws_router = APIRouter(prefix="/api/ws", tags=["youtube"])


class GenerateRequest(BaseModel):
    topic: str
    niche: str = "ai"
    provider: str = "nvidia"
    video_format: str = "full"  # 'short' | 'full'


async def _dispatch(
    session: AsyncSession,
    user_id: str,
    topic: str,
    niche: str,
    provider: str,
    video_format: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Enforce the monthly cap, create a run, and dispatch the pipeline."""
    await queries.reset_usage_if_expired(session, user_id)
    usage = await queries.get_usage(session, user_id)
    if not usage:
        await queries.init_usage(session, user_id)
        usage = await queries.get_usage(session, user_id)
    if usage and usage["runs_this_month"] >= usage["max_runs_per_month"]:
        raise HTTPException(status_code=429, detail="Usage limit exceeded for this month.")

    run = await queries.create_run(session, user_id, topic, provider)
    run_id = run["id"]

    dispatch_pipeline(
        content_type="youtube_script",
        run_id=run_id,
        topic=topic,
        niche=niche,
        user_id=user_id,
        provider=provider,
        video_format=video_format,
        background_tasks=background_tasks,
    )
    return {"run_id": run_id, "status": "queued", "message": "YouTube script pipeline started"}


@router.post("/generate")
async def generate_youtube_script(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _dispatch(
        session, current_user["id"], request.topic, request.niche,
        request.provider, request.video_format, background_tasks,
    )


@router.get("/scripts")
async def list_youtube_scripts(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # get_youtube_scripts already omits the script body for the list view.
    return await queries.get_youtube_scripts(session, current_user["id"], limit=50)


@router.get("/scripts/{script_id}")
async def get_youtube_script(
    script_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    script = await queries.get_youtube_script_by_id(session, script_id, current_user["id"])
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


@router.delete("/scripts/{script_id}")
async def delete_youtube_script(
    script_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await queries.soft_delete_youtube_script(session, script_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Script not found or already deleted")
    return {"message": "Script deleted"}


# ── WebSocket: /api/ws/youtube/{client_id} ────────────────────────────────────


@ws_router.websocket("/youtube/{client_id}")
async def youtube_websocket(
    websocket: WebSocket,
    client_id: str,
    user: dict = Depends(get_current_user_ws),
    session: AsyncSession = Depends(get_session),
):
    """Stream YouTube pipeline progress. ``client_id`` is the run_id.

    Authenticated before ``accept()`` and scoped to the run's owner.
    """
    run_id = client_id
    user_id = user["id"]

    run = await queries.get_run_by_id(session, run_id, user_id)
    if run is None:
        await websocket.close(code=WS_FORBIDDEN, reason="Unknown run")
        return

    await websocket.accept()
    last_step_id = 0

    try:
        while True:
            for step in await queries.get_new_steps_since(
                session, run_id, user_id, last_step_id
            ):
                last_step_id = max(last_step_id, step["id"])
                await websocket.send_json({
                    "type": "agent_update",
                    "agent": step["agent_name"],
                    "task": step["task_name"],
                })

            run = await queries.get_run_by_id(session, run_id, user_id)
            if run and run["status"] in ("completed", "failed"):
                if run["status"] == "completed":
                    saved = await queries.get_youtube_scripts_by_run_id(
                        session, run_id, user_id
                    )
                    script = saved[-1] if saved else None
                    await websocket.send_json({
                        "type": "complete",
                        "title": script["title"] if script else "",
                        "script": script["script"] if script else (run.get("final_result") or ""),
                        "word_count": script["word_count"] if script else 0,
                        "seo_title": script["seo_title"] if script else "",
                        "seo_description": script["seo_description"] if script else "",
                        # seo_tags is JSONB now — already a list, no json.loads.
                        "seo_tags": (script["seo_tags"] if script else None) or [],
                        "approved": bool(script["approved"]) if script else False,
                    })
                else:
                    await websocket.send_json({"type": "error", "message": "Pipeline failed"})
                break

            await asyncio.sleep(2)

    except (WebSocketDisconnect, WebSocketAuthError):
        logger.info("YouTube WS client disconnected: run_id=%s", run_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("YouTube WS error for run_id=%s: %s", run_id, exc)
        try:
            await websocket.send_json({"type": "error", "message": "stream error"})
        except Exception:
            pass
