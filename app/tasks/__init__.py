"""
``app.tasks`` is the Celery entry point for the dedicated LinkedIn and blog
workers (``celery -A app.tasks worker -Q linkedin_queue`` /
``celery -A app.tasks worker -Q blog_queue``).

It re-exports the single shared Celery instance from ``app.celery_app`` (so the
broker / backend config is identical to every other worker) and imports the
task modules so their tasks are registered the moment this package is loaded.

Importing ``celery_app`` BEFORE the task modules is required: each task binds
its decorator to this same instance.
"""

from app.celery_app import celery_app

# `celery -A app.tasks` searches module attributes for a Celery instance; expose
# the conventional `app` alias in addition to `celery_app` so resolution is robust.
app = celery_app

from app.tasks.linkedin_task import run_linkedin_pipeline  # noqa: E402,F401  (registers the task)
from app.tasks.blog_task import run_blog_pipeline  # noqa: E402,F401  (registers the task)

__all__ = ["celery_app", "app", "run_linkedin_pipeline", "run_blog_pipeline"]
