import json
import logging
import asyncio
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.ws_manager import manager
from app.config import Settings, get_settings
from app.crew import run_pipeline_streaming

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ws", tags=["websocket"])

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
                    await manager.send_json({"error": "Topic is required"}, client_id)
                    continue

                run_id = str(uuid.uuid4())
                # Run the pipeline in an async background task to avoid blocking the WS loop
                asyncio.create_task(
                    run_pipeline_streaming(topic, settings, provider, client_id, run_id)
                )
            except json.JSONDecodeError:
                await manager.send_json({"error": "Invalid JSON"}, client_id)
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
        manager.disconnect(client_id)

@router.websocket("/auto-generate/{client_id}")
async def auto_generate_endpoint(
    websocket: WebSocket,
    client_id: str,
    settings: Settings = Depends(get_settings),
):
    """
    Automatically research the latest AI trends without requiring an explicit user topic.
    """
    await manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                provider = payload.get("provider", settings.default_provider)
                
                # We do not pull 'topic' from the payload.
                # Instead, we inject the dynamic meta-instruction.
                auto_topic = (
                    "LATEST AI TRENDS: Use your web search tool to find the most breaking, viral AI news from today. "
                    "CRITICAL: When using the web_search tool, do NOT query this entire sentence. "
                    "Use short, specific keywords like 'latest AI trends today' or 'viral tech news 2024'. "
                    "Pick the absolute #1 most viral AI topic right now, perform a deep trend analysis, "
                    "and base every single subsequent task output entirely on that specific topic."
                )
                
                run_id = str(uuid.uuid4())
                # Run the pipeline in an async background task
                asyncio.create_task(
                    run_pipeline_streaming(auto_topic, settings, provider, client_id, run_id)
                )
            except json.JSONDecodeError:
                await manager.send_json({"error": "Invalid JSON"}, client_id)
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"Auto-generate Client {client_id} disconnected")
    except Exception as e:
        logger.error(f"Auto-generate WebSocket Error: {e}")
        manager.disconnect(client_id)
