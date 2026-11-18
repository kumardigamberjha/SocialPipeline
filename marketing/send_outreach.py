#!/usr/bin/env python3
"""
Wings of AI — Anti-Bot Compliant Cold Email Outreach Dispatcher.

This script dispatches personalized cold emails to selected high-fit creator and
business leads with strict deliverability and anti-spam protections:
- Randomized human jitter delays (avoiding algorithmic spam velocity spikes).
- Full RFC 2822 compliant MIME multipart messages (text/plain + clean HTML).
- Unique RFC-compliant Message-IDs, Date headers, and proper From/Reply-To headers.
- Spam keyword mitigation (no spam triggers, clean subject lines).
- CAN-SPAM compliant opt-out footer.
- Comprehensive CSV delivery audit log (outreach_sent_log.csv).
- Safe --dry-run mode for pre-flight verification.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import email.utils
import logging
import os
import random
import smtplib
import sys
import time
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List

from dotenv import dotenv_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("OutreachSender")

DEFAULT_LEADS_CSV = Path(__file__).resolve().parent / "youtube_business_leads_1000.csv"
AUDIT_LOG_CSV = Path(__file__).resolve().parent / "outreach_sent_log.csv"
ENV_PATH = Path(__file__).resolve().parent.parent / "app" / ".env"


def load_smtp_config() -> Dict[str, Any]:
    """Load and validate SMTP configuration from app/.env."""
    env = dotenv_values(ENV_PATH)
    host = env.get("SMTP_HOST", "smtp.gmail.com")
    port = int(env.get("SMTP_PORT", 587))
    user = env.get("SMTP_USER", "")
    pwd = env.get("SMTP_PASSWORD", "")
    sender_from = env.get("SMTP_FROM", user)

    if not user or not pwd:
        raise ValueError(
            f"Missing SMTP_USER or SMTP_PASSWORD in {ENV_PATH}. Please verify configuration."
        )

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": pwd,
        "from_email": sender_from,
        "sender_name": "Digamber Jha",
    }


def pick_best_leads(
    leads_csv: Path,
    count: int = 10,
    category: Optional[str] = None,
    seed: int = 101,
) -> List[Dict[str, str]]:
    """Select a randomized, high-fit, balanced sample of NEW top leads, optionally filtered by category, excluding already contacted leads."""
    if not leads_csv.exists():
        raise FileNotFoundError(f"Leads database not found at {leads_csv}")

    with open(leads_csv, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    # Exclude any leads that have already been contacted
    uncontacted = [
        l for l in reader
        if l.get("outreach_status", "").lower() != "contacted"
    ]

    random.seed(seed)

    # If specific category or agency/owner requested
    if category:
        cat_lower = category.lower()
        if "agency" in cat_lower or "owner" in cat_lower or "cto" in cat_lower:
            # Pick from curated agency owners and tech company founders/CTOs
            owner_leads = [
                l for l in uncontacted
                if int(l.get("lead_id", 999)) <= 100
                and l.get("category") in ["Digital Media & Growth Agency", "B2B DevTool & SaaS Founder"]
            ]
            # Shuffle with seed for variety
            random.shuffle(owner_leads)
            return owner_leads[:count]

        cat_leads = [
            l for l in uncontacted
            if cat_lower in l.get("category", "").lower()
        ]
        # Prioritize top curated leads (id <= 100) first
        curated_first = sorted(
            cat_leads,
            key=lambda x: (0 if int(x.get("lead_id", 999)) <= 100 else 1, -float(x.get("product_fit_score", "0").split("/")[0]))
        )
        return curated_first[:count]

    # Otherwise, balanced cross-category pick (prioritizing curated first 100)
    curated_leads = [l for l in uncontacted if int(l.get("lead_id", "999")) <= 100]
    by_cat: Dict[str, List[Dict[str, str]]] = {}
    for l in (curated_leads if len(curated_leads) >= count else uncontacted):
        by_cat.setdefault(l["category"], []).append(l)

    categories = [
        "AI & Machine Learning Creator",
        "Web & Full-Stack Development Creator",
        "Cloud, DevOps & Systems Creator",
        "B2B DevTool & SaaS Founder",
        "Digital Media & Growth Agency",
    ]

    picked: List[Dict[str, str]] = []
    per_cat = max(1, count // len(categories))

    for cat in categories:
        items = by_cat.get(cat, [])
        sample_size = min(per_cat, len(items))
        if items:
            picked.extend(random.sample(items, sample_size))

    # Fill any remaining slots up to count
    if len(picked) < count:
        remaining = [l for l in (curated_leads if len(curated_leads) >= count else uncontacted) if l not in picked]
        needed = count - len(picked)
        if remaining:
            picked.extend(random.sample(remaining, min(needed, len(remaining))))

    return picked[:count]


def build_email_content(lead: Dict[str, str]) -> Dict[str, str]:
    """Generate personalized email subject, plain text, and HTML bodies showcasing full platform capabilities."""
    name = lead.get("name", "there")
    first_name = name.split()[0] if name else "there"
    company = lead.get("channel_or_company", "your channel")
    niche = lead.get("primary_niche", "tech content").split(",")[0].strip()
    category = lead.get("category", "")
    pitch_hook = lead.get("personalized_pitch_hook", "")

    # Tailor subject based on audience category
    if "Agency" in category:
        subject = f"instant YouTube channel audits & competitor intelligence for {company}"
    elif "SaaS" in category or "Founder" in category:
        subject = f"automated AI content engine & channel intelligence for {company}"
    elif "DevOps" in category:
        subject = f"deep channel audit & competitor breakout alerts for {company}"
    else:
        subject = f"deep YouTube audit & competitor breakout engine for {company}"

    # Plain text version
    plain_text = f"""Hi {first_name},

