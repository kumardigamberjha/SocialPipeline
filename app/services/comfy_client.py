"""
Wings of AI — ComfyUI Instagram Integration
System: HP OMEN / RTX 4060 8GB / Ubuntu 24.04

Optimized for:
- SDXL-Turbo  → 4 steps, ~3s per image
- Flux.1-schnell Q4 → 4 steps, ~8s, better quality
- Resolution: 1080x1350 (Instagram 4:5)
"""

import os
import aiohttp
import asyncio
import json
import uuid
import base64
import time
from pathlib import Path
from typing import Optional
import websockets

COMFY_HOST = os.getenv("COMFY_HOST", "127.0.0.1")
COMFY_PORT = int(os.getenv("COMFY_PORT", "8188"))
COMFY_URL  = f"http://{COMFY_HOST}:{COMFY_PORT}"
WS_URL     = f"ws://{COMFY_HOST}:{COMFY_PORT}/ws"

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard" / "public" / "generated_posts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# INSTAGRAM PROMPT ENGINE
# Maps palette + layout + topic → cinematic ComfyUI prompt
# ─────────────────────────────────────────────────────────────

PALETTE_MOODS = {
    "void_purple":  "deep purple neon cyberpunk atmosphere, violet bokeh, dark tech aesthetic, electric glow",
    "cyber_teal":   "bioluminescent teal glow, deep ocean dark tech, cyan light particles, glass refraction",
    "neon_coral":   "warm coral sunset editorial, neon pink digital art, soft bokeh energy, warm tones",
    "solar_amber":  "golden amber cinematic light, sunrise tech, warm bokeh lens flares, editorial magazine",
    "ice_blue":     "crisp ice blue cold light, frost glass texture, arctic tech atmosphere, clean sharp",
    "forest":       "emerald bioluminescent forest, green data streams, organic tech fusion, deep rich green",
    "crimson":      "deep crimson dramatic lighting, red glowing particles, dark editorial, intense atmosphere",
    "pure_dark":    "ultra clean monochrome, black white high contrast, film grain, studio editorial",
}

LAYOUT_COMPOSITIONS = {
    "bottom_hero":  "wide cinematic background, strong visual interest in upper 60%, clear negative space bottom third for text overlay",
    "top_title":    "vertical portrait composition, visual anchor at center, open clear space at top quarter",
    "center_bold":  "perfectly centered radial composition, symmetrical focal point, dramatic center depth",
    "split_left":   "asymmetric rule-of-thirds, main subject right-weighted, left side open negative space",
    "minimal":      "70 percent negative space, single dramatic focal point, extreme minimalist zen composition",
    "full_text":    "abstract layered texture, blurred bokeh depth field, atmospheric background pattern",
}

QUALITY_SUFFIX = (
    "professional photography, 8k ultra sharp, cinematic color grading, "
    "perfect exposure, no text, no watermark, no logos, no letters, "
    "Instagram worthy, trending on ArtStation, award winning composition, "
    "commercial photography quality, Hasselblad medium format look"
)

NEGATIVE_PROMPT = (
    "text, watermark, logo, words, letters, typography, signature, username, "
    "blurry, low resolution, pixelated, oversaturated, distorted, ugly, "
    "amateur, stock photo, white background, flat design, cartoonish, "
    "illustration, drawing, painting, 3d render, anime, deformed, "
    "bad anatomy, bad proportions, duplicate, error, jpeg artifacts"
)


def build_instagram_prompt(
    topic: str,
    palette: str = "void_purple",
    layout: str = "bottom_hero",
    style_hints: str = "",
) -> tuple[str, str]:
    """
    Returns (positive_prompt, negative_prompt) optimized for
    1080x1350 Instagram posts on RTX 4060.
    """
    mood   = PALETTE_MOODS.get(palette, PALETTE_MOODS["void_purple"])
    comp   = LAYOUT_COMPOSITIONS.get(layout, LAYOUT_COMPOSITIONS["bottom_hero"])
    extra  = f", {style_hints}" if style_hints else ""

    positive = (
        f"(Instagram post background for {topic}), "
        f"{mood}, "
        f"{comp}, "
        f"{QUALITY_SUFFIX}"
        f"{extra}"
    )
    return positive, NEGATIVE_PROMPT


# ─────────────────────────────────────────────────────────────
# COMFYUI WORKFLOW BUILDER
# RTX 4060 optimized: SDXL-Turbo or Flux.1-schnell
# ─────────────────────────────────────────────────────────────

