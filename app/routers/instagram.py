"""
/api/instagram/generate – Instagram Post Image Generation and WebSocket
"""

import logging
import base64
from typing import Optional
from fastapi import APIRouter, HTTPException, WebSocket, Depends
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from app.services.comfy_client import (
    ComfyClient,
    build_instagram_prompt,
    build_flux_schnell_workflow,
    build_sdxl_turbo_workflow,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["instagram"])
comfy = ComfyClient()

class InstagramGenerateRequest(BaseModel):
    topic: str
    palette: str = "void_purple"
    layout: str = "bottom_hero"
    model: str = "sdxl_turbo"       # "sdxl_turbo" | "flux_schnell"
    style_hints: str = ""
    seed: Optional[int] = None

@router.post("/api/instagram/generate")
async def generate_instagram_image(req: InstagramGenerateRequest):
    if not await comfy.health_check():
        raise HTTPException(status_code=503, detail="ComfyUI is not running. Start it with: ./start_comfy.sh")
    result = await comfy.generate_instagram_post(
        topic=req.topic,
        palette=req.palette,
        layout=req.layout,
        model=req.model,
        style_hints=req.style_hints,
        seed=req.seed,
    )
    return result

@router.websocket("/ws/instagram/generate")
async def ws_generate_instagram(websocket: WebSocket):
    """
    WebSocket version — streams progress events to the Next.js dashboard.
    """
    await websocket.accept()
    data = await websocket.receive_json()
    req  = InstagramGenerateRequest(**data)

    await websocket.send_json({"type": "status", "message": "Building prompt..."})

    if not await comfy.health_check():
        await websocket.send_json({"type": "error", "message": "ComfyUI offline"})
        return

    positive, negative = build_instagram_prompt(
        req.topic, req.palette, req.layout, req.style_hints
    )
    await websocket.send_json({"type": "prompt_ready", "prompt": positive})

    workflow = (
        build_flux_schnell_workflow(positive, seed=req.seed)
        if req.model == "flux_schnell"
        else build_sdxl_turbo_workflow(positive, negative, seed=req.seed)
    )

    await websocket.send_json({"type": "status", "message": f"Queued on ComfyUI ({req.model})..."})
    prompt_id = await comfy.queue_prompt(workflow)

    await websocket.send_json({"type": "status", "message": "Generating image on RTX 4060..."})
    images = await comfy.wait_for_result(prompt_id)

    b64 = [base64.b64encode(b).decode() for b in images]
    await websocket.send_json({
        "type":     "complete",
        "prompt_id": prompt_id,
        "images":   b64,
        "prompt":   positive,
    })
    await websocket.close()
