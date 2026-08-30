"""
Wings of AI — Gemini image generation for Instagram posts.

Replaces the local ComfyUI/RTX-4060 render path (see the fully commented-out
``app/services/comfy_client.py``). Images now come from the Gemini image models
over the Generative Language REST API, so there is no GPU, no model download and
no ``start_comfy.sh`` to babysit — but every render costs an API call.

The public surface is deliberately the same shape ComfyClient exposed
(``health_check`` / ``generate_instagram_post`` / ``OUTPUT_DIR`` /
``build_instagram_prompt``) so the routers, the CrewAI tool and the dashboard
kept working across the swap. The one thing that could not survive is the
ComfyUI websocket progress protocol: Gemini returns the finished image in a
single HTTP response, so ``queue_prompt``/``wait_for_result`` are gone and the
websocket route just reports "generating" until the call returns.
"""

import base64
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

# Where rendered images are written; unchanged from the ComfyUI path so already
# stored meta.image_file names still resolve.
OUTPUT_DIR = Path(_settings.image_output_dir)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1"

# Callers (and stored plan items) still speak the old ComfyUI model vocabulary.
# Map every legacy name onto the configured Gemini model rather than 400-ing on
# a value that was perfectly valid before the swap.
_LEGACY_MODELS = {"sdxl_turbo", "flux_schnell"}

MODEL_ALIASES = {
    "gemini_flash":      "gemini-3.1-flash-image",
    "gemini_flash_lite": "gemini-3.1-flash-lite-image",
    "gemini_pro":        "gemini-3-pro-image",
}

# The REST API takes protobuf enum *names* here, not the "4:5"/"2K" spellings
# the SDKs and the docs use — posting "4:5" is a 400. Settings stay readable and
# are translated on the way out.
_ASPECT_RATIO_ENUM = {
    "1:1":  "ASPECT_RATIO_ONE_BY_ONE",
    "2:3":  "ASPECT_RATIO_TWO_BY_THREE",
    "3:2":  "ASPECT_RATIO_THREE_BY_TWO",
    "3:4":  "ASPECT_RATIO_THREE_BY_FOUR",
    "4:3":  "ASPECT_RATIO_FOUR_BY_THREE",
    "4:5":  "ASPECT_RATIO_FOUR_BY_FIVE",
    "5:4":  "ASPECT_RATIO_FIVE_BY_FOUR",
    "9:16": "ASPECT_RATIO_NINE_BY_SIXTEEN",
    "16:9": "ASPECT_RATIO_SIXTEEN_BY_NINE",
    "21:9": "ASPECT_RATIO_TWENTY_ONE_BY_NINE",
    "1:8":  "ASPECT_RATIO_ONE_BY_EIGHT",
    "8:1":  "ASPECT_RATIO_EIGHT_BY_ONE",
    "1:4":  "ASPECT_RATIO_ONE_BY_FOUR",
    "4:1":  "ASPECT_RATIO_FOUR_BY_ONE",
}

_IMAGE_SIZE_ENUM = {
    "512": "IMAGE_SIZE_FIVE_TWELVE",
    "1K":  "IMAGE_SIZE_ONE_K",
    "2K":  "IMAGE_SIZE_TWO_K",
    "4K":  "IMAGE_SIZE_FOUR_K",
}


def _aspect_ratio_enum(value: str) -> str:
    """Map "4:5" → the REST enum name; an already-enum value passes through."""
    return _ASPECT_RATIO_ENUM.get(value, value)


def _image_size_enum(value: str) -> str:
    return _IMAGE_SIZE_ENUM.get(str(value).upper(), value)


def resolve_model(model: Optional[str]) -> str:
    """Turn a request's ``model`` into a Gemini model id.

    Accepts an alias (``gemini_flash``), a raw model id (``gemini-3.1-flash-image``)
    or one of the retired ComfyUI names, which fall back to the configured default.
    """
    if not model or model in _LEGACY_MODELS:
        return _settings.gemini_image_model
    return MODEL_ALIASES.get(model, model)


