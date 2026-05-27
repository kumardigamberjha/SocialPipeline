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

# Derive broker and backend from the configured Redis URL
# Broker uses db 0, backend uses db 1
_broker_url = settings.redis_url.rstrip("/")
if _broker_url.endswith("/0"):
    _backend_url = _broker_url[:-1] + "1"
else:
    _backend_url = _broker_url + "/1"

celery_app.conf.update(
    broker_url=_broker_url,
    result_backend=_backend_url,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_soft_time_limit=300,
    task_time_limit=360,
    task_routes={
        "generate_instagram_image": {"queue": "gpu_queue"},
    },
)

celery_app.autodiscover_tasks(["app.celery_tasks"])
