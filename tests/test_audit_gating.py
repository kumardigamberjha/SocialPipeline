"""The export gate: a fallback-written audit must not reach a client.

The failure this prevents is not "a worse report" — it is a report nobody could
tell was worse. The Qwen audit went out as a branded PDF looking exactly like a
Gemini one. So the rule is structural rather than editorial: reports carry the
tier that wrote them, and only client-grade tiers may be exported, printed or
shared.

Unknown provenance counts as internal_only throughout. Every legacy row is in
that state, which is deliberate: a report we cannot vouch for is regenerated,
not shipped.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.provider_tiers import CLIENT_GRADE, INTERNAL_ONLY
from app.routers import youtube_prospects as router

CHANNEL_ID = "UC_willpower"


def _row(grade, index=1, name="Tier 1: Gemini (primary key)", model="gemini/gemini-3.7-flash"):
    """One persisted youtube_prospect_reports row."""
    return {
        "payload_json": {"verdict": "ok"},
        "model": "Gemini 3.7 Flash",
        "weeks": 4,
        "created_at": "2026-08-29T12:00:00+00:00",
        "tier_index": index,
        "tier_name": name,
        "tier_grade": grade,
        "resolved_model": model,
    }


#: A row written before tier tracking existed. The migration backfills
#: tier_grade to 'internal_only'; the other columns stay NULL.
LEGACY_ROW = {
    "payload_json": {"verdict": "ok"},
    "model": "Gemini 3.6 Flash",
    "weeks": 4,
    "created_at": "2025-01-01T00:00:00+00:00",
    "tier_index": None,
    "tier_name": None,
    "tier_grade": INTERNAL_ONLY,
    "resolved_model": None,
}


@pytest.fixture
def saved(monkeypatch):
    """Serve one prospect + a pair of report rows from the query layer."""

    def _install(audit_row, roadmap_row=None):
        roadmap_row = roadmap_row if roadmap_row is not None else audit_row

        async def get_prospect(session, user_id, channel_id):
            return {
                "id": "p1",
                "channel_id": CHANNEL_ID,
                "title": "WillPower Star",
                "handle": "@willpowerstar",
                "description": "",
                "thumbnail_url": "",
                "country": "IN",
                "subscriber_count": 2_400_000,
                "view_count": 100_000_000,
                "video_count": 18,
                "metrics_json": {"video_count_analyzed": 18},
                "headline_json": None,
                "outreach_line": "hi",
                "outreach_status": "new",
                "duration_available": True,
            }

        async def get_latest(session, user_id, prospect_id, kind):
            return audit_row if kind == "audit" else roadmap_row

        monkeypatch.setattr(router.queries, "get_prospect", get_prospect)
        monkeypatch.setattr(router.queries, "get_latest_prospect_report", get_latest)

    return _install


def _get(surface):
    return asyncio.run(
        router.get_saved_report(
            CHANNEL_ID, surface=surface, user={"id": "u1"}, session=None
        )
    )


# ── The gate ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("surface", ["pdf", "print", "share"])
def test_client_surfaces_are_blocked_for_an_internal_only_audit(saved, surface):
    saved(_row(INTERNAL_ONLY, index=5, name="Tier 5: Ollama local (Qwen 2.5)",
               model="ollama/qwen2.5:latest"))
    with pytest.raises(HTTPException) as err:
        _get(surface)
    assert err.value.status_code == 409


@pytest.mark.parametrize("surface", ["pdf", "print", "share"])
def test_client_surfaces_are_allowed_for_a_client_grade_audit(saved, surface):
    saved(_row(CLIENT_GRADE))
    result = _get(surface)
    assert result["tier"]["grade"] == CLIENT_GRADE


def test_the_internal_dashboard_still_reads_a_fallback_audit(saved):
    """The banner needs something to warn about.

    Blocking the operator's own view would hide the problem rather than surface
    it, which is the failure mode this whole change is about.
    """
    saved(_row(INTERNAL_ONLY, index=3, name="Tier 3: OpenRouter (Nemotron 3 Ultra)"))
    result = _get("internal")
    assert result["tier"]["grade"] == INTERNAL_ONLY
    assert result["audit"] == {"verdict": "ok"}


def test_legacy_rows_are_blocked(saved):
    """Provenance was never recorded for these, so they fail closed."""
    saved(LEGACY_ROW)
    with pytest.raises(HTTPException) as err:
        _get("pdf")
    assert err.value.status_code == 409
    assert _get("internal")["tier"]["grade"] == INTERNAL_ONLY


def test_a_client_grade_audit_with_a_fallback_roadmap_is_blocked(saved):
    """A deliverable is only as good as its weaker half.

    Quota can run out between the two calls, and half a client-grade report is
    not a client-grade report.
    """
    saved(_row(CLIENT_GRADE), _row(INTERNAL_ONLY, index=4, name="Tier 4: Ollama Cloud"))
    with pytest.raises(HTTPException) as err:
        _get("share")
    assert err.value.status_code == 409


# ── What the client is told ──────────────────────────────────────────────────
def test_the_block_message_names_no_model(saved):
    """Which fallback wrote it is operational detail, not client-facing."""
    saved(_row(INTERNAL_ONLY, index=5, name="Tier 5: Ollama local (Qwen 2.5)",
               model="ollama/qwen2.5:latest"))
    with pytest.raises(HTTPException) as err:
        _get("pdf")

    detail = str(err.value.detail).lower()
    for leak in ("qwen", "ollama", "nemotron", "gemini", "gemma", "tier 5", "openrouter"):
        assert leak not in detail, f"{leak!r} leaked into a client-facing error"
    assert "regenerate" in detail


def test_the_block_message_says_what_to_do(saved):
    saved(_row(INTERNAL_ONLY))
    with pytest.raises(HTTPException) as err:
        _get("print")
    assert "fallback model" in str(err.value.detail)


# ── The PDF route reads through the gate ─────────────────────────────────────
def test_pdf_export_is_blocked_before_any_rendering(saved, monkeypatch):
    """The 409 must come from the gate, not from a failed render."""
    saved(_row(INTERNAL_ONLY))

    called = {"rendered": False}

    async def never(_report):
        called["rendered"] = True
        return b"%PDF"

    import app.services.pdf_export_service as pdf_export
    monkeypatch.setattr(pdf_export, "generate_prospect_pdf", never)

    with pytest.raises(HTTPException) as err:
        asyncio.run(
            router.export_prospect_pdf(CHANNEL_ID, user={"id": "u1"}, session=None)
        )
    assert err.value.status_code == 409
    assert not called["rendered"], "the PDF was rendered before the gate ran"


def test_pdf_export_succeeds_for_a_client_grade_audit(saved, monkeypatch):
    saved(_row(CLIENT_GRADE))

    async def render(_report):
        return b"%PDF-1.4 fake"

    import app.services.pdf_export_service as pdf_export
    monkeypatch.setattr(pdf_export, "generate_prospect_pdf", render)

    response = asyncio.run(
        router.export_prospect_pdf(CHANNEL_ID, user={"id": "u1"}, session=None)
    )
    assert response.media_type == "application/pdf"
    assert response.body == b"%PDF-1.4 fake"


# ── Provenance reassembled from the columns ──────────────────────────────────
def test_row_tier_reports_the_weaker_half():
    tier = router._row_tier(
        _row(CLIENT_GRADE, index=1),
        _row(INTERNAL_ONLY, index=4, name="Tier 4: Ollama Cloud", model="ollama/gemma4:31b-cloud"),
    )
    assert tier["grade"] == INTERNAL_ONLY
    assert tier["index"] == 4
    assert tier["model"] == "ollama/gemma4:31b-cloud"


def test_row_tier_is_client_grade_only_when_both_halves_are():
    tier = router._row_tier(_row(CLIENT_GRADE, index=1), _row(CLIENT_GRADE, index=2))
    assert tier["grade"] == CLIENT_GRADE
    assert tier["index"] == 2