{pitch_hook}

Most creators, agencies, and tech founders are flying blind because manual channel audits, retention teardowns, and competitor tracking consume 15+ hours every week.

We built Wings of AI (Nexus) — an AI-powered content operating system and competitor intelligence hub (powering content.codingindia.co.in):

1. Instant Deep Audit of ANY YouTube Channel:
   Drop in any channel link (yours or any competitor's) to instantly diagnose retention bottlenecks, SEO tag flaws, CTR anomaly scores, and generate an algorithmic 1-to-8 week publishing roadmap.

2. Competitor Outlier & Breakout Engine:
   Automatically detects competitor videos performing way above baseline (viral velocity & CTR spikes) before trends peak, giving you proven viral angles.

3. Deep Own-Channel Analytics & Meta Graph Sync:
   Real-time sync with YouTube Data & Analytics API v3 and Meta Instagram Graph API to track genuine reach, retention graphs, and audience engagement in one unified dashboard.

4. Multi-Agent AI Studio (Gemini 3.6 Flash + Gemini Visuals):
   Autonomous syndication agents (Hook Finder → Scriptwriter → Code QA → SEO Editor) that convert ideas into viral scripts, verified technical blogs, and high-res Gemini graphics (4:5, 1:1, 16:9).

5. Institutional PDF Deliverable Engine:
   Generates client-ready, white-labeled channel audit and growth roadmap PDF reports in seconds.

We are currently onboarding a private cohort of top creators and teams before public rollout at content.codingindia.co.in.

I'd love to jump on a quick 10-minute live demo to:
• Run a real-time deep audit of {company} (and 2 of your top competitors) right on the call.
• Hand you your channel's institutional growth roadmap PDF deliverable.
• Walk you through the automated AI pipeline.

Are you open to a quick 10-minute live walkthrough this Thursday or Friday? (Or let me know a day/time that works best for you!)

Best regards,
Digamber Jha
Founder, Wings of AI (Nexus)
https://content.codingindia.co.in • [@codingindiaai on Instagram]

---
If you'd prefer not to hear from me about Wings of AI, simply reply with 'unsubscribe' and I will immediately remove you from all future communications.
"""

    # Semantic HTML version
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #222222; margin: 0; padding: 12px; }}
  p {{ margin: 0 0 14px 0; }}
  ul {{ margin: 0 0 14px 0; padding-left: 20px; }}
  li {{ margin-bottom: 8px; }}
  .meeting-box {{ background-color: #f0f7ff; border-left: 4px solid #0066cc; padding: 14px 18px; margin: 18px 0; border-radius: 0 4px 4px 0; }}
  .footer {{ margin-top: 24px; padding-top: 14px; border-top: 1px solid #e0e0e0; font-size: 11px; color: #777777; line-height: 1.4; }}
  .footer a {{ color: #777777; }}
</style>
</head>
<body>
  <p>Hi {first_name},</p>
  <p>{pitch_hook}</p>
  <p>Most creators, media agencies, and DevRel teams are flying blind because manual channel analysis, retention audits, and competitor monitoring consume 15+ hours every week.</p>
  <p>We built <strong>Wings of AI (Nexus)</strong> — an AI-powered content operating system and competitor intelligence hub (powering <a href="https://content.codingindia.co.in" style="color: #0066cc; font-weight: 600;">content.codingindia.co.in</a>):</p>
  <ul>
    <li><strong>Instant Deep Audit of ANY YouTube Channel:</strong> Paste any channel URL (yours or any competitor's) for instant retention leak diagnosis, SEO tag scoring, CTR anomaly analysis, and an algorithmic 1–8 week publishing roadmap.</li>
    <li><strong>Competitor Outlier & Breakout Engine:</strong> Automatically detects competitor videos outperforming baseline velocity before trends peak, uncovering high-retention content angles.</li>
    <li><strong>Deep Own-Channel Analytics & Meta Graph Sync:</strong> Direct live sync with YouTube Data & Analytics API v3 and Instagram Graph API to track true retention curves, engagement, and reach without leaving the hub.</li>
    <li><strong>Autonomous Multi-Agent AI Studio (Gemini 3.6 Flash + Gemini Visuals):</strong> 5-stage agent syndicate (Hook Finder &rarr; Scriptwriter &rarr; Code QA &rarr; SEO Editor) producing viral scripts, verified technical articles, and native high-res graphics (4:5 portrait, 16:9, 1:1).</li>
    <li><strong>Institutional PDF Deliverable Engine:</strong> 1-click generation of client-ready, white-labeled channel audit and growth roadmap PDF reports.</li>
  </ul>
  <div class="meeting-box">
    <p style="margin: 0 0 8px 0; font-weight: bold; color: #004499;">We are onboarding a private cohort of top creators and teams before public rollout.</p>
    <p style="margin: 0 0 6px 0;">I'd love to jump on a brief 10-minute live demo to:</p>
    <ul style="margin: 0 0 10px 0; padding-left: 20px;">
      <li>Run a real-time deep audit of <strong>{company}</strong> (and 2 of your top competitors) right on the call.</li>
      <li>Hand you your channel's institutional growth roadmap PDF deliverable.</li>
      <li>Walk you through the automated AI pipeline.</li>
    </ul>
    <p style="margin: 0; font-weight: 600; color: #003388;">Are you open to a quick 10-minute live walkthrough this Thursday or Friday? (Or let me know a day/time that works best for you!)</p>
  </div>
  <p>Best regards,<br>
  <strong>Digamber Jha</strong><br>
  Founder, Wings of AI (Nexus)<br>
  <a href="https://content.codingindia.co.in" style="color: #0066cc;">content.codingindia.co.in</a> &bull; <a href="https://instagram.com/codingindiaai" style="color: #666666;">@codingindiaai</a>
  </p>
  <div class="footer">
    <p>If you'd prefer not to hear from me about Wings of AI, simply reply with "unsubscribe" and I will immediately remove you from all future communications.</p>
  </div>
</body>
</html>"""

    return {
        "subject": subject,
        "plain_text": plain_text,
        "html_content": html_content,
    }


def create_mime_message(
    sender_name: str,
    from_email: str,
    to_name: str,
    to_email: str,
    subject: str,
    plain_text: str,
    html_content: str,
) -> MIMEMultipart:
    """Construct an RFC 2822 compliant multipart email message with anti-spam headers."""
    msg = MIMEMultipart("alternative")

    # Anti-bot and RFC compliant headers
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{from_email}>"
    msg["To"] = f"{to_name} <{to_email}>"
    msg["Reply-To"] = from_email
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=from_email.split("@")[-1])

    # Clean mailer attribution
    msg["X-Mailer"] = "WingsOfAI-Client/1.0"
    msg["Precedence"] = "bulk"

    part1 = MIMEText(plain_text, "plain", "utf-8")
    part2 = MIMEText(html_content, "html", "utf-8")

    # Plain text first, HTML second per RFC 2046
    msg.attach(part1)
    msg.attach(part2)

    return msg


