"""An audit must describe the channel that was actually asked for.

``resolve_channel``'s OAuth branch fell through to a zero-quota scrapetube search
and returned hit #1 unconditionally. ``POST /{channel_id}/report`` passes a bare
``UC...`` id, so any miss on ``channels.list`` — a transient error, quota, a
deleted channel — silently audited a different, usually more popular creator
under the requested id. The report would be internally consistent, so nothing
downstream could catch it. The no-OAuth branch already refused exactly this.
"""

from __future__ import annotations

import pytest

from app.services import youtube_channel_lookup as lookup

RIGHT_ID = "UC" + "r" * 22
WRONG_ID = "UC" + "w" * 22


def _row(cid, title="Some Creator", handle=""):
    return {"channel_id": cid, "title": title, "handle": handle}


@pytest.fixture
def oauth(monkeypatch):
    """An OAuth client that resolves nothing, forcing the scrapetube fallback."""
    monkeypatch.setattr(lookup, "_service", lambda user_id: object())
    monkeypatch.setattr(lookup, "_resolve_by_ids", lambda yt, ids, ledger: {})
    monkeypatch.setattr(lookup, "_resolve_by_handle", lambda yt, handle, ledger: None)
    monkeypatch.setattr(lookup, "_resolve_by_search", lambda yt, probe, ledger: None)


def test_a_mismatched_scraped_hit_is_refused(monkeypatch, oauth):
    monkeypatch.setattr(lookup, "_scraped_match", lambda q: _row(WRONG_ID, "Someone Else"))
    assert lookup.resolve_channel("user", RIGHT_ID) is None


def test_a_matching_scraped_hit_is_accepted(monkeypatch, oauth):
    monkeypatch.setattr(lookup, "_scraped_match", lambda q: _row(RIGHT_ID, "The Right One"))
    result = lookup.resolve_channel("user", RIGHT_ID)
    assert result is not None and result["channel_id"] == RIGHT_ID


def test_free_text_still_trusts_the_first_hit(monkeypatch, oauth):
    """Guarding against over-tightening: free text *is* a search, so hit #1 is
    the answer. Only an explicitly named identity gets checked."""
    monkeypatch.setattr(lookup, "_scraped_match", lambda q: _row(WRONG_ID, "Aarti's Kitchen"))
    result = lookup.resolve_channel("user", "aartis kitchen")
    assert result is not None and result["channel_id"] == WRONG_ID


def test_a_mismatched_handle_is_refused(monkeypatch, oauth):
    monkeypatch.setattr(
        lookup, "_scraped_match", lambda q: _row(WRONG_ID, "Reaction Channel", "@someoneelse")
    )
    assert lookup.resolve_channel("user", "@aartiskitchen") is None


def test_a_matching_handle_is_accepted(monkeypatch, oauth):
    monkeypatch.setattr(
        lookup, "_scraped_match", lambda q: _row(RIGHT_ID, "Aarti's Kitchen", "@aartiskitchen")
    )
    result = lookup.resolve_channel("user", "@aartiskitchen")
    assert result is not None and result["channel_id"] == RIGHT_ID


def test_a_handle_without_a_scraped_handle_falls_back_to_the_title(monkeypatch, oauth):
    """scrapetube frequently omits the handle, and a /c/ custom URL legitimately
    differs from the modern @handle, so the title slug is the tiebreak."""
    monkeypatch.setattr(lookup, "_scraped_match", lambda q: _row(RIGHT_ID, "Aarti's Kitchen"))
    result = lookup.resolve_channel("user", "@aartiskitchen")
    assert result is not None and result["channel_id"] == RIGHT_ID


def test_the_quota_search_path_also_checks_the_id(monkeypatch):
    """The 100-unit search.list fallback had the same hole."""
    monkeypatch.setattr(lookup, "_service", lambda user_id: object())
    monkeypatch.setattr(lookup, "_resolve_by_ids", lambda yt, ids, ledger: {})
    monkeypatch.setattr(lookup, "_resolve_by_handle", lambda yt, handle, ledger: None)
    monkeypatch.setattr(lookup, "_scraped_match", lambda q: None)
    monkeypatch.setattr(
        lookup, "_resolve_by_search", lambda yt, probe, ledger: {"id": WRONG_ID, "snippet": {}}
    )
    assert lookup.resolve_channel("user", RIGHT_ID) is None
