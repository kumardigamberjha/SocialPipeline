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
                        auto_research=False
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

                if provider == "ollama":
                    auto_topic = (
                        "LATEST AI TRENDS: Select one of the absolute most trending AI topics today "
                        "(e.g., local LLMs, AI agents, RAG, or new reasoning models). Perform a deep trend analysis "
                        "on it and base every single subsequent task output entirely on that specific topic."
                    )
                else:
                    auto_topic = (
                        "LATEST AI TRENDS: Use your web search tool to find the most breaking, viral AI news from today. "
                        "CRITICAL: When using the web_search tool, do NOT query this entire sentence. "
                        "Use short, specific keywords like 'latest AI trends today' or 'viral tech news 2024'. "
                        "Pick the absolute #1 most viral AI topic right now, perform a deep trend analysis, "
                        "and base every single subsequent task output entirely on that specific topic."
                    )

                # Create run in SQLite
                run = queries.create_run(user_id, auto_topic, provider)
                run_id = run['id']

                # Dispatch pipeline natively via asyncio.create_task
                from app.crew import run_pipeline_streaming
                asyncio.create_task(
                    run_pipeline_streaming(
                        topic=auto_topic,
                        settings=settings,
                        provider=provider,
                        client_id=client_id,
                        run_id=run_id,
                        auto_research=True
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
