"""
YouTube competitor discovery, verification and video sync.

Discovery is hybrid and verification-gated:
1. Direct YouTube channel search via YouTube for real, active creator channels in the user's niche.
2. LLM / web search candidate proposal (app.services.youtube_ai_analysis.propose_competitors).
3. If Google OAuth is connected, candidates are verified against the official YouTube Data API.
   If Google OAuth is not connected, channels are verified directly against YouTube.
4. Already-tracked channels in ANY status (approved, rejected, or archived) and the user's own channel
   are excluded.
5. Videos are synced via YouTube Data API or YouTube RSS feeds.
"""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET

import requests
from googleapiclient.errors import HttpError

from app.services.youtube_data import _service, _wrap_http_error

logger = logging.getLogger(__name__)

# Quota units (per YouTube Data API v3 pricing): channels.list / playlistItems.list
# / videos.list = 1 unit each; search.list = 100 units.
LOOKUP_COST = 1
SEARCH_FALLBACK_COST = 100
SEARCH_FALLBACK_CAP = 5          # max search.list calls in one discovery run
DISCOVERY_OVERFETCH = 40         # ask the LLM for more than `count` to survive verification + exclusion
DEFAULT_VIDEO_SYNC_LIMIT = 10


class QuotaLedger:
    """Tracks quota spend for one discovery or sync run."""

    def __init__(self, budget: int = 10_000):
        self.budget = budget
        self.spent = 0
        self.search_calls = 0

    def spend(self, cost: int) -> None:
        self.spent += cost

    def can_search(self) -> bool:
        return self.search_calls < SEARCH_FALLBACK_CAP and self.spent < self.budget


class QuotaExhausted(Exception):
    pass


def _parse_subscriber_count(text: str) -> int:
    """Parse strings like '137K subscribers', '1.2M subscribers', '540 subscribers' into integers."""
    if not text:
        return 0
    t = text.lower().replace("subscribers", "").replace("subscriber", "").replace(",", "").strip()
    try:
        if "m" in t:
            return int(float(t.replace("m", "").strip()) * 1_000_000)
        if "k" in t:
            return int(float(t.replace("k", "").strip()) * 1_000)
        return int(float(t))
    except Exception:
        return 0


def search_youtube_channels_direct(query: str, limit: int = 20) -> list[dict]:
    """Search YouTube directly for channels matching `query`."""
    if not query:
        return []
    try:
        import scrapetube

        results = scrapetube.get_search(query, limit=limit, results_type="channel")
        channels: list[dict] = []
        seen: set[str] = set()

        for item in results:
            cid = item.get("channelId")
            if not cid or cid in seen:
                continue
            seen.add(cid)

            title = (
                item.get("title", {}).get("simpleText")
                or (item.get("title", {}).get("runs", [{}])[0].get("text") if item.get("title") else "")
                or "YouTube Creator"
            )
            thumbs = item.get("thumbnail", {}).get("thumbnails", [{}])
            thumb_url = thumbs[-1].get("url", "") if thumbs else ""
            if thumb_url.startswith("//"):
                thumb_url = f"https:{thumb_url}"

            sub_text = (
                item.get("subscriberCountText", {}).get("simpleText")
                or item.get("videoCountText", {}).get("simpleText")
                or ""
            )
            desc = ""
            if item.get("descriptionSnippet") and item["descriptionSnippet"].get("runs"):
                desc = "".join(r.get("text", "") for r in item["descriptionSnippet"]["runs"])

            handle = sub_text if sub_text.startswith("@") else ""
            sub_count = _parse_subscriber_count(sub_text) if not handle else 0

            channels.append({
                "channel_id": cid,
                "title": title,
                "handle": handle,
                "description": desc[:1500],
                "thumbnail_url": thumb_url,
                "uploads_playlist_id": f"UU{cid[2:]}" if cid.startswith("UC") else "",
                "subscriber_count": sub_count,
                "view_count": 0,
                "video_count": 0,
                "rationale": f"Direct YouTube match for \"{query}\"",
                "tier": "peer",
                "name": title,
            })
        return channels
    except Exception as exc:
        logger.warning("Direct YouTube channel search failed: %s", exc)
        return []


