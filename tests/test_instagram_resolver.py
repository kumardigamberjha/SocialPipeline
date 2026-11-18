"""Unit tests for live Instagram profile resolver and dynamic gap metrics."""

import pytest
from app.models.shortform_prospects import ShortFormProfile
from app.services.instagram_resolver import (
    clean_instagram_handle,
    extract_profile_from_snippet,
    parse_social_count,
    resolve_instagram_profile,
)
from app.services.shortform_prospect_service import (
    compute_gap_metrics,
    resolve_candidate,
)


def test_parse_social_count():
    assert parse_social_count("475") == 475
    assert parse_social_count("1,338") == 1338
    assert parse_social_count("12.5K") == 12500
    assert parse_social_count("8M") == 8000000
    assert parse_social_count(None) == 0
    assert parse_social_count("") == 0


def test_clean_instagram_handle():
    assert clean_instagram_handle("@oscar.content") == "oscar.content"
    assert clean_instagram_handle("https://www.instagram.com/iamnikhil/") == "iamnikhil"
    assert clean_instagram_handle("https://instagram.com/hubermanlab?igsh=123") == "hubermanlab"


def test_extract_profile_from_snippet():
    snippet = '475 Followers, 62 Following, 39 Posts - Oscar Ortiz | Content Marketing (@ oscar . content ) on Instagram: "Helping coaches & agencies get clients with content systems Client got 0 -> 3 clients in 45 days DM “client” for FREE audit"'
    title = 'Oscar Ortiz | Content Marketing (@oscar.content) - Instagram'
    parsed = extract_profile_from_snippet("oscar.content", snippet, title)

    assert parsed is not None
    assert parsed["followers"] == 475
    assert parsed["total_posts"] == 39
    assert "Oscar Ortiz" in parsed["title"]
    assert "Helping coaches" in parsed["bio"]


def test_instagram_dynamic_gap_metrics():
    # Micro creator with low posts -> High arbitrage score
    micro_profile = ShortFormProfile(
        platform="instagram",
        identifier="micro_creator",
        title="Micro Creator",
        handle="@micro_creator",
        followers_or_subs=475,
        total_videos_or_posts=25,
        bio="Test Bio",
    )
    micro_gap = compute_gap_metrics([], micro_profile)
    assert micro_gap.shortform_opportunity_score >= 90
    assert "Severe Short-Form Deficit" in micro_gap.opportunity_verdict

    # Large creator with high volume posts -> Retention/offer optimization score
    macro_profile = ShortFormProfile(
        platform="instagram",
        identifier="macro_creator",
        title="Macro Creator",
        handle="@macro_creator",
        followers_or_subs=8000000,
        total_videos_or_posts=1600,
        bio="Test Bio",
    )
    macro_gap = compute_gap_metrics([], macro_profile)
    assert macro_gap.shortform_opportunity_score <= 80
    assert "High-Volume Catalog" in macro_gap.opportunity_verdict

    # Verify scores are not identical
    assert micro_gap.shortform_opportunity_score != macro_gap.shortform_opportunity_score


@pytest.mark.anyio
async def test_resolve_instagram_live():
    # Live resolution test for known handles
    profile, posts = await resolve_candidate("instagram", "oscar.content")
    assert profile.platform == "instagram"
    assert profile.handle == "@oscar.content"
    assert profile.followers_or_subs > 0
    assert profile.total_videos_or_posts > 0
    assert len(posts) > 0

    gap = compute_gap_metrics(posts, profile)
    # The score should NOT be the old static 68
    assert gap.shortform_opportunity_score != 68 or profile.total_videos_or_posts == 45
