"""
Celery task: generate_instagram_image

Runs on the 'gpu_queue' — a dedicated worker with GPU access and concurrency=1.
Wraps the existing ComfyClient to generate Instagram images via ComfyUI.
"""

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="generate_instagram_image",
    max_retries=1,
    soft_time_limit=120,
    time_limit=150,
    queue="gpu_queue",
)
def generate_instagram_image(
    self,
    run_id: str,
    user_id: str,
    topic: str,
    palette: str = "void_purple",
    layout: str = "bottom_hero",
    model: str = "sdxl_turbo",
    style_hints: str = "",
    seed: int | None = None,
):
    """
    Generate an Instagram image using ComfyUI and save metadata to SQLite.

    Args:
        run_id:       UUID for the parent agent run.
        user_id:      UUID of the authenticated user.
        topic:        Image generation topic / prompt seed.
        palette:      Color palette name (e.g. 'void_purple', 'cyber_teal').
        layout:       Composition layout (e.g. 'bottom_hero', 'center_bold').
        model:        ComfyUI model ('sdxl_turbo' or 'flux_schnell').
        style_hints:  Additional style directives.
        seed:         Optional fixed seed for reproducibility.
    """
    from app.services.comfy_client import ComfyClient

    client = ComfyClient()

    async def _generate():
        healthy = await client.health_check()
        if not healthy:
            raise RuntimeError("ComfyUI is not running or unreachable")

        return await client.generate_instagram_post(
            topic=topic,
            palette=palette,
            layout=layout,
            model=model,
            style_hints=style_hints,
            seed=seed,
        )

    try:
        result = asyncio.run(_generate())

        # Save image URL back to SQLite
        try:
            from app.db.database import get_db
            db = get_db()
            prompt_id = result.get("prompt_id")
            if prompt_id and len(result.get("images", [])) > 0:
                image_url = f"/generated_posts/{prompt_id}_0.png"
                db.execute(
                    "UPDATE agent_runs SET image_url = ? WHERE id = ?",
                    (image_url, run_id)
                )
                db.commit()
                logger.info("Successfully saved image URL to SQLite.")
        except Exception as e:
            logger.error("Failed to save image URL to SQLite: %s", e)

        logger.info(
            "Image generated ▸ run_id=%s model=%s duration=%.2fs",
            run_id, result.get("model"), result.get("duration_s", 0),
        )
        return {
            "run_id": run_id,
            "prompt_id": result.get("prompt_id"),
            "image_count": len(result.get("images", [])),
            "duration_s": result.get("duration_s"),
        }

    except Exception as exc:
        logger.error("Image generation failed ▸ run_id=%s error=%s", run_id, exc)
        try:
            self.retry(exc=exc, countdown=15)
        except self.MaxRetriesExceededError:
            logger.error("Image generation retries exhausted ▸ run_id=%s", run_id)
            raise