def build_sdxl_turbo_workflow(
    positive: str,
    negative: str,
    seed: Optional[int] = None,
    width: int = 1080,
    height: int = 1350,
) -> dict:
    """
    SDXL-Turbo workflow — 4 steps, ~3s on RTX 4060 8GB.
    Best for batch generation / rapid prototyping.
    """
    seed = seed or int(time.time() * 1000) % 999999999
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_turbo_1.0_fp16.safetensors"}
        },
        "2": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1}
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive, "clip": ["1", 1]}
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["1", 1]}
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 4,
                "cfg": 1.0,
                "sampler_name": "euler_ancestral",
                "scheduler": "karras",
                "denoise": 1.0,
                "model":          ["1", 0],
                "positive":       ["3", 0],
                "negative":       ["4", 0],
                "latent_image":   ["2", 0],
            }
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]}
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["6", 0],
                "filename_prefix": f"wings_ai_ig_{seed}"
            }
        },
    }


def build_flux_schnell_workflow(
    positive: str,
    seed: Optional[int] = None,
    width: int = 1080,
    height: int = 1350,
) -> dict:
    """
    Flux.1-schnell Q4_K_M workflow.
    Needs ~7GB VRAM — fits RTX 4060 8GB with headroom.
    Better quality than SDXL-Turbo, ~8s per image.
    Model file: flux1-schnell-Q4_K_S.gguf (via ComfyUI-GGUF node)
    """
    seed = seed or int(time.time() * 1000) % 999999999
    return {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": "flux1-schnell-Q4_K_S.gguf"}
        },
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": "t5xxl_fp8_e4m3fn.safetensors",
                "clip_name2": "clip_l.safetensors",
                "type": "flux"
            }
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "ae.safetensors"}
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive, "clip": ["2", 0]}
        },
        "5": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1}
        },
        "6": {
            "class_type": "BasicGuider",
            "inputs": {"model": ["1", 0], "conditioning": ["4", 0]}
        },
        "7": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed}
        },
        "8": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["1", 0],
                "scheduler": "simple",
                "steps": 4,
                "denoise": 1.0
            }
        },
        "9": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["7", 0],
                "guider": ["6", 0],
                "sampler": ["10", 0],
                "sigmas": ["8", 0],
                "latent_image": ["5", 0]
            }
        },
        "10": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler"}
        },
        "11": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["3", 0]}
        },
        "12": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["11", 0],
                "filename_prefix": f"wings_ai_flux_{seed}"
            }
        },
    }


# ─────────────────────────────────────────────────────────────
# ASYNC COMFYUI CLIENT
# ─────────────────────────────────────────────────────────────