# ─────────────────────────────────────────────────────────────
# INSTAGRAM PROMPT ENGINE
# Maps palette + layout + topic → cinematic image prompt
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
    "professional photography, ultra sharp, cinematic color grading, "
    "perfect exposure, Instagram worthy, award winning composition, "
    "commercial photography quality, Hasselblad medium format look"
)

# Gemini takes no separate negative-prompt field, so the exclusions are stated
# as an instruction inside the positive prompt instead. Kept as its own constant
# because the API response still reports it back for provenance.
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
    """Returns (positive_prompt, negative_prompt) for a 4:5 Instagram post."""
    mood  = PALETTE_MOODS.get(palette, PALETTE_MOODS["void_purple"])
    comp  = LAYOUT_COMPOSITIONS.get(layout, LAYOUT_COMPOSITIONS["bottom_hero"])
    extra = f", {style_hints}" if style_hints else ""

    positive = (
        f"(Instagram post background for {topic}), "
        f"{mood}, "
        f"{comp}, "
        f"{QUALITY_SUFFIX}"
        f"{extra}. "
        f"Do not render any of the following: {NEGATIVE_PROMPT}."
    )
    return positive, NEGATIVE_PROMPT


# ─────────────────────────────────────────────────────────────
# ASYNC GEMINI IMAGE CLIENT
# ─────────────────────────────────────────────────────────────


# Failures a different key can actually fix. Quota on the free tier is counted
# per project, so 429 is the case this exists for; 401/403 cover a key that was
# revoked, restricted or mistyped.
#
# Deliberately excluded: 503 (the *model* is overloaded — every key queues for
# the same capacity, so retrying just spends the backup's quota on the same
# outcome), 400/404 (a malformed request or a bad model id fails identically
# for anyone), and 5xx other than 503.
_KEY_SCOPED_FAILURES = frozenset({401, 403, 429})


