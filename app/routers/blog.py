"""
Blog pipeline HTTP + WebSocket router.

The 5-agent blog pipeline runs in a dedicated Celery worker (queue
``blog_queue``), so the WebSocket cannot stream from an in-process task. Instead
it polls the SQLite ``task_steps`` the worker writes (a 2-second cadence) and
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

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.auth_deps import get_current_user
from app.db import queries

from app.tasks.blog_task import run_blog_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/blog", tags=["blog"])
ws_router = APIRouter(prefix="/api/ws", tags=["blog"])

BLOG_QUEUE = "blog_queue"

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
def generate_blog(request: GenerateRequest, current_user: dict = Depends(get_current_user)):
    """Enforce the monthly usage cap, create a run, and dispatch the pipeline."""
    user_id = current_user["id"]

    queries.reset_usage_if_expired(user_id)
    usage = queries.get_usage(user_id)
    if not usage:
        queries.init_usage(user_id)
        usage = queries.get_usage(user_id)
    if usage and usage["runs_this_month"] >= usage["max_runs_per_month"]:
        raise HTTPException(status_code=429, detail="Usage limit exceeded for this month.")

    run = queries.create_run(user_id, request.topic, request.provider)
    run_id = run["id"]

    run_blog_pipeline.apply_async(
        args=[run_id, request.topic, request.target_keyword, user_id, request.provider],
        queue=BLOG_QUEUE,
    )
    return {"run_id": run_id, "status": "queued", "message": "Blog pipeline started"}


@router.get("/posts")
def list_blog_posts(current_user: dict = Depends(get_current_user)):
    """Metadata-only list of the user's posts (no ``content`` field)."""
    posts = queries.get_blog_posts(current_user["id"], limit=50)
    return [{k: p.get(k) for k in _LIST_FIELDS} for p in posts]


@router.get("/posts/{blog_id}")
def get_blog_post(blog_id: str, current_user: dict = Depends(get_current_user)):
    post = queries.get_blog_by_id(blog_id, current_user["id"])
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return post


@router.get("/view/{slug}")
def view_blog_post(slug: str):
    """Public endpoint — render a post by slug, no authentication required."""
    post = queries.get_blog_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return post


@router.delete("/posts/{blog_id}")
def delete_blog_post(blog_id: str, current_user: dict = Depends(get_current_user)):
    success = queries.soft_delete_blog(blog_id, current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Blog post not found or already deleted")
    return {"message": "Blog post deleted"}


# ── WebSocket: /api/ws/blog/{client_id}?token={jwt} ───────────────────────────


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
async def blog_websocket(websocket: WebSocket, client_id: str, token: str | None = None):
    """Stream blog pipeline progress. ``client_id`` is the run_id."""
    await websocket.accept()
    run_id = client_id
    last_step_id = 0

    try:
        while True:
            for step in queries.get_new_steps_since(run_id, last_step_id):
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

            run = queries.get_run_by_id(run_id)
            if run and run["status"] in ("completed", "failed"):
                if run["status"] == "completed":
                    saved = queries.get_blog_posts_by_run_id(run_id)
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

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        logger.info("Blog WS client disconnected: run_id=%s", run_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Blog WS error for run_id=%s: %s", run_id, exc)
        try:
            await websocket.send_json({"type": "error", "message": "stream error"})
        except Exception:
            pass