def log_audit_record(record: Dict[str, Any], audit_file: Path = AUDIT_LOG_CSV) -> None:
    """Record delivery details into the CSV audit log."""
    file_exists = audit_file.exists()
    fieldnames = [
        "timestamp",
        "lead_id",
        "recipient_name",
        "recipient_company",
        "recipient_email",
        "category",
        "subject",
        "status",
        "message_id",
        "error_message",
    ]
    with open(audit_file, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)


def mark_lead_contacted(lead_id: str, csv_path: Path = DEFAULT_LEADS_CSV) -> None:
    """Update lead outreach_status to Contacted in the CSV."""
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            if str(r.get("lead_id")) == str(lead_id):
                r["outreach_status"] = "Contacted"
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
    except Exception as e:
        logger.warning(f"Could not update status for lead {lead_id}: {e}")


def dispatch_outreach(
    leads: List[Dict[str, str]],
    dry_run: bool = True,
    min_delay_sec: float = 8.0,
    max_delay_sec: float = 18.0,
) -> None:
    """Send personalized emails with randomized delays and full error handling."""
    config = load_smtp_config()
    total = len(leads)
    logger.info(f"Targeting {total} leads. Mode: {'DRY-RUN (Simulation)' if dry_run else 'LIVE DISPATCH'}")

    server = None
    if not dry_run:
        logger.info(f"Connecting to SMTP server {config['host']}:{config['port']}...")
        server = smtplib.SMTP(config["host"], config["port"], timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(config["user"], config["password"])
        logger.info("SMTP TLS handshake and authentication successful.")

    try:
        for idx, lead in enumerate(leads, start=1):
            to_name = lead.get("name", "Creator")
            to_email = lead.get("business_email", "")
            company = lead.get("channel_or_company", "")
            lead_id = lead.get("lead_id", "")
            category = lead.get("category", "")

            content = build_email_content(lead)
            msg = create_mime_message(
                sender_name=config["sender_name"],
                from_email=config["from_email"],
                to_name=to_name,
                to_email=to_email,
                subject=content["subject"],
                plain_text=content["plain_text"],
                html_content=content["html_content"],
            )

            status = "SIMULATED"
            err_msg = ""
            msg_id = msg["Message-ID"]

            if dry_run:
                logger.info(f"[{idx}/{total}] DRY-RUN -> {to_name} <{to_email}> ({company})")
                logger.info(f"       Subject: {content['subject']}")
                logger.info(f"       Message-ID: {msg_id}")
            else:
                try:
                    logger.info(f"[{idx}/{total}] SENDING -> {to_name} <{to_email}> ({company})...")
                    server.send_message(msg)
                    status = "SENT"
                    mark_lead_contacted(lead_id)
                    logger.info(f"[{idx}/{total}]  SUCCESS: Dispatched to {to_email} (Marked Contacted)")
                except Exception as e:
                    status = "FAILED"
                    err_msg = str(e)
                    logger.error(f"[{idx}/{total}]  FAILED to send to {to_email}: {e}")

            # Audit record
            log_audit_record({
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "lead_id": lead_id,
                "recipient_name": to_name,
                "recipient_company": company,
                "recipient_email": to_email,
                "category": category,
                "subject": content["subject"],
                "status": status,
                "message_id": msg_id,
                "error_message": err_msg,
            })

            # Random human jitter delay between sends (anti-bot velocity throttling)
            if idx < total:
                delay = random.uniform(min_delay_sec, max_delay_sec)
                logger.info(f"       [Anti-Bot Deliberate Pause] Waiting {delay:.1f}s before next send...")
                if not dry_run:
                    time.sleep(delay)
                else:
                    time.sleep(0.5)  # brief pacing in dry run

    finally:
        if server:
            try:
                server.quit()
                logger.info("Closed SMTP session.")
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="Wings of AI Anti-Bot Compliant Cold Email Dispatcher"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of best leads to pick and contact (default: 10)",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter leads by specific category (e.g. 'Digital Media & Growth Agency')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate the outreach without sending actual emails",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        default=False,
        help="Execute live dispatch over authenticated SMTP",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=8.0,
        help="Minimum delay between emails in seconds (default: 8.0)",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=18.0,
        help="Maximum delay between emails in seconds (default: 18.0)",
    )

    args = parser.parse_args()

    if not args.send and not args.dry_run:
        print("Please specify either --dry-run (to preview) or --send (to execute live dispatch).")
        sys.exit(1)

    selected = pick_best_leads(DEFAULT_LEADS_CSV, count=args.count, category=args.category, seed=42)
    dispatch_outreach(
        leads=selected,
        dry_run=args.dry_run,
        min_delay_sec=args.min_delay,
        max_delay_sec=args.max_delay,
    )


if __name__ == "__main__":
    main()
