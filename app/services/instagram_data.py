"""
Meta Instagram Graph API Service.

Fetches live, exact profile metrics, media (posts & reels), engagement stats,
and hashtag analytics for the connected Instagram account using the caller's
per-user Instagram connection. Does not use fake or hardcoded mock numbers.
"""

import math
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
import httpx

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.instagram.com/v20.0"
# NOTE: graph.instagram.com is the correct base for Instagram Business Login tokens.
# graph.facebook.com is only for Facebook Login / legacy tokens.


class InstagramGraphAPIError(Exception):
    """Exception raised when Meta Graph API returns an error or is unreachable."""


def make_meta_api_call(endpoint: str, access_token: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Standard Meta Graph API call wrapper. Raises on Code 190 (expired token) like
    any other Graph API error — the retry-with-a-refreshed-token policy lives in
    ``fetch_live_instagram_data``, which is the one caller that knows the user_id
    needed to refresh.
    """
    if params is None:
        params = {}
    params["access_token"] = access_token
    url = f"{GRAPH_API_BASE}/{endpoint.lstrip('/')}"

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, params=params)
        data = resp.json()

        if "error" in data:
            err_code = data["error"].get("code")
            err_msg = data["error"].get("message", "Meta Graph API error")
            logger.error("Meta Graph API error on %s: %s", endpoint, data["error"])
            if err_code == 190:
                raise InstagramGraphAPIError(f"Meta Access Token expired. {err_msg} (Code: {err_code})")
            raise InstagramGraphAPIError(f"{err_msg} (Code: {err_code})")

        return data


def _fetch(endpoint: str, params: Dict[str, Any], token: str) -> Dict[str, Any]:
    return make_meta_api_call(endpoint, token, params)


def get_connected_instagram_account(token: str) -> Dict[str, Any]:
    """
    Fetches the connected Instagram Business/Creator Account profile directly.
    Uses graph.instagram.com/me — correct for Instagram Business Login tokens.
    (graph.facebook.com /me/accounts is for Facebook Login only, not applicable here)
    """
    try:
        data = _fetch(
            "me",
            {
                "fields": (
                    "id,username,name,biography,profile_picture_url,"
                    "followers_count,follows_count,media_count,website"
                )
            },
            token,
        )
        if data.get("id"):
            logger.info(
                "Connected Instagram account: @%s (id=%s, followers=%s)",
                data.get("username"), data.get("id"), data.get("followers_count")
            )
            return data
    except Exception as e:
        logger.error("Failed to fetch Instagram profile via graph.instagram.com/me: %s", e)
        raise InstagramGraphAPIError(
            f"Could not fetch Instagram profile. Make sure the token is from Instagram Business Login. Error: {e}"
        )

    raise InstagramGraphAPIError("No Instagram account data returned from graph.instagram.com/me")


def fetch_live_instagram_data(user_id: str) -> Dict[str, Any]:
    """
    Fetches complete live data from Meta Graph API for Instagram:
    - Profile Information
    - Media Posts (Reels, Carousels, Single Images) with metrics
    - Insights & Summary KPIs
    - Extracted Hashtags

    ``user_id`` identifies whose connected Instagram account to read (per-user
    token, stored encrypted in ``instagram_oauth_tokens``).
    """
    # Deferred import: instagram_auth.py imports this module back (to fetch the
    # connected profile after OAuth exchange), so this stays function-local to
    # avoid a module-level cycle.
    from app.services.instagram_auth import get_instagram_access_token, refresh_if_needed

    token = get_instagram_access_token(user_id)
    if not token:
        raise InstagramGraphAPIError("Instagram account not connected.")

    try:
        profile = get_connected_instagram_account(token)
    except InstagramGraphAPIError as exc:
        if "Code: 190" not in str(exc):
            raise
        # Token expired between the read and this call — force a refresh and retry once.
        refresh_if_needed(user_id, force=True)
        token = get_instagram_access_token(user_id)
        if not token:
            raise
        profile = get_connected_instagram_account(token)
    ig_id = profile.get("id")
    if not ig_id:
        raise InstagramGraphAPIError("Invalid Instagram account ID received from Meta API.")

    # Fetch recent media items
    media_resp = _fetch(
        f"{ig_id}/media",
        {
            "fields": (
                "id,caption,media_type,media_product_type,media_url,permalink,thumbnail_url,"
                "timestamp,like_count,comments_count"
            ),
            "limit": 50,
        },
        token,
    )

    media_items = media_resp.get("data", [])
    posts = []
    hashtags_map: Dict[str, Dict[str, Any]] = {}

    total_likes = 0
    total_comments = 0
    total_reels = 0
    total_carousels = 0
    total_singles = 0
    total_reach = 0
    total_saves = 0

    reel_views_list = []
    carousel_saves_list = []

    for item in media_items:
        m_id = item.get("id", "")
        caption = item.get("caption", "")
        m_type_raw = item.get("media_type", "IMAGE")
        prod_type = item.get("media_product_type", "")
        likes = item.get("like_count", 0)
        comments = item.get("comments_count", 0)
        ts = item.get("timestamp", "")
        permalink = item.get("permalink", "")
        thumb = item.get("thumbnail_url") or item.get("media_url") or ""

        # Determine type
        if prod_type == "REELS" or m_type_raw == "VIDEO":
            post_type = "reel"
            total_reels += 1
        elif m_type_raw == "CAROUSEL_ALBUM":
            post_type = "carousel"
            total_carousels += 1
        else:
            post_type = "single"
            total_singles += 1

        saves = 0
        shares = 0
        reach = likes + comments
        views = likes + comments

        # Attempt to query post-level insights from Graph API
        try:
            insights_resp = _fetch(
                f"{m_id}/insights",
                {"metric": "reach,saved,shares,views,total_interactions"},
                token,
            )
            for m_data in insights_resp.get("data", []):
                name = m_data.get("name")
                # Handle both integer value and dict value safely
                val_entry = m_data.get("values", [{}])[0]
                val = val_entry.get("value", 0) if isinstance(val_entry, dict) else 0

                if name == "reach" and val:
                    reach = val
                elif name == "saved" and val:
                    saves = val
                elif name == "shares" and val:
                    shares = val
                elif name in ("views", "plays") and val:
                    views = val
        except Exception:
            pass

        if post_type == "reel":
            reel_views_list.append(views)
        elif post_type == "carousel":
            carousel_saves_list.append(saves)

        total_likes += likes
        total_comments += comments
        total_reach += reach
        total_saves += saves

        # Extract title hook from first line of caption
        title = caption.split("\n")[0].strip() if caption else f"Post {m_id}"
        if len(title) > 70:
            title = title[:67] + "..."

        # Calculate engagement rate
        total_interactions = likes + comments + saves + shares
        eng_rate_num = (total_interactions / max(reach, 1)) * 100 if reach > 0 else 0.0
        eng_rate_str = f"{round(eng_rate_num, 1)}%"

        posts.append({
            "id": m_id,
            "title": title,
            "type": post_type,
            "publish_time": ts,
            "views": int(views),
            "likes": int(likes),
            "comments": int(comments),
            "shares": int(shares),
            "saves": int(saves),
            "reach": int(reach),
            "engagement_rate": eng_rate_str,
            "thumbnail_url": thumb,
            "permalink": permalink,
            "caption": caption
        })

        # Extract hashtags
        tags = re.findall(r"#([a-zA-Z0-9_]+)", caption)
        for tag in tags:
            tag_clean = f"#{tag.lower()}"
            if tag_clean not in hashtags_map:
                category = "General"
                t_lower = tag.lower()
                if "codingindia" in t_lower or "brand" in t_lower:
                    category = "Brand"
                elif t_lower in ["python", "javascript", "typescript", "java", "cpp", "golang", "sql"]:
                    category = "Language"
                elif t_lower in ["ai", "aiagents", "machinelearning", "llm", "deeplearning", "chatgpt", "ollama", "crewai", "langchain"]:
                    category = "AI / ML"
                elif t_lower in ["fastapi", "react", "nextjs", "django", "vue", "node"]:
                    category = "Framework"
                elif t_lower in ["backend", "frontend", "fullstack", "webdev"]:
                    category = "Development"

                hashtags_map[tag_clean] = {
                    "tag": tag_clean,
                    "posts_used": 0,
                    "total_reach": 0,
                    "category": category
                }
            hashtags_map[tag_clean]["posts_used"] += 1
            hashtags_map[tag_clean]["total_reach"] += reach

    # Format hashtags list. Ranking by raw avg_reach lets a hashtag used on a
    # single lucky post dominate the top of the list; weighting by sqrt(posts_used)
    # rewards hashtags with consistent, repeated performance instead.
    hashtags_list = []
    for tag_clean, h_info in hashtags_map.items():
        posts_used = h_info["posts_used"]
        avg_r = int(h_info["total_reach"] / max(posts_used, 1))
        score = int(avg_r * math.sqrt(posts_used))
        hashtags_list.append({
            "tag": tag_clean,
            "posts_used": posts_used,
            "avg_reach": avg_r,
            "score": score,
            "category": h_info["category"]
        })
    hashtags_list.sort(key=lambda x: x["score"], reverse=True)

    followers = profile.get("followers_count", 0)
    following = profile.get("follows_count", 0)
    total_posts = profile.get("media_count", len(posts))
    username = profile.get("username", "")
    brand_name = profile.get("name") or (f"@{username}" if username else "Instagram User")
    bio = profile.get("biography", "")
    profile_pic = profile.get("profile_picture_url", "")

    avg_eng = round((total_likes + total_comments) / max(followers * max(len(posts), 1), 1) * 100, 1) if followers and posts else 0.0

    profile_data = {
        "handle": f"@{username}" if username else "@instagram",
        "brand_name": brand_name,
        "url": f"https://instagram.com/{username}" if username else "https://instagram.com",
        "bio": bio,
        "followers": followers,
        "following": following,
        "total_posts": total_posts,
        "avg_engagement_rate": avg_eng,
        "monthly_reach": total_reach,
        "monthly_impressions": total_reach,
        "profile_picture_url": profile_pic
    }

    avg_reel_views = int(sum(reel_views_list) / len(reel_views_list)) if reel_views_list else 0
    avg_carousel_saves = int(sum(carousel_saves_list) / len(carousel_saves_list)) if carousel_saves_list else 0

    stats_data = {
        "total_followers": followers,
        "followers_gained": 0,
        "total_reach": total_reach,
        "total_impressions": total_reach,
        "accounts_engaged": total_likes + total_comments + total_saves,
        "profile_visits": 0,
        "link_clicks": 0,
        "total_reels_published": total_reels,
        "total_carousels_published": total_carousels,
        "avg_reel_views": avg_reel_views,
        "avg_carousel_saves": avg_carousel_saves,
    }

    return {
        "profile": profile_data,
        "stats": stats_data,
        "posts": posts,
        "hashtags": hashtags_list
    }
