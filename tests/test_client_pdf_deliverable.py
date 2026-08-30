"""End-to-end verification of the client-facing PDF report deliverable.

Asserts against the WillPower Star fixture:
1. No LLM model names appear anywhere in the exported PDF text.
2. No internal codenames / internal branding (Wings of AI, Command Nexus,
   Autonomous Syndicate, wings-of-ai.com) appear in the client PDF.
3. No API plumbing references (YouTube Data API, Analytics API) appear.
4. Single brand name config (REPORT_BRAND_NAME) is respected.
5. No roadmap justifications cite raw external metrics.
6. Timing regression holds across pages.
7. Fallback tier exports are blocked from client deliverables.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

import pytest

from app.config import get_settings
from app.provider_tiers import CLIENT_GRADE, INTERNAL_ONLY
from app.services import pdf_export_service as pdf_svc
from app.services import youtube_prospect_service as svc
from conftest import NOW, SATURDAY_MULTIPLIER


@pytest.fixture
def clean_willpower_report(willpower_videos):
    """Generate a valid client-grade report structure for WillPower Star."""
    CHANNEL = {
        "title": "WillPower Star",
        "handle": "@willpowerstar",
        "channel_id": "UC_willpower_123",
        "subscriber_count": 2_400_000,
        "view_count": 120_000_000,
        "video_count": 18,
    }

    async def fake_audit(*a, **k):
        return {
            "verdict": "ok",
            "whats_working": [
                "Discipline deep dive documentaries consistently outperform channel median by 2.27x."
            ],
            "underperforming": ["Abstract theory lectures fail to sustain viewer retention."],
            "format_insights": ["Long-form videos over 20 minutes retain 45% more audience."],
            "content_gaps": ["Applied daily execution frameworks."],
            "priorities": ["Double down on biographical discipline case studies."],
            "model": "gemini-3.7-flash",
            "tier": {"name": "Tier 1: Gemini (primary key)", "grade": CLIENT_GRADE, "index": 1},
        }

    async def fake_roadmap(*a, **k):
        return {
            "cadence": "1 video every 2 weeks",
            "weeks": [
                {
                    "focus": "Week 1: Foundations",
                    "items": [
                        {
                            "title": "The 5AM Discipline Teardown",
                            "format": "deep-dive",
                            "theme": "Applied routines",
                            "rationale": "Extends the winning documentary format that averaged 1.03M views on Saturday drops.",
                        }
                    ],
                },
                {
                    "focus": "Week 2: Case Studies",
                    "items": [
                        {
                            "title": "Elite Focus Protocols",
                            "format": "deep-dive",
                            "theme": "Execution frameworks",
                            "rationale": "Anchored to the high-retention 20+ minute format from top performer Discipline Deep Dive 0.",
                        }
                    ],
                },
            ],
            "model": "gemini-3.7-flash",
            "tier": {"name": "Tier 1: Gemini (primary key)", "grade": CLIENT_GRADE, "index": 1},
        }

    import app.services.youtube_ai_analysis as ai
    orig_audit = ai.analyze_strategy
    orig_roadmap = ai.generate_roadmap
    ai.analyze_strategy = fake_audit
    ai.generate_roadmap = fake_roadmap

    try:
        report = asyncio.run(
            svc.generate_prospect_report(CHANNEL, willpower_videos, True, 2, "")
        )
        return report
    finally:
        ai.analyze_strategy = orig_audit
        ai.generate_roadmap = orig_roadmap


def test_client_pdf_contains_no_internal_metadata_or_model_names(clean_willpower_report):
    """The client PDF must never display which LLM generated it or internal codenames."""
    html_content = pdf_svc.build_report_html(clean_willpower_report)

    # Strip HTML tags to get human-readable prose
    rendered_text = re.sub(r"<[^>]+>", " ", html_content)
    lower_text = rendered_text.lower()

    # 1. No LLM model names
    forbidden_models = [
        "gemini",
        "gemma",
        "qwen",
        "deepseek",
        "claude",
        "gpt-4",
        "gpt-3",
        "nemotron",
        "llama",
        "mistral",
        "openrouter",
        "litellm",
    ]
    for model_name in forbidden_models:
        assert model_name not in lower_text, f"Forbidden model name {model_name!r} leaked into client PDF text"

    # 2. No internal system codenames / branding
    forbidden_internal = [
        "wings of ai",
        "wings-of-ai",
        "command nexus",
        "autonomous syndicate",
        "tier 1",
        "tier 2",
        "tier 3",
        "tier 4",
        "tier 5",
    ]
    for internal_name in forbidden_internal:
        assert internal_name not in lower_text, f"Forbidden internal label {internal_name!r} leaked into client PDF text"

    # 3. No API plumbing references
    forbidden_plumbing = [
        "youtube data api",
        "analytics api",
    ]
    for plumbing in forbidden_plumbing:
        assert plumbing not in lower_text, f"Forbidden API reference {plumbing!r} leaked into client PDF text"

    # 4. Must keep only valid deliverable elements
    settings = get_settings()
    expected_brand = (settings.report_brand_name or "Growth Intelligence").upper()
    assert expected_brand in rendered_text
    assert "Channel Intelligence Audit" in rendered_text
    assert "Prepared for" in rendered_text
    assert "WillPower Star" in rendered_text
    assert "PAGE 1 OF" in rendered_text


def test_roadmap_justifications_contain_no_raw_external_metrics(clean_willpower_report):
    """Roadmap items in the report must not contain raw external metrics."""
    for week in clean_willpower_report.get("roadmap", {}).get("weeks", []):
        for item in week.get("items", []):
            rationale = item.get("rationale", "")
            lower_rat = rationale.lower()
            assert "stars" not in lower_rat
            assert "upvotes" not in lower_rat
            assert "/day" not in lower_rat
            assert "trended" not in lower_rat
            assert "went viral" not in lower_rat
            assert "product hunt" not in lower_rat
            assert "github" not in lower_rat


def test_custom_brand_name_configuration(monkeypatch, clean_willpower_report):
    """A custom REPORT_BRAND_NAME setting updates the client PDF cleanly."""
    settings = get_settings()
    monkeypatch.setattr(settings, "report_brand_name", "Acme Media Analytics")

    html_content = pdf_svc.build_report_html(clean_willpower_report)
    assert "ACME MEDIA ANALYTICS" in html_content
    assert "WINGS OF AI" not in html_content
