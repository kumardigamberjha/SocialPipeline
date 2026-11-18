"""Tests for the Short-Form & Instagram Reels Prospect Audit Engine."""

import pytest
from app.models.shortform_prospects import ShortFormProfile
from app.services.shortform_prospect_service import (
    build_portfolio_context,
    compute_gap_metrics,
    get_report_by_id,
    list_saved_reports,
    normalize_instagram_handle,
    resolve_candidate,
)


def test_normalize_instagram_handle():
    assert normalize_instagram_handle("@hubspot") == "hubspot"
    assert normalize_instagram_handle("https://www.instagram.com/codingindiaai/") == "codingindiaai"
    assert normalize_instagram_handle("https://instagram.com/my_brand?igsh=123") == "my_brand"
    assert normalize_instagram_handle("MrBeast") == "mrbeast"


def test_compute_gap_metrics_severe_deficit():
    profile = ShortFormProfile(
        platform="youtube",
        identifier="UC123",
        title="AI Automation Lab",
        handle="@aiautomation",
        followers_or_subs=45000,
        total_videos_or_posts=30,
    )
    # 2 shorts, 28 long-form
    videos = [
        {"title": f"Deep Dive Build #{i}", "views": 10000, "duration_seconds": 1200}
        for i in range(28)
    ] + [
        {"title": "Quick Short #1 #shorts", "views": 5000, "duration_seconds": 45},
        {"title": "Quick Short #2 #shorts", "views": 6000, "duration_seconds": 55},
    ]

    gap = compute_gap_metrics(videos, profile)
    assert gap.shorts_count == 2
    assert gap.longform_count == 28
    assert gap.shorts_ratio_pct == 6.7
    assert gap.shortform_opportunity_score >= 90
    assert gap.estimated_missed_views > 0
    assert "Severe Short-Form Deficit" in gap.opportunity_verdict


def test_compute_gap_metrics_balanced_shorts():
    profile = ShortFormProfile(
        platform="youtube",
        identifier="UC456",
        title="Reels Mastery",
        handle="@reelsmastery",
        followers_or_subs=120000,
        total_videos_or_posts=40,
    )
    # 20 shorts, 20 long-form
    videos = [
        {"title": f"Long form #{i}", "views": 8000, "duration_seconds": 900}
        for i in range(20)
    ] + [
        {"title": f"Short #{i}", "views": 15000, "duration_seconds": 50}
        for i in range(20)
    ]

    gap = compute_gap_metrics(videos, profile)
    assert gap.shorts_count == 20
    assert gap.longform_count == 20
    assert gap.shorts_ratio_pct == 50.0
    assert gap.shortform_opportunity_score < 80
    assert "Active Short-Form Catalog" in gap.opportunity_verdict


def test_build_portfolio_context_formatting():
    videos = [
        {"title": "Build an Autonomous Agent", "views": 25000, "duration_seconds": 640},
        {"title": "LangGraph in 10 Minutes", "views": 12000, "duration_seconds": 600},
    ]
    context = build_portfolio_context(videos)
    assert "Build an Autonomous Agent" in context
    assert "25,000 views" in context
    assert "LangGraph in 10 Minutes" in context


@pytest.mark.anyio
async def test_resolve_instagram_candidate():
    profile, posts = await resolve_candidate("instagram", "@codingindiaai")
    assert profile.platform == "instagram"
    assert profile.handle == "@codingindiaai"
    assert len(posts) > 0