def _resolve_by_ids(yt, channel_ids: list[str], ledger: QuotaLedger) -> dict[str, dict]:
    """channels.list by id, batched at 50. 1 quota unit per batch of 50."""
    out: dict[str, dict] = {}
    for i in range(0, len(channel_ids), 50):
        chunk = channel_ids[i : i + 50]
        if not chunk:
            continue
        try:
            resp = (
                yt.channels()
                .list(part="snippet,statistics,contentDetails", id=",".join(chunk))
                .execute()
            )
        except HttpError as exc:
            logger.warning("channels.list by id failed: %s", exc)
            continue
        ledger.spend(LOOKUP_COST)
        for item in resp.get("items", []):
            out[item["id"]] = item
    return out


def _resolve_by_handle(yt, handle: str, ledger: QuotaLedger) -> dict | None:
    if not handle:
        return None
    handle = handle if handle.startswith("@") else f"@{handle}"
    try:
        resp = (
            yt.channels()
            .list(part="snippet,statistics,contentDetails", forHandle=handle)
            .execute()
        )
    except HttpError as exc:
        logger.info("forHandle lookup failed for %s: %s", handle, exc)
        return None
    ledger.spend(LOOKUP_COST)
    items = resp.get("items", [])
    return items[0] if items else None


def _resolve_by_search(yt, query: str, ledger: QuotaLedger) -> dict | None:
    """100-unit fallback — only used when handle/id resolution failed and the
    per-run search cap hasn't been hit."""
    if not query or not ledger.can_search():
        return None
    ledger.search_calls += 1
    ledger.spend(SEARCH_FALLBACK_COST)
    try:
        resp = yt.search().list(part="snippet", type="channel", q=query, maxResults=1).execute()
    except HttpError as exc:
        logger.info("search.list fallback failed for %r: %s", query, exc)
        return None
    items = resp.get("items", [])
    if not items:
        return None
    channel_id = (items[0].get("id") or {}).get("channelId")
    if not channel_id:
        return None
    resolved = _resolve_by_ids(yt, [channel_id], ledger)
    return resolved.get(channel_id)


def _to_row(candidate: dict, item: dict) -> dict:
    """A verified channels.list item -> the dict shape callers/DB expect."""
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})
    thumbs = snippet.get("thumbnails", {})
    return {
        "channel_id": item["id"],
        "title": snippet.get("title") or candidate.get("name", "") or candidate.get("title", ""),
        "handle": snippet.get("customUrl") or candidate.get("handle", ""),
        "description": (snippet.get("description") or candidate.get("description", ""))[:1500],
        "thumbnail_url": (thumbs.get("high") or thumbs.get("default") or {}).get("url") or candidate.get("thumbnail_url"),
        "uploads_playlist_id": (item.get("contentDetails", {}).get("relatedPlaylists", {}) or {}).get(
            "uploads"
        ) or (f"UU{item['id'][2:]}" if item["id"].startswith("UC") else ""),
        "country": snippet.get("country"),
        "subscriber_count": int(stats.get("subscriberCount", 0) or candidate.get("subscriber_count", 0) or 0),
        "view_count": int(stats.get("viewCount", 0) or candidate.get("view_count", 0) or 0),
        "video_count": int(stats.get("videoCount", 0) or candidate.get("video_count", 0) or 0),
        "rationale": candidate.get("rationale") or candidate.get("why", ""),
        "tier": candidate.get("tier") or "peer",
    }


def get_own_channel_id(user_id: str) -> str | None:
    """1 quota unit. Used so discovery never proposes the user's own channel."""
    try:
        yt = _service(user_id)
        resp = yt.channels().list(part="id", mine=True).execute()
        items = resp.get("items", [])
        return items[0]["id"] if items else None
    except Exception:
        return None


