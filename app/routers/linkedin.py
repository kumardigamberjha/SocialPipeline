"""
LinkedIn pipeline HTTP + WebSocket router.

The pipeline runs in a dedicated Celery worker (queue ``linkedin_queue``), so the
WebSocket cannot stream from an in-process task the way the blog/main pipelines do.
Instead it polls the SQLite ``task_steps`` the worker writes (the same 2-second
polling cadence) and emits structured events to the client.

Two routers are exported:
  - ``router``    : REST endpoints under /api/linkedin
  - ``ws_router`` : the WebSocket under /api/ws/linkedin/{client_id}
Both are registered in app.main.
"""

import ast
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from pydantic import BaseModel
import time

from app.config import get_settings
from app.core.auth_deps import get_current_user
from app.db import queries
from app.tasks.linkedin_task import run_linkedin_pipeline
from app.services.linkedin_pipeline import LinkedInPipelineOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/linkedin", tags=["linkedin"])
ws_router = APIRouter(prefix="/api/ws", tags=["linkedin"])

LINKEDIN_QUEUE = "linkedin_queue"


class GenerateRequest(BaseModel):
    topic: str
    niche: str = "ai"
    provider: str = "nvidia"


def _run_linkedin_fallback(run_id: str, topic: str, niche: str, user_id: str, provider: str):
    try:
        queries.update_run_status(run_id, "running")
        start = time.time()

        def step_callback(agent_name: str, task_name: str, output: str):
            queries.insert_task_step(run_id, agent_name, task_name, str(output))

        orchestrator = LinkedInPipelineOrchestrator(
            llm_provider=provider,
            run_id=run_id,
            step_callback=step_callback,
        )
        result = asyncio.run(orchestrator.run(topic, niche, user_id))

        duration = round(time.time() - start, 2)
        queries.save_linkedin_post(
            run_id=run_id,
            user_id=user_id,
            topic=topic,
            post_text=result["post_text"],
            hook=result["hook"],
            angle_type=result["angle_type"],
            word_count=result["word_count"],
            approved=result["approved"],
            niche=niche,
        )
        queries.update_run_status(run_id, "completed", final_result=result["post_text"], duration=duration)
        queries.increment_usage(user_id)
        logger.info("LinkedIn pipeline DONE (fallback) ▸ run_id=%s duration=%.2fs approved=%s", run_id, duration, result["approved"])

    except Exception as exc:
        logger.exception("LinkedIn pipeline FAILED (fallback) ▸ run_id=%s", run_id)
        queries.update_run_status(run_id, "failed")


import redis

def _is_redis_available() -> bool:
    try:
        r = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        return r.ping()
    except Exception:
        return False

def _dispatch(user_id: str, topic: str, niche: str, provider: str, background_tasks: BackgroundTasks) -> dict:
    """Shared launch logic for /generate and /regenerate: enforce usage, create a
    run, and dispatch the Celery task onto the LinkedIn queue. Falls back to BackgroundTasks if Redis fails."""
    queries.reset_usage_if_expired(user_id)
    usage = queries.get_usage(user_id)
    if not usage:
        queries.init_usage(user_id)
        usage = queries.get_usage(user_id)
    if usage and usage["runs_this_month"] >= usage["max_runs_per_month"]:
        raise HTTPException(status_code=429, detail="Usage limit exceeded for this month.")

    run = queries.create_run(user_id, topic, provider)
    run_id = run["id"]

    if _is_redis_available():
        try:
            run_linkedin_pipeline.apply_async(
                args=[run_id, topic, niche, user_id, provider],
                queue=LINKEDIN_QUEUE,
                ignore_result=True,
            )
        except Exception as exc:
            logger.warning("Redis connection failed for Celery, falling back to BackgroundTasks. Error: %s", exc)
            background_tasks.add_task(
                _run_linkedin_fallback,
                run_id, topic, niche, user_id, provider
            )
    else:
        logger.warning("Redis not available, falling back to BackgroundTasks.")
        background_tasks.add_task(
            _run_linkedin_fallback,
            run_id, topic, niche, user_id, provider
        )
        
    return {"run_id": run_id, "status": "queued", "message": "LinkedIn pipeline started"}


@router.post("/generate")
def generate_linkedin_post(request: GenerateRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    return _dispatch(current_user["id"], request.topic, request.niche, request.provider, background_tasks)


@router.get("/posts")
def list_linkedin_posts(current_user: dict = Depends(get_current_user)):
    # get_linkedin_posts already omits post_text for the list view.
    return queries.get_linkedin_posts(current_user["id"], limit=50)


@router.get("/posts/{post_id}")
def get_linkedin_post(post_id: str, current_user: dict = Depends(get_current_user)):
    post = queries.get_linkedin_post_by_id(post_id, current_user["id"])
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.delete("/posts/{post_id}")
def delete_linkedin_post(post_id: str, current_user: dict = Depends(get_current_user)):
    success = queries.soft_delete_linkedin_post(post_id, current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Post not found or already deleted")
    return {"message": "Post deleted"}


@router.post("/regenerate/{post_id}")
def regenerate_linkedin_post(post_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """Re-run the pipeline on the same topic with a fresh angle. Creates a NEW
    post row (the original is left untouched)."""
    post = queries.get_linkedin_post_by_id(post_id, current_user["id"])
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Reuse the provider from the original run when we can, else fall back.
    provider = get_settings().default_provider or "nvidia"
    original_run = queries.get_run_by_id(post.get("run_id")) if post.get("run_id") else None
    if original_run and original_run.get("provider_used"):
        provider = original_run["provider_used"]

    return _dispatch(current_user["id"], post["topic"], post.get("niche") or "ai", provider, background_tasks)


# ── WebSocket: /api/ws/linkedin/{client_id}?token={jwt} ───────────────────────


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
async def linkedin_websocket(websocket: WebSocket, client_id: str, token: str | None = None):
    """Stream LinkedIn pipeline progress. ``client_id`` is the run_id."""
    await websocket.accept()
    run_id = client_id
    last_step_id = 0

    try:
        while True:
            for step in queries.get_new_steps_since(run_id, last_step_id):
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

            run = queries.get_run_by_id(run_id)
            if run and run["status"] in ("completed", "failed"):
                if run["status"] == "completed":
                    saved = queries.get_linkedin_posts_by_run_id(run_id)
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

    except WebSocketDisconnect:
        logger.info("LinkedIn WS client disconnected: run_id=%s", run_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("LinkedIn WS error for run_id=%s: %s", run_id, exc)
        try:
            await websocket.send_json({"type": "error", "message": "stream error"})
        except Exception:
            pass
