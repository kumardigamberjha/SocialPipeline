"""
Prospect audits: point the channel-analysis engine at someone else's channel.

Given a channel name, @handle, URL or id, this resolves the channel from public
data, pulls its upload history, and produces the same two artefacts the owner's
own channel gets — a strategy audit and a 4-week roadmap — plus a copy-ready
outreach line whose numbers are computed in Python, never by the model.

The AI layer is reused wholesale from ``app.services.youtube_ai_analysis``:
``analyze_strategy`` and ``generate_roadmap`` both take a plain-text context
string, so pointing them at a third-party channel needs a different context
builder (``app.services.youtube_prospect_service``), not different prompts.
That also keeps the payloads byte-compatible with the dashboard's existing
Strategy/Roadmap renderers.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth_deps import get_current_user
from app.db import queries
from app.db.session import get_session
from app.models.prospects import ProspectLookupRequest, UpdateProspectRequest
from app.provider_tiers import CLIENT_GRADE, UNKNOWN_GRADE
from app.routers.youtube_analytics import _domain_key, _get_cached, _set_cached
from app.services import youtube_channel_lookup as lookup
from app.services import youtube_prospect_service as prospects

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/youtube-prospects", tags=["YouTube Prospects"])

MAX_WEEKS = 8
UPLOAD_LIMIT = 200
# The trend scrape is a nice-to-have on a request that already spends two LLM
# calls behind a proxy timeout. Cap it rather than let a hanging fetch decide how
# long the audit takes.
TREND_TIMEOUT_SECONDS = 20

# Channel fields persisted on the prospect row (the rest of the resolver's
# output is display-only and lives in the report payload).
_CHANNEL_COLUMNS = (
    "channel_id", "title", "handle", "description",
    "thumbnail_url", "country", "subscriber_count", "view_count", "video_count",
)


def _map_error(exc: Exception) -> HTTPException:
    """Same mapping as the competitor router — the same OAuth failures apply."""
    from app.services.google_calendar import NotConnectedError
    from app.services.youtube_data import YoutubeApiDisabledError, YoutubeDataError, YoutubeScopeError

    if isinstance(exc, YoutubeScopeError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, NotConnectedError):
        return HTTPException(status_code=400, detail=str(exc) or "Google account not connected.")
    if isinstance(exc, YoutubeApiDisabledError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, YoutubeDataError):
        return HTTPException(status_code=502, detail=str(exc))
    logger.exception("Unexpected prospect lookup error")
    return HTTPException(status_code=502, detail=f"Channel lookup failed: {exc}")


def _map_llm_error(exc: Exception) -> HTTPException:
    """Turn a cascade failure into something the user can act on.

    The analysis cascade (Gemini -> backup key -> Ollama Qwen 2.5 -> NVIDIA) only
    raises once every tier has failed. By far the most common cause is the
    Gemini free tier's daily cap, and "Report generation failed:
    litellm.RateLimitError: ..." tells the user nothing they can use — the
    actionable fact is that it is a quota ceiling that resets, not a bug in
    their query.
    """
    text = str(exc)
    lowered = text.lower()
    if "429" in text or "rate limit" in lowered or "resource_exhausted" in lowered or "quota" in lowered:
        return HTTPException(
            status_code=429,
            detail=(
                "The AI provider's request quota is exhausted, so the audit could not be "
                "generated. The channel data was fetched fine — retry once the quota resets, "
                "or add a provider key with remaining capacity."
            ),
        )
    return HTTPException(status_code=502, detail=f"Report generation failed: {exc}")


@router.post("/lookup")
async def lookup_channel(
    body: ProspectLookupRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """Resolve a channel and return a preview. No LLM call, nothing persisted.

    Separate from ``/report`` so the user confirms they got the right creator
    before spending two LLM calls on the wrong one.
    """
    try:
        channel = await asyncio.to_thread(lookup.resolve_channel, user["id"], body.query)
    except Exception as exc:
        raise _map_error(exc)

    if not channel:
        raise HTTPException(
            status_code=404,
            detail="No YouTube channel matched that name, handle or URL.",
        )
    return {"channel": channel}


@router.post("/{channel_id}/report")
async def generate_report(
    channel_id: str,
    weeks: int = 4,
    refresh: bool = False,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Full audit + roadmap for one channel, persisted as a prospect."""
    user_id = user["id"]
    weeks = max(1, min(weeks, MAX_WEEKS))

    # Redis is an optimisation here, not a dependency: a cache blip must not
    # cost the caller two LLM calls, and must never surface as a 500.
    cache_key = None
    try:
        cache_key = await _domain_key(user_id, "yt-prospect", channel_id, str(weeks))
        if not refresh:
            cached = await _get_cached(cache_key)
            if cached:
                return cached
    except Exception:
        logger.warning("Prospect cache unavailable; generating uncached", exc_info=True)
        cache_key = None

    try:
        channel = await asyncio.to_thread(lookup.resolve_channel, user_id, channel_id)
    except Exception as exc:
        raise _map_error(exc)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found on YouTube.")

    try:
        videos, duration_available = await asyncio.to_thread(
            lookup.fetch_channel_uploads,
            user_id,
            channel["channel_id"],
            channel.get("uploads_playlist_id", ""),
            None,
            UPLOAD_LIMIT,
        )
    except Exception as exc:
        raise _map_error(exc)

    if not videos:
        raise HTTPException(
            status_code=404,
            detail="That channel has no public videos to analyse.",
        )

    # Reconcile channel upload count with actual fetched uploads.
    # YouTube's channels.list statistics.videoCount is often stale, cached, or excludes Shorts.
    # The uploads playlist is ground truth for the actual videos that exist.
    actual_count = len(videos)
    if actual_count < UPLOAD_LIMIT or int(channel.get("video_count") or 0) < actual_count:
        channel["video_count"] = actual_count

    # Niche keywords come from the channel's own titles, same as the owner flow.
    from app.services.youtube_metrics import extract_keywords
    from app.services import youtube_trend_source as trend_source

    keywords = extract_keywords(
        [v.get("title") or "" for v in videos],
        8,
        channel_title=channel.get("title") or "",
        channel_handle=channel.get("handle") or "",
    )
    # Trend context sharpens the roadmap but is not required for it, and it comes
    # from YouTube rather than the general web: app.tools.research_engine is wired
    # to Hacker News, ArXiv, GitHub Trending and a fixed set of tech subreddits, so
    # it answered a cooking channel's audit with LLM tooling and pulled every
    # roadmap toward one niche. Searching YouTube on this channel's own keywords is
    # on-niche by construction. Best-effort: a scrape failure degrades the prompt,
    # never the request.
    try:
        web_context = await asyncio.wait_for(
            asyncio.to_thread(
                trend_source.build_niche_trend_context,
                keywords,
                channel["channel_id"],
                channel.get("title") or "",
            ),
            timeout=TREND_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.warning("YouTube trend search failed; continuing without it", exc_info=True)
        web_context = ""

    try:
        report = await prospects.generate_prospect_report(
            channel, videos, duration_available, weeks, web_context
        )
    except Exception as exc:
        logger.exception("Prospect report generation failed for %s", channel_id)
        raise _map_llm_error(exc)

    report = await _persist_report(session, user_id, report)

    if cache_key:
        try:
            await _set_cached(cache_key, report)
        except Exception:
            logger.warning("Could not cache prospect report", exc_info=True)
    return report


async def _persist_report(session: AsyncSession, user_id: str, report: dict) -> dict:
    """Save the prospect + both report halves, stamping ids onto the response.

    Best-effort: a persistence failure must not throw away a report the user
    already paid two LLM calls for.
    """
    channel = report["channel"]
    try:
        row = {k: channel.get(k) for k in _CHANNEL_COLUMNS}
        row["metrics_json"] = report["metrics"]
        row["headline_json"] = report["headline"]
        row["outreach_line"] = report["outreach_line"]
        row["duration_available"] = report["duration_available"]
        row["last_report_at"] = datetime.now(timezone.utc)
        prospect = await queries.upsert_prospect(session, user_id, row)

        for kind in ("audit", "roadmap"):
            await queries.create_prospect_report(
                session,
                user_id,
                prospect["id"],
                kind,
                report[kind],
                weeks=report.get("weeks") if kind == "roadmap" else None,
                model=report.get("model"),
                # Per-half provenance, falling back to the report-level tier
                # so a half generated before provenance existed still records
                # the (weaker) grade of the deliverable it belongs to.
                tier=(report[kind] or {}).get("tier") or report.get("tier"),
            )
        report["prospect_id"] = prospect["id"]
        report["outreach_status"] = prospect["outreach_status"]
    except Exception:
        # Roll back explicitly. `get_session` commits after this handler
        # returns, and a swallowed error leaves the transaction in Postgres'
        # aborted state — that commit then fails and FastAPI turns it into a
        # bare 500, discarding a report that had already been generated. The
        # rollback makes "saving failed" cost only the save.
        logger.exception("Could not save prospect report")
        try:
            await session.rollback()
        except Exception:
            logger.exception("Rollback after failed prospect save also failed")
    return report


def _row_tier(audit_row: dict, roadmap_row: dict) -> dict:
    """Report-level provenance, reassembled from the two persisted halves.

    Mirrors ``youtube_prospect_service._combine_tiers``, but reads the columns
    rather than the generated payload — so a report loaded from the database is
    graded by what was actually stored, not by what a payload claims about
    itself. Legacy rows carry the backfilled ``internal_only`` and stay blocked.
    """
    grades = [
        (row or {}).get("tier_grade") or UNKNOWN_GRADE
        for row in (audit_row, roadmap_row)
    ]
    grade = CLIENT_GRADE if all(g == CLIENT_GRADE for g in grades) else UNKNOWN_GRADE
    worst = max(
        (audit_row or {}, roadmap_row or {}),
        key=lambda r: (r.get("tier_index") or 99),
    )
    return {
        "index": worst.get("tier_index"),
        "name": worst.get("tier_name"),
        "grade": grade,
        "model": worst.get("resolved_model"),
    }


# ── Client-grade gate ────────────────────────────────────────────────────────
# Everything that puts a report in front of someone outside the company goes
# through this one function, so a new export route cannot quietly skip the check.
#
# The message deliberately does NOT name the model. Which fallback wrote a report
# is operational detail; a client reading an error should learn that the report
# needs regenerating, not what is running underneath.
_FALLBACK_BLOCKED_DETAIL = (
    "This audit was generated by a fallback model and is not client-ready. "
    "Regenerate it on a primary model before exporting or sharing."
)

#: Surfaces that put the report in front of a client. "internal" is the operator's
#: own dashboard, which must keep working so the warning banner has something to
#: warn about.
_CLIENT_SURFACES = {"share", "print", "pdf"}


def _require_client_grade(report: dict, surface: str) -> None:
    """Refuse a client-facing surface for a report a fallback model wrote.

    Reads the persisted ``tier.grade``. A report with no grade at all — a legacy
    row, or one whose provenance was lost — is treated as internal_only: unknown
    provenance must fail closed, because the whole point is that nobody could
    tell the difference by looking.
    """
    if surface not in _CLIENT_SURFACES:
        return
    grade = ((report.get("tier") or {}).get("grade")) or UNKNOWN_GRADE
    if grade != CLIENT_GRADE:
        logger.warning(
            "Blocked %s export of a %s audit for prospect %s",
            surface,
            grade,
            (report.get("channel") or {}).get("channel_id"),
        )
        raise HTTPException(status_code=409, detail=_FALLBACK_BLOCKED_DETAIL)


@router.get("")
async def list_prospects(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Saved prospects, newest first."""
    items = await queries.list_prospects(session, user["id"])
    return {"items": items}


@router.get("/{channel_id}")
async def get_saved_report(
    channel_id: str,
    surface: str = "internal",
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The latest saved report — what the shareable report route reads.

    ``surface`` says what this read is *for*: ``internal`` (the operator's
    dashboard), or one of the client-facing surfaces in ``_CLIENT_SURFACES``,
    which are refused for a fallback-generated audit. It is an explicit
    parameter rather than something inferred from the caller's route, because
    the route is chosen by the browser and the grade decision must not be.
    """
    user_id = user["id"]
    prospect = await queries.get_prospect(session, user_id, channel_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found.")

    audit = await queries.get_latest_prospect_report(session, user_id, prospect["id"], "audit")
    roadmap = await queries.get_latest_prospect_report(session, user_id, prospect["id"], "roadmap")
    if not audit or not roadmap:
        raise HTTPException(
            status_code=404,
            detail="No report has been generated for this prospect yet.",
        )

    metrics = prospect.get("metrics_json") or {}
    headline = prospect.get("headline_json")
    channel_data = {k: prospect.get(k) for k in _CHANNEL_COLUMNS}
    if metrics.get("video_count_analyzed"):
        analyzed_count = int(metrics["video_count_analyzed"])
        if int(channel_data.get("video_count") or 0) < analyzed_count or (int(channel_data.get("video_count") or 0) != analyzed_count and analyzed_count < 200):
            channel_data["video_count"] = analyzed_count
    hooks = prospects.build_outreach_hooks(channel_data, metrics, headline)
    raw_model = roadmap.get("model") or audit.get("model")
    tier = _row_tier(audit, roadmap)

    result = {
        "channel": channel_data,
        "metrics": metrics,
        "headline": headline,
        "outreach_line": prospect.get("outreach_line") or hooks.get("primary") or "",
        "outreach_hooks": hooks,
        "similar_channels": metrics.get("similar_channels") or [],
        "outreach_status": prospect.get("outreach_status"),
        "duration_available": prospect.get("duration_available", True),
        "audit": audit["payload_json"],
        "roadmap": roadmap["payload_json"],
        "weeks": roadmap.get("weeks"),
        "generated_at": roadmap.get("created_at"),
        "model": prospects._clean_model_name(raw_model),
        "tier": tier,
        "prospect_id": prospect["id"],
    }
    _require_client_grade(result, surface)
    return result


@router.post("/{channel_id}/regenerate-on-primary")
async def regenerate_on_primary(
    channel_id: str,
    weeks: int = 4,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Rerun an audit that a fallback model wrote, on a primary tier.

    Refuses up front when no client-grade tier is currently available — quota
    still exhausted, keys missing, or both Gemini tiers parked. Running anyway
    would spend two LLM calls to produce another internal_only report and leave
    the user exactly where they started, which is the sort of silent futility
    this whole change exists to remove.
    """
    from app.llm import describe_chain

    settings = get_settings()
    ready = [
        row for row in describe_chain(settings)
        if row["grade"] == CLIENT_GRADE and row["available"]
    ]
    if not ready:
        blocked = [
            row for row in describe_chain(settings) if row["grade"] == CLIENT_GRADE
        ]
        cooling = max((row.get("cooling_for") or 0) for row in blocked) if blocked else 0
        detail = (
            "No primary model is available right now"
            + (f"; quota resets in about {round(cooling / 60)} minutes." if cooling else ".")
            + " Try again shortly."
        )
        logger.warning("Regenerate-on-primary refused for %s: %s", channel_id, detail)
        raise HTTPException(status_code=503, detail=detail)

    # refresh=True so the cached fallback report is not simply handed back.
    return await generate_report(
        channel_id, weeks=weeks, refresh=True, user=user, session=session
    )


@router.get("/{channel_id}/pdf")
async def export_prospect_pdf(
    channel_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Generate and download a high-fidelity A4 PDF of the prospect audit using Playwright."""
    from app.services import pdf_export_service as pdf_export

    # surface="pdf" makes the gate refuse a fallback-generated audit here,
    # before a single byte of PDF is rendered.
    report_data = await get_saved_report(
        channel_id, surface="pdf", user=user, session=session
    )
    try:
        pdf_bytes = await pdf_export.generate_prospect_pdf(report_data)
    except Exception as exc:
        logger.exception("Failed to generate PDF for prospect %s", channel_id)
        raise HTTPException(status_code=500, detail=f"PDF rendering failed: {exc}")

    settings = get_settings()
    brand_prefix = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (getattr(settings, "report_brand_name", "") or "Growth_Intelligence")).strip("_")
    channel_title = (report_data.get("channel") or {}).get("title") or "Channel"
    safe_slug = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in channel_title).strip("_")
    filename = f"{brand_prefix or 'Growth_Intelligence'}_Audit_{safe_slug or 'Prospect'}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
        },
    )


@router.patch("/{channel_id}")
async def update_prospect(
    channel_id: str,
    body: UpdateProspectRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    updated = await queries.update_prospect_status(
        session, user["id"], channel_id, body.outreach_status
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Prospect not found.")
    return updated


@router.delete("/{channel_id}")
async def delete_prospect(
    channel_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    deleted = await queries.delete_prospect(session, user["id"], channel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Prospect not found.")
    return {"deleted": True}
