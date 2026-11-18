"""Unit tests for Instagram dual engagement rate computation and fallback logic."""

import pytest
from app.services.instagram_data import _engagement_rate, recompute_derived


def test_engagement_rate_with_reach():
    # When reach is known, engagement rate is computed against reach
    # (likes 10 + comments 5 + shares 2 + saves 3) / reach 200 * 100 = 20 / 200 * 100 = 10.0%
    rate, rate_type = _engagement_rate(
        likes=10,
        comments=5,
        shares=2,
        saves=3,
        reach=200,
        followers=1000,
    )
    assert rate == 10.0
    assert rate_type == "reach"


def test_engagement_rate_fallback_to_followers():
    # When reach is None (Meta withheld reach insight), rate falls back to followers
    # (likes 20 + comments 5 + shares 0 + saves 0) / followers 500 * 100 = 25 / 500 * 100 = 5.0%
    rate, rate_type = _engagement_rate(
        likes=20,
        comments=5,
        shares=None,
        saves=None,
        reach=None,
        followers=500,
    )
    assert rate == 5.0
    assert rate_type == "followers"


def test_engagement_rate_when_neither_available():
    # When both reach and followers are None / 0, rate is None
    rate, rate_type = _engagement_rate(
        likes=10,
        comments=2,
        shares=None,
        saves=None,
        reach=None,
        followers=0,
    )
    assert rate is None
    assert rate_type in (None, "none")


def test_recompute_derived_preserves_dual_rates():
    raw_posts = [
        {
            "id": "post_1",
            "title": "Post with reach",
            "type": "reel",
            "publish_time": "2026-03-01T10:00:00Z",
            "likes": 50,
            "comments": 10,
            "reach": 1000,
            "shares": 5,
            "saves": 5,
            "views": 1500,
            "caption": "#coding #ai",
        },
        {
            "id": "post_2",
            "title": "Post without reach",
            "type": "carousel",
            "publish_time": "2026-03-02T10:00:00Z",
            "likes": 20,
            "comments": 5,
            "reach": None,
            "shares": None,
            "saves": 5,
            "views": None,
            "caption": "#python #agent",
        },
    ]

    data = {
        "posts": raw_posts,
        "profile": {"followers": 500},
        "stats_by_range": {},
    }

    derived = recompute_derived(data)

    posts = derived["posts"]
    assert len(posts) == 2

    # Post 1 should have reach-based engagement
    p1 = posts[0]
    assert p1["reach"] == 1000
    assert p1["engagement_rate"] == 7.0  # (50 + 10 + 5 + 5) / 1000 * 100
    assert p1["rate_type"] == "reach"

    # Post 2 should have follower-based engagement fallback
    p2 = posts[1]
    assert p2["reach"] is None
    assert p2["engagement_rate"] == 6.0  # (20 + 5 + 0 + 5) / 500 * 100
    assert p2["rate_type"] == "followers"

    # Profile average engagement rate should be the average of (7.0 + 6.0) / 2 = 6.5
    assert derived["profile"]["avg_engagement_rate"] == 6.5