class GeminiImageClient:
    """Thin async wrapper over ``models/{model}:generateContent``.

    REST rather than the google-genai SDK on purpose: the only call this needs
    is one POST, and the project already depends on httpx.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key
        # Only meaningful when the caller did not pin a key explicitly: an
        # explicit api_key means "use this one", not "start here".
        self.backup_api_key = None if api_key else settings.gemini_backup_api_key
        self.model = model or settings.gemini_image_model
        self.timeout = settings.gemini_image_timeout

    def _keys(self) -> list[tuple[str, str]]:
        """(label, key) pairs to try, in order. Labels are for logging only."""
        pairs = [("primary", self.api_key), ("backup", self.backup_api_key)]
        seen: set[str] = set()
        out = []
        for label, key in pairs:
            # A backup identical to the primary is a config mistake, not a
            # fallback — trying it twice just spends the same exhausted quota.
            if key and key not in seen:
                seen.add(key)
                out.append((label, key))
        return out

    async def health_check(self) -> bool:
        """True when a key is configured and the model is reachable.

        The ComfyUI equivalent pinged a local process; here the only thing that
        can be wrong before the call is a missing/rejected key, so that is what
        is checked. Failures are treated as "not ready" so the routers keep
        returning 503 instead of surfacing a raw traceback.
        """
        keys = self._keys()
        if not keys:
            logger.warning("GEMINI_API_KEY is not set; image generation is disabled")
            return False
        for label, key in keys:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    r = await client.get(
                        f"{GEMINI_API_BASE}/models/{self.model}",
                        headers={"x-goog-api-key": key},
                    )
                if r.status_code == 200:
                    return True
                logger.warning(
                    "Gemini image health check: %s key returned %s", label, r.status_code
                )
            except Exception as exc:
                logger.warning("Gemini image health check (%s key) failed: %s", label, exc)
        return False

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        image_size: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> list[bytes]:
        """Generate image bytes for one prompt. Raises RuntimeError on failure."""
        keys = self._keys()
        if not keys:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        settings = get_settings()
        model_id = resolve_model(model) if model else self.model
        generation_config: dict = {
            "responseModalities": ["TEXT", "IMAGE"],
            "responseFormat": {
                "image": {
                    "aspectRatio": _aspect_ratio_enum(
                        aspect_ratio or settings.gemini_image_aspect_ratio
                    ),
                    "imageSize": _image_size_enum(
                        image_size or settings.gemini_image_size
                    ),
                }
            },
        }
        if seed is not None:
            generation_config["seed"] = seed

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }

        r = None
        attempts = 0
        for index, (label, key) in enumerate(keys):
            attempts += 1
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{GEMINI_API_BASE}/models/{model_id}:generateContent",
                    headers={
                        "x-goog-api-key": key,
                        "Content-Type": "application/json",
                    },
                    content=json.dumps(payload),
                )

            if r.status_code == 200:
                if index:
                    logger.info("Gemini image: %s key served the request", label)
                break

            remaining = index < len(keys) - 1
            if r.status_code in _KEY_SCOPED_FAILURES and remaining:
                logger.warning(
                    "Gemini image: %s key returned %s; retrying with the next key",
                    label, r.status_code,
                )
                continue
            break

        if r is None or r.status_code != 200:
            # The body carries Google's own reason (bad model id, quota, safety
            # block); surface it rather than a bare status code. The count is
            # what was actually *attempted*, not what is configured — a 503 stops
            # after one key on purpose, and claiming "tried 2" would send someone
            # hunting for a second failure that never happened.
            tried = f" (tried {attempts} keys)" if attempts > 1 else ""
            raise RuntimeError(
                f"Gemini image API returned {r.status_code}{tried}: {r.text[:500]}"
            )

        data = r.json()
        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback") or {}
            raise RuntimeError(f"Gemini returned no candidates (feedback: {feedback})")

        images: list[bytes] = []
        for part in candidates[0].get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                images.append(base64.b64decode(inline["data"]))

        if not images:
            finish = candidates[0].get("finishReason")
            raise RuntimeError(f"Gemini returned no image data (finishReason: {finish})")
        return images

    async def generate_instagram_post(
        self,
        topic: str,
        palette: str = "void_purple",
        layout: str = "bottom_hero",
        model: Optional[str] = None,
        style_hints: str = "",
        seed: Optional[int] = None,
    ) -> dict:
        """
        Full pipeline: prompt → Gemini → saved file(s).

        Returns the same dict the ComfyUI client did, so callers that persist
        ``filenames``/``images``/``model`` need no changes:
            {
                "prompt_id": str,
                "positive_prompt": str,
                "negative_prompt": str,
                "model": str,
                "palette": str,
                "layout": str,
                "images": [base64_str, ...],
                "filenames": [str, ...],
                "duration_s": float,
            }
        """
        t0 = time.time()
        model_id = resolve_model(model)
        positive, negative = build_instagram_prompt(topic, palette, layout, style_hints)

        image_bytes_list = await self.generate(positive, model=model_id, seed=seed)

        # Synthetic id standing in for ComfyUI's prompt_id: the stored filenames
        # and the /generated_posts/<prompt_id>_<i>.png links are built from it.
        prompt_id = uuid.uuid4().hex

        filenames = []
        for i, raw in enumerate(image_bytes_list):
            name = f"{prompt_id}_{i}.png"
            (OUTPUT_DIR / name).write_bytes(raw)
            filenames.append(name)

        return {
            "prompt_id":       prompt_id,
            "positive_prompt": positive,
            "negative_prompt": negative,
            "model":           model_id,
            "palette":         palette,
            "layout":          layout,
            "images":          [base64.b64encode(b).decode() for b in image_bytes_list],
            "filenames":       filenames,
            "duration_s":      round(time.time() - t0, 2),
        }


# ─────────────────────────────────────────────────────────────
# CLI TEST
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def test():
        client = GeminiImageClient()
        print(f"Checking Gemini image model {client.model}...")
        if not await client.health_check():
            print("ERROR: set GEMINI_API_KEY (and check GEMINI_IMAGE_MODEL).")
            return

        print("Connected. Generating test post...")
        result = await client.generate_instagram_post(
            topic="Build AI Agents with CrewAI and Python",
            palette="void_purple",
            layout="bottom_hero",
        )
        print(f"Done in {result['duration_s']}s using {result['model']}")
        print(f"Prompt: {result['positive_prompt'][:120]}...")
        print(f"Images saved to: {OUTPUT_DIR}/")

    asyncio.run(test())
