import asyncio
import json
import logging
import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.config import Settings, get_settings
from app.db import queries
from app.ws_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ws", tags=["websocket"])

DUMMY_USER_ID = "00000000-0000-0000-0000-000000000000"


def _extract_user_id(websocket: WebSocket, settings: Settings) -> str:
    """Extract user_id from the ?token= query parameter via JWT verification."""
    token = websocket.query_params.get("token")
    if token:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
            user_id = payload.get("sub")
            if user_id:
                return user_id
        except jwt.PyJWTError:
            logger.warning("Invalid or expired JWT token provided on WebSocket connect")
    return DUMMY_USER_ID


@router.websocket("/generate/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    settings: Settings = Depends(get_settings),
):
    await manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                topic = payload.get("topic")
                provider = payload.get("provider", settings.default_provider)

                if not topic:
                    await manager.send_json({"type": "error", "message": "Topic is required"}, client_id)
                    continue

                user_id = _extract_user_id(websocket, settings)

                from app.services.usage import check_and_increment
                allowed, msg = check_and_increment(user_id)
                if not allowed:
                    await manager.send_json({"type": "error", "message": msg}, client_id)
                    continue

                # Create run in SQLite
                run = queries.create_run(user_id, topic, provider)
                run_id = run['id']

                # Dispatch pipeline natively via asyncio.create_task
                from app.crew import run_pipeline_streaming
                asyncio.create_task(
                    run_pipeline_streaming(
                        topic=topic,
                        settings=settings,
                        provider=provider,
                        client_id=client_id,
                        run_id=run_id,
                        auto_research=False,
                        user_id=user_id
                    )
                )

            except json.JSONDecodeError:
                await manager.send_json({"type": "error", "message": "Invalid JSON"}, client_id)
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info("Client %s disconnected", client_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        manager.disconnect(client_id)


@router.websocket("/auto-generate/{client_id}")
async def auto_generate_endpoint(
    websocket: WebSocket,
    client_id: str,
    settings: Settings = Depends(get_settings),
):
    await manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                provider = payload.get("provider", settings.default_provider)

                user_id = _extract_user_id(websocket, settings)

                from app.services.usage import check_and_increment
                allowed, msg = check_and_increment(user_id)
                if not allowed:
                    await manager.send_json({"type": "error", "message": msg}, client_id)
                    continue

                from app.crew import run_pipeline_streaming
                from app.db.content_tracker import rotate_niche
                from app.services import saved_topic_service

                # auto_select_topic() no longer runs on the happy path, so the
                # niche is rotated here instead — exactly once per click.
                niche = rotate_niche()

                # Research one candidate set: [0] is generated now, the rest are
                # parked as an "uncovered" backlog the user can return to.
                candidates = []
                try:
                    await manager.send_json({
                        "type": "agent_update",
                        "agent": "Topic Research",
                        "output": "Researching candidate topics…",
                    }, client_id)
                    candidates = await saved_topic_service.research_candidates(
                        user_id=user_id, provider=provider, niche=niche,
                    )
                except Exception:
                    # The suggester must never break the button — fall back to
                    # the original seed-bank behaviour below.
                    logger.exception("Candidate research failed; falling back to auto_select_topic")

                if candidates:
                    chosen = candidates[0]["topic"]
                    run_id = queries.create_run(user_id, chosen, provider)["id"]
                    saved = saved_topic_service.save_candidates(
                        user_id, candidates[1:], niche, source_run_id=run_id,
                    )
                    if saved:
                        await manager.send_json(
                            {"type": "saved_topics", "count": saved}, client_id
                        )
                    asyncio.create_task(
                        run_pipeline_streaming(
                            topic=chosen,
                            settings=settings,
                            provider=provider,
                            client_id=client_id,
                            run_id=run_id,
                            auto_research=False,   # topic already chosen
                            niche=niche,
                            user_id=user_id,
                        )
                    )
                else:
                    # Fallback: original behaviour, topic picked from the seed
                    # banks inside the pipeline.
                    run_id = queries.create_run(user_id, "Auto-research (seed banks)", provider)["id"]
                    asyncio.create_task(
                        run_pipeline_streaming(
                            topic="auto",
                            settings=settings,
                            provider=provider,
                            client_id=client_id,
                            run_id=run_id,
                            auto_research=True,
                            user_id=user_id,
                        )
                    )

            except json.JSONDecodeError:
                await manager.send_json({"type": "error", "message": "Invalid JSON"}, client_id)
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info("Auto-generate client %s disconnected", client_id)
    except Exception as e:
        logger.error("Auto-generate WebSocket error: %s", e)
        manager.disconnect(client_id)


@router.websocket("/blog/{client_id}")
async def blog_endpoint(
    websocket: WebSocket,
    client_id: str,
    settings: Settings = Depends(get_settings),
):
    """Stream long-form blog generation.

    Client sends {"topic": "...", "provider": "...", "niche": "..."}.
    Server emits: status, section_started, section_complete (with word_count),
    blog_complete (full markdown + word_count + reading_time), error.
    """
    await manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                topic = payload.get("topic")
                provider = payload.get("provider", settings.default_provider)
                niche = payload.get("niche", "AI / Software Development")

                if not topic:
                    await manager.send_json({"type": "error", "message": "Topic is required"}, client_id)
                    continue

                user_id = _extract_user_id(websocket, settings)

                from app.services.usage import check_and_increment
                allowed, msg = check_and_increment(user_id)
                if not allowed:
                    await manager.send_json({"type": "error", "message": msg}, client_id)
                    continue

                # Create run in SQLite
                run = queries.create_run(user_id, topic, provider)
                run_id = run['id']

                # Dispatch blog generation natively via asyncio.create_task
                from app.crew import run_blog_pipeline_streaming
                asyncio.create_task(
                    run_blog_pipeline_streaming(
                        topic=topic,
                        settings=settings,
                        provider=provider,
                        client_id=client_id,
                        run_id=run_id,
                        user_id=user_id,
                        niche=niche,
                    )
                )

            except json.JSONDecodeError:
                await manager.send_json({"type": "error", "message": "Invalid JSON"}, client_id)
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info("Blog client %s disconnected", client_id)
    except Exception as e:
        logger.error("Blog WebSocket error: %s", e)
        manager.disconnect(client_id)
