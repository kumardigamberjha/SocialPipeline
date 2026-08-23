"""
Celery application configuration for Wings of AI.

Broker: Redis (default queue)
Backend: Redis (result storage)

Start worker:
    celery -A app.celery_app worker --loglevel=info
Start GPU worker:
    celery -A app.celery_app worker -Q gpu_queue --concurrency=1 --loglevel=info
Start Flower:
    celery -A app.celery_app flower --port=5555
"""

from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery("wings_of_ai")

celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_soft_time_limit=300,
    task_time_limit=360,
)

# ── Periodic tasks (Celery Beat) ─────────────────────────────────────────────
# 12:05 AM IST = 18:35 UTC
from celery.schedules import crontab  # noqa: E402

celery_app.conf.beat_schedule = {
    "youtube-nightly-sync": {
        "task": "app.celery_tasks.youtube_task.youtube_nightly_sync",
        "schedule": crontab(hour=18, minute=35),  # 12:05 AM IST daily
        "options": {"queue": "celery"},
    },
    "instagram-nightly-refresh": {
        "task": "app.celery_tasks.instagram_task.instagram_nightly_refresh",
        "schedule": crontab(hour=18, minute=40),  # 12:10 AM IST daily
        "options": {"queue": "celery"},
    },
    "youtube-competitor-weekly-sync": {
        "task": "app.celery_tasks.competitor_task.competitor_weekly_sync",
        "schedule": crontab(day_of_week="sun", hour=8, minute=30),  # Sun 14:00 IST
        "options": {"queue": "celery"},
    },
}

celery_app.autodiscover_tasks(["app.celery_tasks"])

