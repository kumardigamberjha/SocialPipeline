"""
YouTube script pipeline HTTP + WebSocket router.

Mirrors app/routers/linkedin.py: the pipeline runs in a Celery worker (queue
``youtube_queue``) with a BackgroundTasks fallback when Redis is down; the
WebSocket polls SQLite ``task_steps`` on a 2-second cadence.

Two routers are exported:
  - ``router``    : REST endpoints under /api/youtube
  - ``ws_router`` : the WebSocket under /api/ws/youtube/{client_id}
Both are registered in app.main.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.auth_deps import get_current_user
from app.db import queries
from app.services.dispatch import YOUTUBE_QUEUE, run_youtube_fallback, should_use_celery
from app.tasks.youtube_task import run_youtube_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/youtube", tags=["youtube"])
ws_router = APIRouter(prefix="/api/ws", tags=["youtube"])


class GenerateRequest(BaseModel):
    topic: str
    niche: str = "ai"
    provider: str = "nvidia"
    video_format: str = "full"  # 'short' | 'full'


def _dispatch(user_id: str, topic: str, niche: str, provider: str, video_format: str,
              background_tasks: BackgroundTasks) -> dict:
    """Enforce usage, create a run, and dispatch the Celery task onto the
    YouTube queue. Falls back to BackgroundTasks if Redis fails."""
    queries.reset_usage_if_expired(user_id)
    usage = queries.get_usage(user_id)
    if not usage:
        queries.init_usage(user_id)
        usage = queries.get_usage(user_id)
    if usage and usage["runs_this_month"] >= usage["max_runs_per_month"]:
        raise HTTPException(status_code=429, detail="Usage limit exceeded for this month.")

    run = queries.create_run(user_id, topic, provider)
    run_id = run["id"]

    dispatched_to_celery = False
    if should_use_celery(YOUTUBE_QUEUE):
        try:
            run_youtube_pipeline.apply_async(
                args=[run_id, topic, niche, user_id, provider, video_format],
                queue=YOUTUBE_QUEUE,
                ignore_result=True,
            )
            dispatched_to_celery = True
        except Exception as exc:
            logger.warning("Celery dispatch failed, falling back to BackgroundTasks: %s", exc)

    if not dispatched_to_celery:
        logger.info("Running YouTube pipeline in-process (no Celery worker) ▸ run_id=%s", run_id)
        background_tasks.add_task(run_youtube_fallback, run_id, topic, niche, user_id, provider, video_format)

    return {"run_id": run_id, "status": "queued", "message": "YouTube script pipeline started"}


@router.post("/generate")
def generate_youtube_script(request: GenerateRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    return _dispatch(current_user["id"], request.topic, request.niche, request.provider, request.video_format, background_tasks)


@router.get("/scripts")
def list_youtube_scripts(current_user: dict = Depends(get_current_user)):
    # get_youtube_scripts already omits the script body for the list view.
    return queries.get_youtube_scripts(current_user["id"], limit=50)


@router.get("/scripts/{script_id}")
def get_youtube_script(script_id: str, current_user: dict = Depends(get_current_user)):
    script = queries.get_youtube_script_by_id(script_id, current_user["id"])
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


@router.delete("/scripts/{script_id}")
def delete_youtube_script(script_id: str, current_user: dict = Depends(get_current_user)):
    success = queries.soft_delete_youtube_script(script_id, current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Script not found or already deleted")
    return {"message": "Script deleted"}


# ── WebSocket: /api/ws/youtube/{client_id} ────────────────────────────────────


@ws_router.websocket("/youtube/{client_id}")
async def youtube_websocket(websocket: WebSocket, client_id: str, token: str | None = None):
    """Stream YouTube pipeline progress. ``client_id`` is the run_id."""
    await websocket.accept()
    run_id = client_id
    last_step_id = 0

    try:
        while True:
            for step in queries.get_new_steps_since(run_id, last_step_id):
                last_step_id = max(last_step_id, step["id"])
                await websocket.send_json({
                    "type": "agent_update",
                    "agent": step["agent_name"],
                    "task": step["task_name"],
                })

            run = queries.get_run_by_id(run_id)
            if run and run["status"] in ("completed", "failed"):
                if run["status"] == "completed":
                    saved = queries.get_youtube_scripts_by_run_id(run_id)
                    script = saved[-1] if saved else None
                    await websocket.send_json({
                        "type": "complete",
                        "title": script["title"] if script else "",
                        "script": script["script"] if script else (run.get("final_result") or ""),
                        "word_count": script["word_count"] if script else 0,
                        "seo_title": script["seo_title"] if script else "",
                        "seo_description": script["seo_description"] if script else "",
                        "seo_tags": json.loads(script["seo_tags"]) if script and script["seo_tags"] else [],
                        "approved": bool(script["approved"]) if script else False,
                    })
                else:
                    await websocket.send_json({"type": "error", "message": "Pipeline failed"})
                break

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        logger.info("YouTube WS client disconnected: run_id=%s", run_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("YouTube WS error for run_id=%s: %s", run_id, exc)
        try:
            await websocket.send_json({"type": "error", "message": "stream error"})
        except Exception:
            pass
