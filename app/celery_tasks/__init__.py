"""Celery tasks for Wings of AI.

These imports are what actually register the tasks. ``autodiscover_tasks``
defaults to looking for a ``tasks`` submodule inside each listed package, which
this package does not have — so anything not imported here is invisible to the
worker, and a beat entry naming it fails with NotRegistered. Both nightly jobs
were in exactly that state.
"""

from app.celery_tasks.competitor_task import competitor_weekly_sync  # noqa: F401
from app.celery_tasks.email_task import send_verification_email_task  # noqa: F401
from app.celery_tasks.instagram_task import instagram_nightly_refresh  # noqa: F401
from app.celery_tasks.youtube_task import youtube_nightly_sync  # noqa: F401
