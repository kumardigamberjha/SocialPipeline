"""
/api/instagram/generate – Instagram Post Image Generation and WebSocket
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, WebSocket, Depends
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from app.core.auth_deps import get_current_user, get_current_user_ws
from app.services.gemini_image_client import (
    GeminiImageClient,
    build_instagram_prompt,
    resolve_model,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["instagram"])
image_client = GeminiImageClient()

class InstagramGenerateRequest(BaseModel):
    topic: str
    palette: str = "void_purple"
    layout: str = "bottom_hero"
    # Alias ("gemini_flash", "gemini_flash_lite", "gemini_pro"), a raw Gemini
    # image model id, or None for the configured default. The retired ComfyUI
    # names still resolve to the default so older clients keep working.
    model: Optional[str] = None
    style_hints: str = ""
    seed: Optional[int] = None

@router.post("/api/instagram/generate")
async def generate_instagram_image(
    req: InstagramGenerateRequest, user: dict = Depends(get_current_user)
):
    """Generate an Instagram post image via the Gemini image models.

    Was reachable with no authentication at all — an unauthenticated image
    endpoint is a free image-generation service (now billed to our API key) for
    anyone who finds it.
    """
    if not await image_client.health_check():
        raise HTTPException(
            status_code=503,
            detail="Gemini image generation is unavailable. Check GEMINI_API_KEY and GEMINI_IMAGE_MODEL.",
        )
    try:
        result = await image_client.generate_instagram_post(
            topic=req.topic,
            palette=req.palette,
            layout=req.layout,
            model=req.model,
            style_hints=req.style_hints,
            seed=req.seed,
        )
    except Exception as exc:
        logger.error("Instagram image generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Image generation failed: {exc}")
    return result

@router.websocket("/ws/instagram/generate")
async def ws_generate_instagram(
    websocket: WebSocket, user: dict = Depends(get_current_user_ws)
):
    """
    WebSocket version — streams progress events to the Next.js dashboard.

    Authenticated before ``accept()``, same as the other content sockets. If
    authentication fails, ``get_current_user_ws`` closes the socket and raises
    before this body ever runs.

    Gemini answers with the finished image in one HTTP response, so unlike the
    old ComfyUI node-by-node stream there is no real progress to forward — the
    event sequence (status / prompt_ready / complete | error) is kept only so
    the dashboard did not need changing.
    """
    await websocket.accept()
    data = await websocket.receive_json()
    req = InstagramGenerateRequest(**data)

    await websocket.send_json({"type": "status", "message": "Building prompt..."})

    if not await image_client.health_check():
        await websocket.send_json({
            "type": "error",
            "message": "Gemini image generation is unavailable (check GEMINI_API_KEY).",
        })
        return

    positive, _negative = build_instagram_prompt(
        req.topic, req.palette, req.layout, req.style_hints
    )
    await websocket.send_json({"type": "prompt_ready", "prompt": positive})

    model_id = resolve_model(req.model)
    await websocket.send_json({"type": "status", "message": f"Generating with {model_id}..."})

    try:
        result = await image_client.generate_instagram_post(
            topic=req.topic,
            palette=req.palette,
            layout=req.layout,
            model=req.model,
            style_hints=req.style_hints,
            seed=req.seed,
        )
    except Exception as exc:
        logger.error("Instagram image generation failed: %s", exc)
        await websocket.send_json({"type": "error", "message": f"Image generation failed: {exc}"})
        await websocket.close()
        return

    await websocket.send_json({
        "type":      "complete",
        "prompt_id": result["prompt_id"],
        "images":    result["images"],
        "prompt":    positive,
    })
    await websocket.close()
