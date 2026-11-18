"""Parsing and fetch contract for the YouTube-native trend source.

``build_niche_trend_context`` is covered behaviourally in
``test_niche_neutrality``; this file pins the layer beneath it — the text YouTube
actually returns, and the rows we are willing to keep from it.
"""

from __future__ import annotations

import sys
import types

import pytest

from app.services.youtube_trend_source import (
    parse_age_days,
    parse_count,
    search_youtube_videos_direct,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1,234,567 views", 1_234_567),
        ("1.2M views", 1_200_000),
        ("137K views", 137_000),
        ("2.39 million views", 2_390_000),
        ("1 view", 1),
        ("No views", 0),
        ("", 0),
        (None, 0),
    ],
)
def test_parse_count(text, expected):
    """``_parse_subscriber_count`` cannot do this job: it strips only the word
    "subscriber(s)", so "1.2M views" comes back 0 — a real number silently
    flattened to nothing."""
    assert parse_count(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("3 weeks ago", 21.0),
        ("2 days ago", 2.0),
        ("11 months ago", 330.0),
        ("1 year ago", 365.0),
        ("Streamed 2 months ago", 60.0),
    ],
)
def test_parse_age_days(text, expected):
    assert parse_age_days(text) == expected


@pytest.mark.parametrize("text", ["", None, "Premiere", "LIVE"])
def test_parse_age_days_is_none_when_unknown(text):
    """``None`` is not 0. A premiere and a video published today are different
    claims, and the caller must not read an unknown age as fresh."""
    assert parse_age_days(text) is None


def _renderer(vid, title, views, published, channel="Someone", cid="UCsomeone"):
    return {
        "videoId": vid,
        "title": {"runs": [{"text": title}]},
        "viewCountText": {"simpleText": views},
        "publishedTimeText": {"simpleText": published},
        "lengthText": {"simpleText": "12:04"},
        "ownerText": {
            "runs": [
                {
                    "text": channel,
                    "navigationEndpoint": {"browseEndpoint": {"browseId": cid}},
                }
            ]
        },
    }


def _install_fake_scrapetube(monkeypatch, items):
    module = types.ModuleType("scrapetube")
    module.get_search = lambda query, limit=None, results_type="video": iter(items)
    monkeypatch.setitem(sys.modules, "scrapetube", module)


def test_search_parses_a_video_renderer(monkeypatch):
    _install_fake_scrapetube(
        monkeypatch, [_renderer("v1", "Hyderabadi Biryani", "412,900 views", "10 days ago")]
    )
    rows = search_youtube_videos_direct("biryani")
    assert rows == [
        {
            "video_id": "v1",
            "title": "Hyderabadi Biryani",
            "channel_title": "Someone",
            "channel_id": "UCsomeone",
            "views": 412_900,
            "age_days": 10.0,
            "duration": "12:04",
        }
    ]


def test_search_skips_live_streams(monkeypatch):
    """"12K watching" is a concurrent-viewer count, not a view count — it is not
    comparable with anything else in the list."""
    _install_fake_scrapetube(
        monkeypatch,
        [
            _renderer("live", "Cooking Live Right Now", "12K watching", "1 hour ago"),
            _renderer("ok", "Weeknight Dal", "90,000 views", "3 days ago"),
        ],
    )
    assert [r["video_id"] for r in search_youtube_videos_direct("dal")] == ["ok"]


def test_search_skips_items_without_a_video_id(monkeypatch):
    """Search pages carry ad slots and shelf renderers alongside videos."""
    _install_fake_scrapetube(
        monkeypatch,
        [{"promotedVideoRenderer": {}}, _renderer("ok", "Tadka Basics", "50,000 views", "2 days ago")],
    )
    assert [r["video_id"] for r in search_youtube_videos_direct("tadka")] == ["ok"]


def test_search_returns_empty_on_failure(monkeypatch):
    """Supporting evidence for a report that must still generate without it."""
    module = types.ModuleType("scrapetube")

    def boom(*args, **kwargs):
        raise RuntimeError("rate limited")

    module.get_search = boom
    monkeypatch.setitem(sys.modules, "scrapetube", module)
    assert search_youtube_videos_direct("biryani") == []


def test_search_is_a_no_op_without_a_query():
    assert search_youtube_videos_direct("") == []