class ComfyClient:
    def __init__(self, host=COMFY_HOST, port=COMFY_PORT):
        self.base_url = f"http://{host}:{port}"
        self.ws_url   = f"ws://{host}:{port}/ws"
        self.client_id = str(uuid.uuid4())

    async def health_check(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{self.base_url}/system_stats", timeout=aiohttp.ClientTimeout(total=3)) as r:
                    return r.status == 200
        except Exception:
            return False

    async def _get_model_status(self, model_name: str) -> tuple[bool, str]:
        """Check if model is available via ComfyUI API."""
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.base_url}/object_info/CheckpointLoaderSimple",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    if r.status != 200:
                        return True, "Cannot verify (API unavailable), proceeding"
                    data = await r.json()
                    ckpt_list = (
                        data.get("CheckpointLoaderSimple", {})
                        .get("input", {})
                        .get("required", {})
                        .get("ckpt_name", [[]])[0]
                    )
                    if model_name in ckpt_list:
                        return True, "Ready"
                    return False, f"Model not found in ComfyUI: {model_name}"
        except Exception:
            return True, "Cannot verify model, proceeding"

    async def queue_prompt(self, workflow: dict) -> str:
        """Queue workflow, return prompt_id."""
        payload = {"prompt": workflow, "client_id": self.client_id}
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{self.base_url}/prompt", json=payload) as r:
                data = await r.json()
                if "prompt_id" not in data:
                    raise RuntimeError(f"ComfyUI error posting prompt: {data}")
                return data["prompt_id"]

    async def wait_for_result(self, prompt_id: str, timeout: int = 120) -> list[bytes]:
        """
        Listen on WebSocket for execution_success, then fetch images.
        Streams progress events so FastAPI can forward them via its own WS.
        """
        async with websockets.connect(f"{self.ws_url}?clientId={self.client_id}") as ws:
            deadline = time.time() + timeout
            async for raw in ws:
                if time.time() > deadline:
                    raise TimeoutError("ComfyUI generation timed out")
                msg = json.loads(raw) if isinstance(raw, str) else {}
                if msg.get("type") == "executing" and msg["data"].get("node") is None:
                    break  # pipeline finished
                if msg.get("type") == "execution_error":
                    raise RuntimeError(f"ComfyUI error: {msg['data']}")

        return await self.fetch_images(prompt_id)

    async def fetch_images(self, prompt_id: str) -> list[bytes]:
        """Retrieve generated image bytes from /history."""
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{self.base_url}/history/{prompt_id}") as r:
                history = await r.json()

        images = []
        outputs = history.get(prompt_id, {}).get("outputs", {})
        for node_output in outputs.values():
            for img_info in node_output.get("images", []):
                params = {"filename": img_info["filename"], "type": img_info["type"]}
                if img_info.get("subfolder"):
                    params["subfolder"] = img_info["subfolder"]
                async with aiohttp.ClientSession() as s:
                    async with s.get(f"{self.base_url}/view", params=params) as r:
                        images.append(await r.read())
        return images

    async def generate_instagram_post(
        self,
        topic: str,
        palette: str = "void_purple",
        layout: str = "bottom_hero",
        model: str = "sdxl_turbo",   # or "flux_schnell"
        style_hints: str = "",
        seed: Optional[int] = None,
    ) -> dict:
        """
        Full pipeline: prompt → workflow → queue → wait → return result.

        Returns:
            {
                "prompt_id": str,
                "positive_prompt": str,
                "images": [base64_str, ...],
                "duration_s": float,
                "model": str,
            }
        """
        t0 = time.time()

        # Safety check: prevent starting if model is not ready
        if model == "sdxl_turbo":
            ready, msg = await self._get_model_status("sd_xl_turbo_1.0_fp16.safetensors")
            if not ready:
                raise RuntimeError(msg)

        positive, negative = build_instagram_prompt(topic, palette, layout, style_hints)

        if model == "flux_schnell":
            workflow = build_flux_schnell_workflow(positive, seed=seed)
        else:
            workflow = build_sdxl_turbo_workflow(positive, negative, seed=seed)

        prompt_id = await self.queue_prompt(workflow)
        image_bytes_list = await self.wait_for_result(prompt_id)

        b64_images = [base64.b64encode(b).decode() for b in image_bytes_list]

        # Save locally
        for i, raw in enumerate(image_bytes_list):
            path = OUTPUT_DIR / f"{prompt_id}_{i}.png"
            path.write_bytes(raw)

        return {
            "prompt_id":       prompt_id,
            "positive_prompt": positive,
            "negative_prompt": negative,
            "model":           model,
            "palette":         palette,
            "layout":          layout,
            "images":          b64_images,
            "duration_s":      round(time.time() - t0, 2),
        }


# ─────────────────────────────────────────────────────────────
# FASTAPI ROUTE  (drop this into your app/main.py)
# ─────────────────────────────────────────────────────────────

FASTAPI_ROUTE_SNIPPET = '''
# ── Add to app/main.py ──────────────────────────────────────

from fastapi import WebSocket
from comfy_client import ComfyClient

comfy = ComfyClient()

class InstagramGenerateRequest(BaseModel):
    topic: str
    palette: str = "void_purple"
    layout: str = "bottom_hero"
    model: str = "sdxl_turbo"       # "sdxl_turbo" | "flux_schnell"
    style_hints: str = ""
    seed: Optional[int] = None

@app.post("/api/instagram/generate")
async def generate_instagram_image(req: InstagramGenerateRequest):
    if not await comfy.health_check():
        raise HTTPException(503, "ComfyUI is not running. Start it with: ./start_comfy.sh")
    result = await comfy.generate_instagram_post(
        topic=req.topic,
        palette=req.palette,
        layout=req.layout,
        model=req.model,
        style_hints=req.style_hints,
        seed=req.seed,
    )
    return result

@app.websocket("/ws/instagram/generate")
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
'''


# ─────────────────────────────────────────────────────────────
# CLI TEST
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def test():
        client = ComfyClient()
        print("Checking ComfyUI connection...")
        ok = await client.health_check()
        if not ok:
            print("ERROR: ComfyUI not running. Start it first:")
            print("  cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188")
            return

        print("ComfyUI connected. Generating test post...")
        result = await client.generate_instagram_post(
            topic="Build AI Agents with CrewAI and Python",
            palette="void_purple",
            layout="bottom_hero",
            model="sdxl_turbo",
        )
        print(f"Done in {result['duration_s']}s")
        print(f"Prompt: {result['positive_prompt'][:120]}...")
        print(f"Images saved to: {OUTPUT_DIR}/")

    asyncio.run(test())
