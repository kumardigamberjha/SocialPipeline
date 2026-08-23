"""
Async email sender for transactional messages.

Uses ``aiosmtplib`` for non-blocking SMTP so the API event loop is never
blocked by an SMTP handshake.  Falls back to a detailed log line when SMTP is
not configured (SMTP_USER is empty) or aiosmtplib is not installed, so
development works without credentials or the package.

Install dependency:
    pip install aiosmtplib
"""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings

logger = logging.getLogger(__name__)

# Lazy import — keeps the module loadable even if aiosmtplib is not yet
# installed (e.g. on first boot before `pip install -r requirements.txt`).
try:
    import aiosmtplib as _aiosmtplib
    _SMTP_AVAILABLE = True
except ImportError:
    _aiosmtplib = None  # type: ignore[assignment]
    _SMTP_AVAILABLE = False
    logger.warning(
        "aiosmtplib is not installed — verification emails will be logged "
        "to console only. Run: pip install aiosmtplib"
    )


def _build_otp_email(to: str, otp: str, app_name: str) -> MIMEMultipart:
    """Render the verification email as a MIME multipart message."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your {app_name} verification code: {otp}"
    msg["From"] = get_settings().smtp_from or get_settings().smtp_user or "noreply@localhost"
    msg["To"] = to

    # ── Plain text fallback ───────────────────────────────────────────────────
    plain = f"""\
Your {app_name} verification code is: {otp}

This code expires in 10 minutes. Do not share it with anyone.

If you did not create an account, you can safely ignore this email.
"""

    # ── HTML version ──────────────────────────────────────────────────────────
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Email Verification</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Inter',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="480" cellpadding="0" cellspacing="0"
               style="background:#1e293b;border-radius:16px;border:1px solid rgba(255,255,255,0.08);overflow:hidden;">
          <!-- Header -->
          <tr>
            <td style="padding:32px 40px 24px;border-bottom:1px solid rgba(255,255,255,0.06);">
              <p style="margin:0;font-size:13px;font-weight:600;letter-spacing:0.15em;
                         text-transform:uppercase;color:#64748b;">
                {app_name}
              </p>
              <h1 style="margin:8px 0 0;font-size:22px;font-weight:700;color:#f1f5f9;">
                Verify your email
              </h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px 40px;">
              <p style="margin:0 0 24px;font-size:15px;color:#94a3b8;line-height:1.6;">
                Enter the code below in the verification window. It expires in
                <strong style="color:#e2e8f0;">10 minutes</strong>.
              </p>
              <!-- OTP Box -->
              <div style="background:#0f172a;border:1px solid rgba(99,102,241,0.4);
                           border-radius:12px;padding:24px;text-align:center;margin:0 0 24px;">
                <p style="margin:0;font-size:42px;font-weight:800;letter-spacing:0.25em;
                           color:#818cf8;font-family:'Courier New',monospace;">
                  {otp}
                </p>
              </div>
              <p style="margin:0;font-size:13px;color:#475569;line-height:1.5;">
                If you did not create a <strong style="color:#94a3b8;">{app_name}</strong>
                account, you can safely ignore this email. Someone may have typed
                your address by mistake.
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 40px;border-top:1px solid rgba(255,255,255,0.06);">
              <p style="margin:0;font-size:11px;color:#334155;text-align:center;">
                &copy; 2026 {app_name} &mdash; Wings of AI
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


async def send_verification_email(to: str, otp: str) -> None:
    """
    Send a verification OTP to *to* via SMTP.

    • If ``SMTP_USER`` is not set, the OTP is logged at WARNING (dev mode).
    • If ``aiosmtplib`` is not installed, same — falls back to log.
    • Raises on genuine SMTP errors so the endpoint can surface a 502.
    """
    settings = get_settings()

    # Dev / unconfigured fallback — always works without credentials or package.
    if not settings.smtp_user or not _SMTP_AVAILABLE:
        logger.warning(
            "⚠️  SMTP not configured or aiosmtplib missing — "
            "verification OTP for %s → %s  "
            "(set SMTP_USER / SMTP_PASSWORD in app/.env and run: pip install aiosmtplib)",
            to,
            otp,
        )
        return

    msg = _build_otp_email(to, otp, settings.app_name)

    try:
        await _aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("Verification email sent to %s", to)
    except Exception as exc:
        logger.error("Failed to send verification email to %s: %s", to, exc)
        raise
