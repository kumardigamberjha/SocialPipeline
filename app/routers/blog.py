"""
Blog pipeline HTTP + WebSocket router.

The 5-agent blog pipeline runs in a dedicated Celery worker (queue
``blog_queue``), so the WebSocket cannot stream from an in-process task. Instead
it polls the ``task_steps`` rows the worker writes (a 2-second cadence) and
emits structured events to the client.

Two routers are exported:
  - ``router``    : REST endpoints under /api/blog
  - ``ws_router`` : the WebSocket under /api/ws/blog/{client_id}
Both are registered in app.main.
"""

import ast
import asyncio
import json
import logging
import re

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

router = APIRouter(prefix="/api/blog", tags=["blog"])
ws_router = APIRouter(prefix="/api/ws", tags=["blog"])

# Fields returned for the list view (the full ``content`` is intentionally omitted).
_LIST_FIELDS = (
    "id", "title", "topic", "word_count", "reading_time_minutes",
    "approved", "published_at", "slug",
)


class GenerateRequest(BaseModel):
    topic: str
    target_keyword: str
    provider: str = "nvidia"


# ── REST ──────────────────────────────────────────────────────────────────────


@router.post("/generate")
async def generate_blog(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Enforce the monthly usage cap, create a run, and dispatch the pipeline."""
    user_id = current_user["id"]

    if os.getenv("ENABLE_USAGE_LIMITS", "false").lower() in ("true", "1"):
        await queries.reset_usage_if_expired(session, user_id)
        usage = await queries.get_usage(session, user_id)
        if not usage:
            await queries.init_usage(session, user_id)
            usage = await queries.get_usage(session, user_id)
        if usage and usage.get("max_runs_per_month") and usage["runs_this_month"] >= usage["max_runs_per_month"]:
            raise HTTPException(status_code=429, detail="Usage limit exceeded for this month.")

    run = await queries.create_run(session, user_id, request.topic, request.provider)
    run_id = run["id"]

    # The Celery-vs-in-process decision, queue name and task signature all live
    # in dispatch_pipeline, so this router cannot drift from the others.
    dispatch_pipeline(
        content_type="blog",
        run_id=run_id,
        topic=request.topic,
        niche=request.target_keyword,
        user_id=user_id,
        provider=request.provider,
        video_format="full",
        background_tasks=background_tasks,
    )
    return {"run_id": run_id, "status": "queued", "message": "Blog pipeline started"}


@router.get("/posts")
async def list_blog_posts(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Metadata-only list of the user's posts (no ``content`` field)."""
    posts = await queries.get_blog_posts(session, current_user["id"], limit=50)
    return [{k: p.get(k) for k in _LIST_FIELDS} for p in posts]


@router.get("/posts/{blog_id}")
async def get_blog_post(
    blog_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    post = await queries.get_blog_by_id(session, blog_id, current_user["id"])
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return post


@router.get("/view/{slug}")
async def view_blog_post(slug: str, session: AsyncSession = Depends(get_session)):
    """Public endpoint — render a post by slug, no authentication required.

    One of the few genuinely public routes; see PUBLIC_ROUTES in app.main.
    """
    post = await queries.get_public_blog_by_slug(session, slug)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return post


@router.delete("/posts/{blog_id}")
async def delete_blog_post(
    blog_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await queries.soft_delete_blog(session, blog_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Blog post not found or already deleted")
    return {"message": "Blog post deleted"}


# ── WebSocket: /api/ws/blog/{client_id} ───────────────────────────────────────


def _parse_step_output(output_str: str) -> dict | None:
    """Step outputs are stored as either a JSON string (pydantic model_dump_json)
    or a Python dict repr. Try both, safely."""
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


def _heading_from_task(task_name: str) -> str:
    """Extract the section heading from a Writer/Editor task label.

    'Write: Introduction'         -> 'Introduction'
    'Edit cycle 2: Introduction'  -> 'Introduction'
    """
    return task_name.split(":", 1)[1].strip() if ":" in task_name else task_name


def _cycle_from_task(task_name: str) -> int | None:
    match = re.search(r"cycle\s+(\d+)", task_name, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


@ws_router.websocket("/blog/{client_id}")
async def blog_websocket(
    websocket: WebSocket,
    client_id: str,
    user: dict = Depends(get_current_user_ws),
    session: AsyncSession = Depends(get_session),
):
    """Stream blog pipeline progress. ``client_id`` is the run_id.

    Previously this accepted any connection and streamed the full generated
    article to whoever named a run_id — it declared a ``token`` parameter and
    never read it. The socket is now authenticated before ``accept()`` and the
    run must belong to the caller.
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

                if agent_name == "QA Assembler":
                    data = _parse_step_output(step["output"]) or {}
                    await websocket.send_json({
                        "type": "qa_result",
                        "total_words": data.get("total_word_count", 0),
                        "thin_sections": data.get("thin_sections", []),
                        "keyword_density": data.get("keyword_density", 0.0),
                        "approved": False,
                    })
                elif agent_name == "Editor":
                    cycle = _cycle_from_task(task_name)
                    heading = _heading_from_task(task_name)
                    await websocket.send_json({
                        "type": "agent_update",
                        "agent": agent_name,
                        "task": task_name,
                        "cycle": cycle,
                    })
                    data = _parse_step_output(step["output"]) or {}
                    body = data.get("revised_body") or ""
                    await websocket.send_json({
                        "type": "section_complete",
                        "heading": heading,
                        "word_count": len(body.split()),
                    })
                else:  # Researcher, Writer, Approver
                    await websocket.send_json({
                        "type": "agent_update",
                        "agent": agent_name,
                        "task": task_name,
                        "cycle": _cycle_from_task(task_name),
                    })

            run = await queries.get_run_by_id(session, run_id, user_id)
            if run and run["status"] in ("completed", "failed"):
                if run["status"] == "completed":
                    saved = await queries.get_blog_posts_by_run_id(
                        session, run_id, user_id
                    )
                    post = saved[-1] if saved else None
                    await websocket.send_json({
                        "type": "complete",
                        "markdown": post["content"] if post else (run.get("final_result") or ""),
                        "word_count": post["word_count"] if post else 0,
                        "approved": bool(post["approved"]) if post else False,
                        "slug": post["slug"] if post else None,
                    })
                else:
                    await websocket.send_json({"type": "error", "message": "Pipeline failed"})
                break

            # The worker writes progress from another process, so this polls
            # rather than subscribing. Phase 4 replaces it with job pub/sub.
            await asyncio.sleep(2)

    except (WebSocketDisconnect, WebSocketAuthError):
        logger.info("Blog WS client disconnected: run_id=%s", run_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Blog WS error for run_id=%s: %s", run_id, exc)
        try:
            await websocket.send_json({"type": "error", "message": "stream error"})
        except Exception:
            pass
