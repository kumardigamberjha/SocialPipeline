"""
Celery task: send the OTP verification email.

Previously ``app/routers/auth.py`` awaited ``send_verification_email``
in-line inside the register / resend-otp request handlers, so the HTTP
response held open for the full SMTP round-trip. This queues it instead —
the endpoint returns as soon as the OTP is stored, and a slow or flaky SMTP
provider retries in the background rather than stalling the request (or,
behind a proxy with a short timeout, failing it outright).
"""

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.celery_tasks.email_task.send_verification_email_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def send_verification_email_task(self, to: str, otp: str):
    """Send (or retry sending) the OTP email.

    Runs the async SMTP client via ``asyncio.run`` since Celery tasks are
    plain sync callables. ``send_verification_email`` itself no-ops (logs the
    OTP) when SMTP is not configured, so this only ever retries on a genuine
    SMTP error.
    """
    from app.core.email import send_verification_email

    try:
        asyncio.run(send_verification_email(to, otp))
    except Exception as exc:
        logger.error(
            "Verification email to %s failed (attempt %d/%d): %s",
            to, self.request.retries + 1, self.max_retries + 1, exc,
        )
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(
                "Verification email to %s: max retries exceeded. Giving up.", to
            )
