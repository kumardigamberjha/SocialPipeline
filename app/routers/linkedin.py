"""
LinkedIn pipeline HTTP + WebSocket router.

The pipeline runs in a dedicated Celery worker (queue ``linkedin_queue``), so the
WebSocket cannot stream from an in-process task the way the main pipeline does.
Instead it polls the ``task_steps`` rows the worker writes (a 2-second cadence)
and emits structured events to the client.

Two routers are exported:
  - ``router``    : REST endpoints under /api/linkedin
  - ``ws_router`` : the WebSocket under /api/ws/linkedin/{client_id}
Both are registered in app.main.
"""

import ast
import asyncio
import json
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

from app.config import get_settings
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

router = APIRouter(prefix="/api/linkedin", tags=["linkedin"])
ws_router = APIRouter(prefix="/api/ws", tags=["linkedin"])


class GenerateRequest(BaseModel):
    topic: str
    niche: str = "ai"
    provider: str = "nvidia"


async def _dispatch(
    session: AsyncSession,
    user_id: str,
    topic: str,
    niche: str,
    provider: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Shared launch logic for /generate and /regenerate.

    Enforces the monthly cap, creates the run, and hands off to the shared
    dispatcher. The in-process fallback used to be re-implemented here as a
    third copy of the pipeline body; it now lives in one place.
    """
    if os.getenv("ENABLE_USAGE_LIMITS", "false").lower() in ("true", "1"):
        await queries.reset_usage_if_expired(session, user_id)
        usage = await queries.get_usage(session, user_id)
        if not usage:
            await queries.init_usage(session, user_id)
            usage = await queries.get_usage(session, user_id)
        if usage and usage.get("max_runs_per_month") and usage["runs_this_month"] >= usage["max_runs_per_month"]:
            raise HTTPException(status_code=429, detail="Usage limit exceeded for this month.")

    run = await queries.create_run(session, user_id, topic, provider)
    run_id = run["id"]

    dispatch_pipeline(
        content_type="linkedin",
        run_id=run_id,
        topic=topic,
        niche=niche,
        user_id=user_id,
        provider=provider,
        video_format="full",
        background_tasks=background_tasks,
    )
    return {"run_id": run_id, "status": "queued", "message": "LinkedIn pipeline started"}


@router.post("/generate")
async def generate_linkedin_post(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _dispatch(
        session, current_user["id"], request.topic, request.niche,
        request.provider, background_tasks,
    )


@router.get("/posts")
async def list_linkedin_posts(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # get_linkedin_posts already omits post_text for the list view.
    return await queries.get_linkedin_posts(session, current_user["id"], limit=50)


@router.get("/posts/{post_id}")
async def get_linkedin_post(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    post = await queries.get_linkedin_post_by_id(session, post_id, current_user["id"])
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.delete("/posts/{post_id}")
async def delete_linkedin_post(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await queries.soft_delete_linkedin_post(session, post_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Post not found or already deleted")
    return {"message": "Post deleted"}


@router.post("/regenerate/{post_id}")
async def regenerate_linkedin_post(
    post_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Re-run the pipeline on the same topic with a fresh angle. Creates a NEW
    post row (the original is left untouched)."""
    user_id = current_user["id"]
    post = await queries.get_linkedin_post_by_id(session, post_id, user_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Reuse the provider from the original run when we can, else fall back.
    provider = get_settings().default_provider or "nvidia"
    if post.get("run_id"):
        original_run = await queries.get_run_by_id(session, post["run_id"], user_id)
        if original_run and original_run.get("provider_used"):
            provider = original_run["provider_used"]

    return await _dispatch(
        session, user_id, post["topic"], post.get("niche") or "ai",
        provider, background_tasks,
    )


# ── WebSocket: /api/ws/linkedin/{client_id} ───────────────────────────────────


def _parse_step_output(output_str: str) -> dict | None:
    """Step outputs are stored as either a Python dict repr (QA checker) or a
    JSON string (pydantic model_dump_json). Try both, safely."""
    if not output_str:
        return None
    try:
        return json.loads(output_str)
    except (ValueError, TypeError):
        pass
    try:
        parsed = ast.literal_eval(output_str)
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, SyntaxError):
        return None


@ws_router.websocket("/linkedin/{client_id}")
async def linkedin_websocket(
    websocket: WebSocket,
    client_id: str,
    user: dict = Depends(get_current_user_ws),
    session: AsyncSession = Depends(get_session),
):
    """Stream LinkedIn pipeline progress. ``client_id`` is the run_id.

    Authenticated before ``accept()`` and scoped to the run's owner. The
    previous version took an unused ``token`` parameter and streamed the full
    generated post to anyone who supplied a run_id.
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
                agent_name = step["agent_name"]
                task_name = step["task_name"]

                if agent_name == "QA Checker":
                    qa_data = _parse_step_output(step["output"]) or {}
                    cycle = "final" if "Final" in task_name else task_name.split(" ")[-1]
                    await websocket.send_json({
                        "type": "qa_result",
                        "cycle": cycle,
                        "overall_pass": qa_data.get("overall_pass", False),
                        "word_count": qa_data.get("word_count", 0),
                        "violations": qa_data.get("long_lines", []) + qa_data.get("banned_words_found", []),
                    })
                else:
                    await websocket.send_json({
                        "type": "agent_update",
                        "agent": agent_name,
                        "task": task_name,
                    })

            run = await queries.get_run_by_id(session, run_id, user_id)
            if run and run["status"] in ("completed", "failed"):
                if run["status"] == "completed":
                    saved = await queries.get_linkedin_posts_by_run_id(
                        session, run_id, user_id
                    )
                    post = saved[-1] if saved else None
                    await websocket.send_json({
                        "type": "complete",
                        "post_text": post["post_text"] if post else (run.get("final_result") or ""),
                        "hook": post["hook"] if post else "",
                        "word_count": post["word_count"] if post else 0,
                        "approved": bool(post["approved"]) if post else False,
                    })
                else:
                    await websocket.send_json({"type": "error", "message": "Pipeline failed"})
                break

            await asyncio.sleep(2)

    except (WebSocketDisconnect, WebSocketAuthError):
        logger.info("LinkedIn WS client disconnected: run_id=%s", run_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("LinkedIn WS error for run_id=%s: %s", run_id, exc)
        try:
            await websocket.send_json({"type": "error", "message": "stream error"})
        except Exception:
            pass