def verify_candidates(user_id: str, candidates: list[dict], ledger: QuotaLedger) -> list[dict]:
    """Confirm every candidate against YouTube (Data API if connected, or direct metadata)."""
    yt = None
    try:
        yt = _service(user_id)
    except Exception:
        yt = None

    if yt is not None:
        with_ids = [c for c in candidates if c.get("channel_id")]
        without_ids = [c for c in candidates if not c.get("channel_id")]

        resolved_by_id = _resolve_by_ids(yt, [c["channel_id"] for c in with_ids], ledger)

        verified: list[dict] = []
        seen: set[str] = set()

        def _keep(candidate: dict, item: dict | None) -> None:
            if not item:
                return
            cid = item["id"]
            if cid in seen:
                return
            stats = item.get("statistics", {})
            if int(stats.get("subscriberCount", 0) or 0) == 0 and int(stats.get("videoCount", 0) or 0) == 0:
                return  # dead/empty channel — not a real competitor
            seen.add(cid)
            verified.append(_to_row(candidate, item))

        for c in with_ids:
            _keep(c, resolved_by_id.get(c["channel_id"]))

        for c in without_ids:
            item = _resolve_by_handle(yt, c.get("handle", ""), ledger) if c.get("handle") else None
            if not item:
                item = _resolve_by_search(yt, c.get("name", ""), ledger)
            _keep(c, item)

        if verified:
            return verified

    # Fallback or unauthenticated direct YouTube verification
    verified_direct: list[dict] = []
    seen = set()
    for c in candidates:
        cid = c.get("channel_id")
        if not cid:
            query = c.get("handle") or c.get("name") or c.get("title")
            if query:
                direct_matches = search_youtube_channels_direct(query, limit=1)
                if direct_matches:
                    c = {**c, **direct_matches[0]}
                    cid = c.get("channel_id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        uploads_id = c.get("uploads_playlist_id") or (f"UU{cid[2:]}" if cid.startswith("UC") else "")
        verified_direct.append({
            "channel_id": cid,
            "title": c.get("title") or c.get("name", "YouTube Creator"),
            "handle": c.get("handle", ""),
            "description": (c.get("description") or "")[:1500],
            "thumbnail_url": c.get("thumbnail_url") or "",
            "uploads_playlist_id": uploads_id,
            "country": c.get("country"),
            "subscriber_count": int(c.get("subscriber_count") or 0),
            "view_count": int(c.get("view_count") or 0),
            "video_count": int(c.get("video_count") or 0),
            "rationale": c.get("rationale") or c.get("why", "Top creator in this niche"),
            "tier": c.get("tier") or "peer",
        })
    return verified_direct


def _sync_videos_via_rss(channel_id: str, limit: int = DEFAULT_VIDEO_SYNC_LIMIT) -> list[dict]:
    """Fetch latest videos directly via public YouTube RSS feed without OAuth."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "media": "http://search.yahoo.com/mrss/",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        videos: list[dict] = []
        for entry in root.findall("atom:entry", ns)[:limit]:
            title_el = entry.find("atom:title", ns)
            vid_el = entry.find("yt:videoId", ns)
            pub_el = entry.find("atom:published", ns)
            media_group = entry.find("media:group", ns)
            desc_el = media_group.find("media:description", ns) if media_group is not None else None
            views = 0
            likes = 0
            thumb_url = ""
            if media_group is not None:
                comm = media_group.find("media:community", ns)
                if comm is not None:
                    stats = comm.find("media:statistics", ns)
                    if stats is not None:
                        views = int(stats.get("views", 0) or 0)
                    star = comm.find("media:starRating", ns)
                    if star is not None:
                        likes = int(star.get("count", 0) or 0)
                thumb = media_group.find("media:thumbnail", ns)
                if thumb is not None:
                    thumb_url = thumb.get("url", "")

            vid = vid_el.text.strip() if vid_el is not None and vid_el.text else ""
            if not vid:
                continue

            videos.append({
                "video_id": vid,
                "channel_id": channel_id,
                "title": title_el.text.strip() if title_el is not None and title_el.text else "",
                "description": (desc_el.text.strip() if desc_el is not None and desc_el.text else "")[:1500],
                "published_at": pub_el.text.strip() if pub_el is not None and pub_el.text else "",
                "duration_seconds": 0,
                "is_short": False,
                "views": views,
                "likes": likes,
                "comments": 0,
                "tags": [],
                "thumbnail_url": thumb_url,
            })
        return videos
    except Exception as exc:
        logger.warning("RSS video sync failed for channel %s: %s", channel_id, exc)
        return []


def sync_competitor_videos(
    user_id: str, channel_id: str, uploads_playlist_id: str, ledger: QuotaLedger,
    limit: int = DEFAULT_VIDEO_SYNC_LIMIT,
) -> list[dict]:
    """Latest ``limit`` videos for one competitor channel.
    Uses official YouTube Data API when connected, or falls back to public RSS feed."""
    yt = None
    try:
        yt = _service(user_id)
    except Exception:
        yt = None

    if yt is not None and uploads_playlist_id:
        try:
            resp = (
                yt.playlistItems()
                .list(part="contentDetails", playlistId=uploads_playlist_id, maxResults=min(limit, 50))
                .execute()
            )
            ledger.spend(LOOKUP_COST)
            video_ids = [
                it["contentDetails"]["videoId"]
                for it in resp.get("items", [])
                if it.get("contentDetails", {}).get("videoId")
            ]
            if video_ids:
                v_resp = yt.videos().list(part="snippet,contentDetails,statistics", id=",".join(video_ids)).execute()
                ledger.spend(LOOKUP_COST)
                from app.services.youtube_sync_service import _parse_duration

                videos: list[dict] = []
                for item in v_resp.get("items", []):
                    snippet = item.get("snippet", {})
                    stats = item.get("statistics", {})
                    duration = _parse_duration(item.get("contentDetails", {}).get("duration", ""))
                    thumbs = snippet.get("thumbnails", {})
                    videos.append({
                        "video_id": item["id"],
                        "channel_id": channel_id,
                        "title": snippet.get("title", ""),
                        "description": (snippet.get("description") or "")[:1500],
                        "published_at": snippet.get("publishedAt"),
                        "duration_seconds": duration,
                        "is_short": duration > 0 and duration <= 60,
                        "views": int(stats.get("viewCount", 0) or 0),
                        "likes": int(stats.get("likeCount", 0) or 0),
                        "comments": int(stats.get("commentCount", 0) or 0),
                        "tags": snippet.get("tags") or [],
                        "thumbnail_url": (thumbs.get("high") or thumbs.get("default") or {}).get("url"),
                    })
                return videos
        except Exception as exc:
            logger.warning("YouTube API video sync failed for %s (%s), falling back to RSS", channel_id, exc)

    return _sync_videos_via_rss(channel_id, limit=limit)


# ── Discovery orchestration (async — the router-facing entry points) ─────────


async def _own_channel_context(session, user_id: str) -> tuple[str, str]:
    """(context_text, niche_guess) from this user's own synced videos."""
    from app.db import queries

    titles = await queries.get_recent_youtube_titles(session, user_id, limit=10)
    if not titles:
        return "", ""
    lines = [f"- {t['title']}" for t in titles]
    all_tags = [tag for t in titles for tag in (t.get("tags") or [])]
    niche_guess = " ".join(dict.fromkeys(all_tags[:6]))
    return "This creator's recent videos:\n" + "\n".join(lines), niche_guess


async def run_discovery(session, user_id: str, niche: str = "", count: int = 20) -> dict:
    """Discover competitor channels directly from YouTube and AI analysis.

    Channels already tracked (any status) and the user's own channel are excluded.
    Candidates are verified and staged for user approval.
    """
    from app.db import queries
    from app.services import youtube_ai_analysis
    from app.services.personal_intelligence import get_directives

    run = await queries.create_competitor_discovery_run(session, user_id, niche)

    own_context, niche_guess = await _own_channel_context(session, user_id)
    effective_niche = niche or niche_guess or "tech coding and AI"

    exclude_names = await queries.list_competitor_names(session, user_id, limit=150)
    directives = await get_directives(session, user_id, scope="youtube")
    own_channel_id = await asyncio.to_thread(get_own_channel_id, user_id)

    verified_all: list[dict] = []
    seen_ids: set[str] = {own_channel_id} if own_channel_id else set()
    ledger = QuotaLedger()

    # 1. Primary: Search YouTube directly for active channels in this niche
    direct_candidates = await asyncio.to_thread(search_youtube_channels_direct, effective_niche, count * 2)
    if direct_candidates:
        verified_direct = await asyncio.to_thread(verify_candidates, user_id, direct_candidates, ledger)
        new_ids = [v["channel_id"] for v in verified_direct if v["channel_id"] not in seen_ids]
        if new_ids:
            known = await queries.filter_known_competitor_ids(session, user_id, new_ids)
        else:
            known = set()

        for v in verified_direct:
            cid = v["channel_id"]
            if cid in seen_ids or cid in known:
                continue
            seen_ids.add(cid)
            verified_all.append(v)
            if len(verified_all) >= count:
                break

    # 2. Secondary: If more channels are needed, run AI proposal & web research
    if len(verified_all) < count:
        try:
            from app.tools.custom import run_web_search

            web_context = await asyncio.to_thread(
                run_web_search, f"best YouTube channels {effective_niche} 2026", 6
            )
        except Exception as exc:
            logger.warning("Competitor discovery web search failed: %s", exc)
            web_context = ""

        rounds = 0
        max_rounds = 2
        while len(verified_all) < count and rounds < max_rounds:
            rounds += 1
            already_named = exclude_names + [v["title"] for v in verified_all]
            try:
                proposed = await youtube_ai_analysis.propose_competitors(
                    own_context, effective_niche, web_context, already_named,
                    count=DISCOVERY_OVERFETCH, directives=directives,
                )
            except Exception as e:
                logger.warning("AI propose_competitors failed: %s", e)
                proposed = []

            if not proposed:
                break

            verified = await asyncio.to_thread(verify_candidates, user_id, proposed, ledger)
            new_ids = [v["channel_id"] for v in verified if v["channel_id"] not in seen_ids]
            if new_ids:
                known = await queries.filter_known_competitor_ids(session, user_id, new_ids)
            else:
                known = set()

            for v in verified:
                cid = v["channel_id"]
                if cid in seen_ids or cid in known:
                    continue
                seen_ids.add(cid)
                verified_all.append(v)
                if len(verified_all) >= count:
                    break

    verified_all = verified_all[:count]
    for v in verified_all:
        v["niche"] = effective_niche

    await queries.complete_discovery_run(session, run["id"], user_id, verified_all, ledger.spent)
    run["candidates"] = verified_all
    run["quota_units_spent"] = ledger.spent
    run["status"] = "pending"
    return run


async def approve_candidates(
    session, user_id: str, run_id: str, approved_ids: list[str], rejected_ids: list[str]
) -> dict:
    """Persist the user's approve/reject decisions from a discovery run.

    Approved rows carry full stats and become ``status='approved'``; rejected
    rows are kept as ``status='rejected'`` tombstones — filter_known_competitor_ids
    matches on channel_id in ANY status, so a rejected channel is never proposed
    again. Approved competitors are synced immediately.
    """
    from app.db import queries

    run = await queries.get_competitor_discovery_run(session, run_id, user_id)
    if not run:
        raise ValueError("Discovery run not found")

    by_id = {c["channel_id"]: c for c in (run.get("candidates") or [])}

    approved_rows = []
    for cid in approved_ids:
        c = by_id.get(cid)
        if not c:
            continue
        approved_rows.append({**c, "status": "approved", "discovered_by": "direct_youtube", "source_run_id": run_id})

    rejected_rows = []
    for cid in rejected_ids:
        c = by_id.get(cid)
        if not c:
            continue
        rejected_rows.append(
            {
                "channel_id": cid,
                "title": c.get("title", ""),
                "status": "rejected",
                "discovered_by": "direct_youtube",
                "source_run_id": run_id,
            }
        )

    if approved_rows:
        await queries.bulk_upsert_competitors(session, user_id, approved_rows)
    if rejected_rows:
        await queries.bulk_upsert_competitors(session, user_id, rejected_rows)

    await queries.decide_discovery_run(session, run_id, user_id, len(approved_rows), len(rejected_rows))

    # Immediate video sync for newly approved channels so the tab has data on first load
    synced = 0
    if approved_rows:
        ledger = QuotaLedger()
        for row in approved_rows:
            cid = row["channel_id"]
            uploads_id = row.get("uploads_playlist_id") or (f"UU{cid[2:]}" if cid.startswith("UC") else "")
            try:
                videos = await asyncio.to_thread(
                    sync_competitor_videos, user_id, cid,
                    uploads_id, ledger,
                )
                if videos:
                    await queries.bulk_upsert_competitor_videos(session, user_id, videos)
                    synced += 1
            except Exception as exc:
                logger.warning("Initial video sync failed for %s: %s", cid, exc)

    return {"approved": len(approved_rows), "rejected": len(rejected_rows), "videos_synced": synced}
