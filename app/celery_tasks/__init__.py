"""Celery tasks for Wings of AI pipeline."""

from app.celery_tasks.pipeline_task import run_content_pipeline  # noqa: F401
from app.celery_tasks.image_task import generate_instagram_image  # noqa: F401
