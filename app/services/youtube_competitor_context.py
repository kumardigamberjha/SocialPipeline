"""
Renders tracked-competitor data into the compact text block the YouTube
analysis and 30-day-planner prompts inject — the reason competitor tracking
exists at all. Pure formatting over app.db.queries reads; never calls the
YouTube API itself.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Character budget: keeps a user with hundreds of tracked competitors from
# blowing out a prompt. Titles are clipped to keep line count meaningful
# rather than truncating mid-block.
COMPETITOR_BLOCK_CHAR_BUDGET = 2500
MAX_CHANNELS = 8
MAX_VIDEOS_PER_CHANNEL = 4


def _clip_title(title: str, limit: int = 90) -> str:
    title = (title or "").strip()
    return title if len(title) <= limit else title[: limit - 1] + "…"


async def build_competitor_block(
    session, user_id: str, max_channels: int = MAX_CHANNELS,
    max_videos_per_channel: int = MAX_VIDEOS_PER_CHANNEL,
    char_budget: int = COMPETITOR_BLOCK_CHAR_BUDGET,
) -> str:
    """Recent competitor uploads, grouped by channel, newest first.

    Best-effort: any failure (including "no competitors tracked yet")
    returns "" so callers can always safely prepend this to a prompt.
    """
    from app.db import queries

    try:
        videos = await queries.get_competitor_recent_videos(session, user_id, days=45, limit=200)
    except Exception as exc:
        logger.warning("build_competitor_block failed for user %s: %s", user_id, exc)
        return ""
    if not videos:
        return ""

    by_channel: dict[str, list[dict]] = {}
    for v in videos:
        by_channel.setdefault(v["channel_id"], []).append(v)

    # Rank channels by total recent views — the ones actually moving.
    ranked = sorted(by_channel.items(), key=lambda kv: sum(x.get("views") or 0 for x in kv[1]), reverse=True)

    lines = [f"COMPETITORS ({len(ranked)} of {len(by_channel)} tracked, most active first):"]
    for channel_id, vids in ranked[:max_channels]:
        lines.append(f"- Channel: {vids[0].get('channel_title') or channel_id}")
        for v in vids[:max_videos_per_channel]:
            published = (v.get("published_at") or "")[:10]
            lines.append(
                f"  · {published} | {_clip_title(v['title'])} — {int(v.get('views') or 0):,} views"
            )

    block = "\n".join(lines)
    if len(block) > char_budget:
        kept: list[str] = []
        total = 0
        for line in lines:
            total += len(line) + 1
            if total > char_budget and kept:
                logger.debug("competitor block clipped at %d/%d chars for user %s", total, char_budget, user_id)
                break
            kept.append(line)
        block = "\n".join(kept)
    return block


async def build_topic_overlap_block(session, user_id: str, title: str, *, limit: int = 6) -> str:
    """Competitor videos with titles similar to ``title`` — used by per-video
    growth recommendations to show what competitors did with the same topic."""
    from app.db import queries

    try:
        videos = await queries.get_competitor_recent_videos(session, user_id, days=180, limit=200)
    except Exception as exc:
        logger.warning("build_topic_overlap_block failed for user %s: %s", user_id, exc)
        return ""
    if not videos or not title:
        return ""

    words = {w.lower() for w in title.split() if len(w) > 3}
    if not words:
        return ""

    scored = []
    for v in videos:
        v_words = {w.lower() for w in (v.get("title") or "").split() if len(w) > 3}
        overlap = len(words & v_words)
        if overlap:
            scored.append((overlap, v))
    scored.sort(key=lambda t: t[0], reverse=True)
    if not scored:
        return ""

    lines = ["COMPETITOR VIDEOS ON A SIMILAR TOPIC:"]
    for _, v in scored[:limit]:
        lines.append(f"- {_clip_title(v['title'])} — {int(v.get('views') or 0):,} views")
    return "\n".join(lines)
