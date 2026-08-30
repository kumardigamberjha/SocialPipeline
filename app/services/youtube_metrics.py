"""
Pure, dependency-free YouTube metric helpers shared by the owner-channel
analytics router (``app.routers.youtube_analytics``) and the prospect audit
service (``app.services.youtube_prospect_service``).

Nothing here performs I/O or touches the database, so both an async request
handler and a sync Celery task can call it freely. It lives in its own module
rather than in either caller so the two features cannot drift apart — the
length buckets in particular are quoted verbatim in outreach copy, so "30+ min"
must mean the same thing in the audit prompt and in the headline number.
"""

from __future__ import annotations

import collections
import re

# Ordered widest-to-narrowest for stable display; "unknown" always sorts last.
DURATION_BUCKETS: tuple[str, ...] = (
    "Shorts (<=1m)",
    "1-5 min",
    "5-15 min",
    "15-30 min",
    "30+ min",
    "unknown",
)

META_STOPWORDS = {
    "official", "video", "videos", "ep", "episode", "episodes", "part", "pt",
    "vol", "vlog", "vlogs", "clip", "clips", "highlight", "highlights", "stream",
    "live", "livestream", "shorts", "short", "teaser", "trailer", "preview",
    "ft", "feat", "featuring", "presents", "audio", "music", "podcast", "channel",
    "subscribe", "reupload", "watch", "status", "reel", "reels", "full", "hd",
    "4k", "2024", "2025", "2026", "2027", "assembly", "latest", "new", "best",
    "top", "day", "days", "week", "update", "updates",
}

STOPWORDS = set(
    "the a an and or of to for with your you how what why when who in on at is are be "
    "this that these those from into your my our it its as vs your best top new using use "
    "part full free real make made build built guide tutorial video || coding india".split()
) | META_STOPWORDS


def _get_channel_stopwords(channel_title: str = "", channel_handle: str = "") -> set[str]:
    """Extract individual tokens from a channel title and handle so creator names aren't treated as insights."""
    words = set()
    for text in (channel_title, channel_handle):
        if not text:
            continue
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        for token in cleaned.split():
            if len(token) >= 2:
                words.add(token)
                if token.endswith("yt") and len(token) > 4:
                    words.add(token[:-2])
                if token.endswith("channel") and len(token) > 9:
                    words.add(token[:-7])
    return words


def duration_bucket(seconds) -> str:
    """Bucket a video length. ``0``/``None`` means *unknown*, never "a short".

    The RSS fallback path in ``app.services.youtube_channel_lookup`` returns
    ``duration_seconds == 0`` for every video because the feed simply does not
    carry duration. Mapping that to "Shorts" would silently invent a claim, so
    it maps to "unknown" and callers drop the bucket.
    """
    s = seconds or 0
    if s <= 0:
        return "unknown"
    if s <= 60:
        return "Shorts (<=1m)"
    if s <= 300:
        return "1-5 min"
    if s <= 900:
        return "5-15 min"
    if s <= 1800:
        return "15-30 min"
    return "30+ min"


def extract_keywords(
    titles, n: int = 6, channel_title: str = "", channel_handle: str = ""
) -> list[str]:
    """Most frequent meaningful words across video titles (for niche/search)."""
    channel_words = _get_channel_stopwords(channel_title, channel_handle)
    all_stop = STOPWORDS | channel_words
    counter: collections.Counter = collections.Counter()
    for t in titles:
        for w in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.]{2,}", (t or "").lower()):
            if w in all_stop or len(w) < 3:
                continue
            counter[w] += 1
    return [w for w, _ in counter.most_common(n)]


def analyze_channel_keywords(
    videos: list[dict],
    channel_baseline_views: float,
    channel_title: str = "",
    channel_handle: str = "",
) -> dict:
    """Analyze keywords and topic clusters across public channel uploads."""
    if not videos or channel_baseline_views <= 0:
        return {"top_keywords": [], "underperforming_keywords": []}

    channel_words = _get_channel_stopwords(channel_title, channel_handle)
    all_stop = STOPWORDS | channel_words
    phrase_videos = collections.defaultdict(list)

    for v in videos:
        title = (v.get("title") or "").strip()
        words = [
            w
            for w in re.findall(r"[a-zA-Z0-9+#.]+", title.lower())
            if len(w) >= 2 and w not in all_stop
        ]
        seen_in_title = set()

        # 1-grams
        for w in words:
            if len(w) >= 3 and w not in seen_in_title:
                seen_in_title.add(w)
                phrase_videos[w.title()].append(v)

        # 2-grams
        for i in range(len(words) - 1):
            p = f"{words[i]} {words[i+1]}".title()
            if p not in seen_in_title:
                seen_in_title.add(p)
                phrase_videos[p].append(v)

        # 3-grams
        for i in range(len(words) - 2):
            p = f"{words[i]} {words[i+1]} {words[i+2]}".title()
            if p not in seen_in_title:
                seen_in_title.add(p)
                phrase_videos[p].append(v)

    raw_results = []
    for phrase, v_list in phrase_videos.items():
        if len(v_list) < 2:
            continue
        v_ids = set(x.get("video_id") or x.get("title") for x in v_list)
        t_views = sum(int(x.get("views") or 0) for x in v_list)
        avg = int(t_views / len(v_list))
        mult = round(avg / max(1.0, float(channel_baseline_views)), 1)
        top_vid = max(v_list, key=lambda x: int(x.get("views") or 0))

        raw_results.append({
            "keyword": phrase,
            "video_count": len(v_list),
            "avg_views": avg,
            "total_views": t_views,
            "multiplier": mult,
            "v_ids": v_ids,
            "top_video_title": top_vid.get("title", ""),
        })

    raw_results.sort(key=lambda x: (len(x["keyword"].split()), x["multiplier"]), reverse=True)
    deduped = []

    for item in raw_results:
        is_sub = False
        for ex in deduped:
            if item["keyword"].lower() in ex["keyword"].lower() and item["v_ids"] == ex["v_ids"]:
                is_sub = True
                break
        if not is_sub:
            deduped.append(item)

    for item in deduped:
        item.pop("v_ids", None)
        item["status"] = (
            "high_demand"
            if item["multiplier"] >= 1.3
            else ("underperforming" if item["multiplier"] <= 0.75 else "steady")
        )

    deduped.sort(key=lambda x: (x["multiplier"], x["video_count"]), reverse=True)
    top_kw = [r for r in deduped if r["multiplier"] >= 1.1][:6]
    under_kw = [r for r in reversed(deduped) if r["multiplier"] <= 0.85][:4]

    return {"top_keywords": top_kw, "underperforming_keywords": under_kw}


# ── Breakout Title Keyword Patterns & Clusters ────────────────────────────────

GRAMMAR_STOPWORDS = set(
    "the a an and or of to for with your you how what why when who in on at is are be "
    "this that these those from into my our it its as vs by about than then over after before "
    "out up down all just so not can will do did does have has had get got i me we us he him "
    "she her they them but if also & part video videos".split()
) | META_STOPWORDS

KNOWN_CASINGS = {
    "ai": "AI",
    "llm": "LLM",
    "llms": "LLMs",
    "gpt": "GPT",
    "chatgpt": "ChatGPT",
    "openai": "OpenAI",
    "api": "API",
    "apis": "APIs",
    "fastapi": "FastAPI",
    "ui": "UI",
    "ux": "UX",
    "css": "CSS",
    "sql": "SQL",
    "crm": "CRM",
    "seo": "SEO",
    "saas": "SaaS",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "react": "React",
    "reactjs": "React.js",
    "python": "Python",
    "docker": "Docker",
    "gemini": "Gemini",
    "deepseek": "DeepSeek",
    "claude": "Claude",
    "no-code": "No-Code",
    "low-code": "Low-Code",
    "nocode": "No-Code",
    "lowcode": "Low-Code",
    "full-stack": "Full-Stack",
    "fullstack": "Full-Stack",
    "open-source": "Open-Source",
    "opensource": "Open-Source",
    "step-by-step": "Step-by-Step",
    "zero-to-hero": "Zero to Hero",
    "free": "Free",
}


def _format_kw_join(keywords: list[str]) -> str:
    """Format a list of keywords with quotes and Oxford comma (e.g. 'AI', 'Free', and 'No-Code')."""
    if not keywords:
        return ""
    quoted = [f"'{k}'" for k in keywords]
    if len(quoted) == 1:
        return quoted[0]
    if len(quoted) == 2:
        return f"{quoted[0]} and {quoted[1]}"
    return f"{', '.join(quoted[:-1])}, and {quoted[-1]}"


def _normalize_title_tokens(
    title: str, channel_stopwords: set[str] | None = None
) -> list[str]:
    """Extract and normalize individual tokens and phrases from a video title."""
    if not title:
        return []
    
    # Pre-process compound phrases
    normalized_raw = title
    normalized_raw = re.sub(r"(?i)\bno[- ]code\b", "No-Code", normalized_raw)
    normalized_raw = re.sub(r"(?i)\blow[- ]code\b", "Low-Code", normalized_raw)
    normalized_raw = re.sub(r"(?i)\bfull[- ]stack\b", "Full-Stack", normalized_raw)
    normalized_raw = re.sub(r"(?i)\bopen[- ]source\b", "Open-Source", normalized_raw)
    normalized_raw = re.sub(r"(?i)\bstep[- ]by[- ]step\b", "Step-by-Step", normalized_raw)
    normalized_raw = re.sub(r"(?i)\bzero[- ]to[- ]hero\b", "Zero to Hero", normalized_raw)

    all_stop = GRAMMAR_STOPWORDS | (channel_stopwords or set())

    # Extract words preserving hyphens and dots (e.g. No-Code, Next.js, C++)
    raw_tokens = re.findall(r"[a-zA-Z0-9+#.-]+", normalized_raw)
    cleaned_tokens = []
    
    for t in raw_tokens:
        clean = t.strip(".-+:|()[]{}#_")
        if not clean or clean.lower() in all_stop or len(clean) < 2:
            continue
        
        # Check known casings
        lower_clean = clean.lower()
        if lower_clean in KNOWN_CASINGS:
            cleaned_tokens.append(KNOWN_CASINGS[lower_clean])
        elif clean.isupper() and len(clean) <= 5:
            cleaned_tokens.append(clean)
        else:
            cleaned_tokens.append(clean.capitalize())
            
    return cleaned_tokens


def analyze_breakout_keyword_patterns(
    breakout_videos: list[dict],
    top_videos: list[dict] | None = None,
    channel_baseline_views: float = 0,
    channel_title: str = "",
    channel_handle: str = "",
    all_videos: list[dict] | None = None,
) -> dict:
    """Extract recurring keyword clusters & title patterns from breakout & top videos,
    strictly validating against catalog-wide base-rate frequency.

    Only fires when top-N frequency meaningfully exceeds full catalog-wide frequency:
    - Must appear in >= 40% of top/breakout videos (min 2 videos)
    - Prevalence gap: p_top - p_catalog >= 0.25 (at least 25% higher prevalence in top videos)
    - Relative ratio: p_top / max(p_catalog, 0.01) >= 2.0 (at least 2x higher than catalog base rate)
    - Filters out creator name/handle tokens and channel branding
    - Uses catalog median views for realistic lift calculation, avoiding inflated spurious multipliers.
    """
    empty_result = {
        "has_pattern": False,
        "breakout_video_count": 0,
        "common_keywords": [],
        "cluster_title": "",
        "pattern_summary": "",
        "insight": "",
        "hook_text": "",
        "clusters": [],
    }

    channel_stopwords = _get_channel_stopwords(channel_title, channel_handle)
    candidates = []
    if breakout_videos and len(breakout_videos) >= 2:
        candidates = breakout_videos[:5]
    elif top_videos and len(top_videos) >= 2:
        candidates = top_videos[:5]

    if not candidates or len(candidates) < 2:
        return empty_result

    sample_size = len(candidates)
    base_avg = float(channel_baseline_views) if channel_baseline_views > 0 else 1.0

    # Catalog-wide base rate tracking
    catalog = all_videos or []
    catalog_size = len(catalog)
    catalog_phrase_counts: dict[str, int] = collections.defaultdict(int)

    if catalog_size >= 5:
        for v in catalog:
            t = v.get("title") or ""
            toks = _normalize_title_tokens(t, channel_stopwords)
            seen_phrases = set(toks)
            for i in range(len(toks) - 1):
                seen_phrases.add(f"{toks[i]} {toks[i+1]}")
            for p in seen_phrases:
                catalog_phrase_counts[p] += 1

    # Extract tokens for candidate top videos
    video_token_map = []
    for v in candidates:
        title = v.get("title") or ""
        tokens = _normalize_title_tokens(title, channel_stopwords)
        
        phrases = list(tokens)
        for i in range(len(tokens) - 1):
            two_gram = f"{tokens[i]} {tokens[i+1]}"
            phrases.append(two_gram)
            
        video_token_map.append({
            "video": v,
            "tokens": set(tokens),
            "phrases": set(phrases),
            "views": int(v.get("views") or 0),
        })

    phrase_counter = collections.defaultdict(list)
    for vdata in video_token_map:
        for phrase in vdata["phrases"]:
            # Exclude phrases containing any channel stopword or grammar stopword
            words_in_p = [w.lower() for w in phrase.split()]
            if any(w in channel_stopwords or w in GRAMMAR_STOPWORDS for w in words_in_p):
                continue
            phrase_counter[phrase].append(vdata)

    qualifying = []

    for phrase, v_list in phrase_counter.items():
        count = len(v_list)
        if count < 2:
            continue
        
        p_top = count / sample_size
        if p_top < 0.40:
            continue

        p_catalog = (catalog_phrase_counts.get(phrase, 0) / catalog_size) if catalog_size >= 5 else 0.0
        
        # Base-rate gap check: must exceed catalog prevalence by >= 25% and be >= 2.0x ratio
        if catalog_size >= 5:
            if (p_top - p_catalog) < 0.25:
                continue
            if p_catalog > 0 and (p_top / p_catalog) < 2.0:
                continue

        # Calculate realistic median views across catalog matching videos
        phrase_re = re.compile(rf"\b{re.escape(phrase)}\b", re.I)
        matching_vids = [
            v for v in (catalog if catalog else [item["video"] for item in v_list])
            if phrase_re.search(v.get("title") or "")
        ]
        if not matching_vids:
            continue

        views_list = sorted(int(v.get("views") or 0) for v in matching_vids)
        kw_median = views_list[len(views_list) // 2]
        kw_lift = round(kw_median / base_avg, 1)

        if kw_lift < 1.25:
            continue

        v_ids = [item["video"].get("video_id") or item["video"].get("title") for item in v_list]
        
        qualifying.append({
            "keyword": phrase,
            "count": count,
            "total_breakouts": sample_size,
            "percentage": round(p_top * 100),
            "catalog_percentage": round(p_catalog * 100),
            "avg_views": int(sum(views_list) / len(views_list)),
            "median_views": kw_median,
            "avg_multiplier": kw_lift,
            "matching_video_ids": v_ids,
        })

    # If no keywords clear the strict catalog base-rate filter, return empty pattern
    if not qualifying:
        return empty_result

    # Sort qualifying keywords by count (desc), then lift (desc)
    qualifying.sort(key=lambda x: (x["count"], x["avg_multiplier"], -len(x["keyword"].split())), reverse=True)

    # Deduplicate overlapping sub-keywords with identical video matches
    deduped_clusters = []
    for item in qualifying:
        is_redundant = False
        for existing in deduped_clusters:
            # Redundant if another cluster already covers identical videos with a more specific phrase
            if item["matching_video_ids"] == existing["matching_video_ids"] and (
                item["keyword"].lower() in existing["keyword"].lower()
                or existing["keyword"].lower() in item["keyword"].lower()
            ):
                is_redundant = True
                break
        if not is_redundant:
            deduped_clusters.append(item)

    top_clusters = deduped_clusters[:4]
    common_keywords = [c["keyword"] for c in top_clusters]

    if not common_keywords:
        return empty_result

    cluster_title = " + ".join(common_keywords[:3])
    formatted_kw = _format_kw_join(common_keywords[:3])
    avg_lift = round(sum(c["avg_multiplier"] for c in top_clusters) / len(top_clusters), 1)

    if len(common_keywords) >= 2:
        pattern_summary = f"In your top {sample_size} videos, {formatted_kw} are common"
        insight = (
            f"Your top {sample_size} breakout videos consistently feature {formatted_kw}, "
            f"delivering an average {avg_lift}× view lift over channel baseline."
        )
    else:
        pattern_summary = f"In your top {sample_size} videos, '{common_keywords[0]}' is the dominant breakout keyword"
        insight = (
            f"Your top videos center on '{common_keywords[0]}', pulling an average "
            f"{top_clusters[0]['avg_views']:,} views ({top_clusters[0]['avg_multiplier']}× channel average)."
        )

    hook_text = (
        f"Ran your channel through something I built. In your top {sample_size} videos, "
        f"{formatted_kw} are common — pulling {avg_lift}× your channel average. Full 4-week plan attached if useful."
    )

    return {
        "has_pattern": True,
        "breakout_video_count": sample_size,
        "common_keywords": common_keywords,
        "cluster_title": cluster_title,
        "pattern_summary": pattern_summary,
        "insight": insight,
        "hook_text": hook_text,
        "clusters": top_clusters,
    }




# ── Upload Timing & Best Publishing Schedule ──────────────────────────────────

DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DAY_SHORTS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Sample floors, the "top N" of every "X of top N", and every other tunable now
# live on ``ReportRules`` in ``app.services.youtube_report_rules`` so the metric
# layer, the prompt layer, the validator and the dashboard cannot each carry
# their own copy and drift apart.

TIME_SLOT_RANGES = (
    ("00:00-03:00", "00:00 – 03:00 UTC", "Late Night", 0, 3),
    ("03:00-06:00", "03:00 – 06:00 UTC", "Early Morning", 3, 6),
    ("06:00-09:00", "06:00 – 09:00 UTC", "Morning", 6, 9),
    ("09:00-12:00", "09:00 – 12:00 UTC", "Late Morning", 9, 12),
    ("12:00-15:00", "12:00 – 15:00 UTC", "Afternoon", 12, 15),
    ("15:00-18:00", "15:00 – 18:00 UTC", "Peak Afternoon", 15, 18),
    ("18:00-21:00", "18:00 – 21:00 UTC", "Prime Evening", 18, 21),
    ("21:00-24:00", "21:00 – 24:00 UTC", "Late Evening", 21, 24),
)

SLOT_BOUNDS = {key: (start, end) for key, _label, _period, start, end in TIME_SLOT_RANGES}


def _parse_iso_datetime(val):
    """Parse ISO timestamp or datetime object safely."""
    from datetime import datetime, timezone

    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    s = str(val).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if "T" in s:
            return datetime.fromisoformat(s)
        # Date only: YYYY-MM-DD
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return datetime.fromisoformat(s[:10] + "T00:00:00+00:00")
    except (ValueError, TypeError):
        pass
    return None


def _has_clock_time(val) -> bool:
    """True when the source timestamp actually carried a time of day.

    ``_parse_iso_datetime`` normalises a bare ``YYYY-MM-DD`` to midnight UTC, so
    once parsed a date-only record is indistinguishable from a real 00:00
    upload. Counting those as "published 00:00–03:00" manufactures a publishing
    window out of missing data, so the time-of-day analysis skips them. The cost
    is that a genuine midnight upload stored date-only is left out of the hour
    breakdown — that errs toward saying less, which is the right direction for
    a number quoted to a stranger.
    """
    from datetime import datetime

    if isinstance(val, datetime):
        return True
    return "T" in str(val or "")


def _clocked_slot_counts(videos: list[dict]) -> tuple[int, dict[str, int]]:
    """How many uploads carry a real publish time, and how they fall into slots.

    Counts from the raw video dicts rather than the scored rows so the gate can
    be asked about a catalogue before ``analyze_upload_timing`` has run — the
    prompt layer and the validator both need the answer, and neither should have
    to reproduce the bucketing to get it.
    """
    counts = {key: 0 for key, _label, _period, _s, _e in TIME_SLOT_RANGES}
    clocked = 0
    for v in videos or []:
        raw = v.get("published_at") if isinstance(v, dict) else None
        if not _has_clock_time(raw):
            continue
        dt = _parse_iso_datetime(raw)
        if dt is None:
            continue
        clocked += 1
        for key, _label, _period, h_start, h_end in TIME_SLOT_RANGES:
            if h_start <= dt.hour < h_end:
                counts[key] += 1
                break
    return clocked, counts


def time_of_day_recommendation_allowed(videos: list[dict], rules=None) -> bool:
    """Whether this catalogue may be given an hour-level publishing window.

    THE gate. Page 2's timing widget, the audit narrative, the strategic
    priorities and the roadmap all ask this one function, because they used to
    decide separately: the widget printed "not enough uploads carry a publish
    time" while the narrative on the page before recommended "Saturday & Sunday
    between 09:00-12:00 UTC". Both were rendered from the same data, in the same
    document, for the same reader.

    Two floors, both required:

    * ``rules.min_clock_sample`` uploads in the catalogue carry a usable publish
      timestamp at all. A date-only feed normalises to midnight, so without this
      floor a handful of records manufactures a "late night" window out of
      missing data.
    * ``rules.min_slot_sample`` uploads sit in the strongest single slot. A
      window is a claim about one three-hour band; eight timestamps spread
      across eight bands support none of them.

    Day-of-week recommendations are a separate, less strict question
    (``rules.min_day_sample``) and are unaffected by this returning ``False``.
    """
    if rules is None:  # imported lazily: the rules module imports from this one
        from app.services.youtube_report_rules import DEFAULT_RULES

        rules = DEFAULT_RULES

    clocked, counts = _clocked_slot_counts(videos)
    if clocked < rules.min_clock_sample:
        return False
    return max(counts.values(), default=0) >= rules.min_slot_sample


def timing_allows_time_of_day(timing: dict | None) -> bool:
    """The gate's verdict for an already-computed ``analyze_upload_timing`` block.

    Reads the flag recorded at computation time, narrowed by anything the
    validator dropped afterwards (a window that was not the highest-average
    bucket, or one its own cited evidence contradicted). Surfaces holding the
    timing dict rather than the raw videos consume this; it is the same rule
    reported back, not a second one.
    """
    if not timing:
        return False
    win = timing.get("best_window") or {}
    return bool(timing.get("time_of_day_allowed")) and bool(win.get("slot_confident"))


def compose_window_copy(
    best_days: list[str],
    slot_label: str | None,
    day_multiplier: float,
    slot_multiplier: float | None,
    proof_count: int,
    top_tier_count: int,
    window_proof_count: int = 0,
) -> dict:
    """The three strings the report prints for a publishing window.

    Shared with ``app.services.youtube_report_rules`` so that when the validator
    drops a time-of-day claim it can rebuild the day-only copy with exactly the
    same phrasing the metric layer would have produced. Two functions writing
    this text independently is how "publish 12:00-15:00" ended up above a table
    that named a different window.
    """
    days_str = " & ".join(best_days)
    slot_str = slot_label.split(" (")[0] if slot_label else ""
    combined_label = " • ".join(p for p in (days_str, slot_str) if p) or "Not enough timing data"

    if proof_count > 0 and days_str:
        # The headline count is the day claim. The window is a narrower claim
        # about a subset, so it gets its own number rather than inheriting this
        # one — "9 of top 10 went out on Sat & Tue, 09:00-12:00" would assert
        # that all nine were in the window when only seven were.
        proof = f"{proof_count} of top {top_tier_count} videos by views went out on {days_str}"
        if slot_str:
            proof += f" — {window_proof_count} of those in {slot_str}"
    elif days_str:
        proof = (
            f"{days_str} uploads average {day_multiplier}× the channel median, "
            f"though none of the top {top_tier_count} videos landed there"
        )
    else:
        proof = ""

    if not days_str:
        recommendation = "Not enough dated uploads to recommend a publishing slot."
    elif slot_str:
        lift = int(round(((slot_multiplier or 1.0) - 1.0) * 100))
        note = f" ({slot_multiplier}× the channel median in that window)" if slot_multiplier else ""
        recommendation = f"Publish on {days_str} between {slot_str}{note}."
        if lift <= 0:
            recommendation = f"Publish on {days_str} between {slot_str}."
    else:
        lift = int(round((day_multiplier - 1.0) * 100))
        lift_note = f" (+{lift}% vs the channel median)" if lift > 0 else ""
        recommendation = (
            f"Publish on {days_str}{lift_note}. Not enough uploads carry a publish time "
            f"to recommend a time of day."
        )

    return {
        "combined_label": combined_label,
        "recommendation": recommendation,
        "top_video_proof": proof,
    }


def analyze_upload_timing(
    videos: list[dict], channel_baseline_views: float, rules=None
) -> dict:
    """The creator's best day and time window to publish, plus the proof for it.

    The day, the window and the "evidence" videos all print on one page, so four
    rules keep them from contradicting each other:

    1. **One list, both numbers.** The proof numerator and denominator are both
       drawn from ``top_tier`` — the top ``rules.top_breakout_n`` videos by views.
       They were previously computed from different collections, which is how
       "13 of top 10 breakout videos" became printable.
    2. **Separate statistics.** Day-of-week and time-of-day are independent
       computations with independent sample floors, and ``day_multiplier`` and
       ``slot_multiplier`` are never merged. A time claim can never be backed by
       a day number.
    3. **Sample floors.** Time-of-day is gated by
       ``time_of_day_recommendation_allowed`` — the single function every other
       surface asks — and a day needs ``rules.min_day_sample``. If the gate is
       closed, ``best_time_slot`` is ``None`` and the recommendation carries the
       day finding alone: it never falls back to a hardcoded window presented as
       this channel's measured peak, and no other section may name one either.
    4. **The winner is the winner.** The recommended window is the qualifying
       slot with the highest average views, not the one that scores best on a
       blend of lift and upload volume.
    """
    if rules is None:  # imported lazily: the rules module imports from this one
        from app.services.youtube_report_rules import DEFAULT_RULES

        rules = DEFAULT_RULES

    empty = {
        "has_timing_data": False,
        "has_hour_data": False,
        "time_of_day_allowed": False,
        "days": [],
        "time_slots": [],
        "best_window": None,
        "top_timing_videos": [],
        "evidence_videos": [],
    }
    if not videos:
        return empty

    scored = []
    for v in videos:
        raw = v.get("published_at")
        dt = _parse_iso_datetime(raw)
        if dt is None:
            continue
        scored.append({
            "video_id": v.get("video_id") or "",
            "title": v.get("title") or "",
            "views": int(v.get("views") or 0),
            "likes": int(v.get("likes") or 0),
            "published_at": raw,
            "dt": dt,
            "day_idx": dt.weekday(),
            "hour": dt.hour,
            "has_clock": _has_clock_time(raw),
            "duration_seconds": int(v.get("duration_seconds") or 0),
        })

    if not scored:
        return empty

    total_analyzed = len(scored)
    baseline_views = float(channel_baseline_views) if channel_baseline_views > 0 else (
        sorted(v["views"] for v in scored)[total_analyzed // 2]
    )
    safe_baseline = max(1.0, baseline_views)

    # THE list. Every "X of top N" in the report counts out of exactly this, and
    # membership is by object identity rather than video_id — an id can be blank,
    # and two blanks must not collapse into one another.
    sorted_by_views = sorted(scored, key=lambda x: x["views"], reverse=True)
    top_tier_videos = sorted_by_views[: min(rules.top_breakout_n, total_analyzed)]
    top_tier_count = len(top_tier_videos)
    top_tier_marker = {id(v) for v in top_tier_videos}

    def _summarise(vids: list[dict], base: dict) -> dict:
        v_count = len(vids)
        t_views = sum(v["views"] for v in vids)
        a_views = int(t_views / v_count) if v_count else 0
        return {
            **base,
            "video_count": v_count,
            "total_views": t_views,
            "avg_views": a_views,
            "multiplier": round(a_views / safe_baseline, 2) if v_count else 0.0,
            "top_video_count": sum(1 for v in vids if id(v) in top_tier_marker),
        }

    # ── 1. Day of Week ─────────────────────────────────────────────────────────
    # Days rank on a composite of lift and how much of the top tier landed there,
    # because a day carries both signals. This is deliberately NOT the rule used
    # for time slots below.
    days_data = [
        _summarise(
            [v for v in scored if v["day_idx"] == idx],
            {
                "day": DAY_NAMES[idx],
                "day_short": DAY_SHORTS[idx],
                "day_index": idx,
                "is_best": False,
            },
        )
        for idx in range(7)
    ]

    def _day_score(row: dict) -> float:
        return row["multiplier"] * 1.5 + (row["top_video_count"] / max(1, top_tier_count)) * 2.0

    eligible_days = [d for d in days_data if d["video_count"] >= rules.min_day_sample]
    day_confident = bool(eligible_days)
    ranked_days = sorted(
        eligible_days or [d for d in days_data if d["video_count"] > 0],
        key=lambda d: (_day_score(d), d["video_count"]),
        reverse=True,
    )

    best_days_list: list[str] = []
    if ranked_days:
        ranked_days[0]["is_best"] = True  # same dict object as in days_data
        best_days_list.append(ranked_days[0]["day"])
        if len(ranked_days) > 1 and ranked_days[1]["multiplier"] >= 1.05:
            best_days_list.append(ranked_days[1]["day"])

    primary_best_day = ranked_days[0] if ranked_days else None
    day_multiplier = primary_best_day["multiplier"] if primary_best_day else 0.0

    # ── 2. Time Slot Windows (UTC) ─────────────────────────────────────────────
    # A window is recommended on one criterion only: it is the qualifying slot
    # with the highest average views. No blending with day statistics, and no
    # borrowing the day's multiplier when the slot has none.
    clock_videos = [v for v in scored if v["has_clock"]]
    # One gate, asked once. Everything downstream — this table, the narrative,
    # the priorities, the roadmap — reads the answer rather than re-deriving it.
    tod_allowed = time_of_day_recommendation_allowed(videos, rules)
    has_hour_data = tod_allowed

    time_slots_data = [
        _summarise(
            [v for v in clock_videos if h_start <= v["hour"] < h_end] if has_hour_data else [],
            {"slot": slot_key, "label": slot_label, "period": period_name},
        )
        for slot_key, slot_label, period_name, h_start, h_end in TIME_SLOT_RANGES
    ]

    qualifying_slots = [s for s in time_slots_data if s["video_count"] >= rules.min_slot_sample]
    best_slot = max(qualifying_slots, key=lambda s: s["avg_views"]) if qualifying_slots else None
    slot_confident = best_slot is not None
    best_slot_label = best_slot["label"] if best_slot else None
    best_slot_multiplier = best_slot["multiplier"] if best_slot else None
    best_slot_range = SLOT_BOUNDS[best_slot["slot"]] if best_slot else None

    # ── 3. Proof, counted out of the one list ─────────────────────────────────
    day_hits = [v for v in top_tier_videos if DAY_NAMES[v["day_idx"]] in best_days_list]
    window_hits = [
        v
        for v in day_hits
        if best_slot_range is None
        or (v["has_clock"] and best_slot_range[0] <= v["hour"] < best_slot_range[1])
    ]
    window_marker = {id(v) for v in window_hits}

    copy = compose_window_copy(
        best_days_list, best_slot_label, day_multiplier, best_slot_multiplier,
        len(day_hits), top_tier_count, len(window_hits),
    )

    # Evidence leads with the videos that back the recommendation; the rest
    # follow, flagged, so the reader can see what falls outside the window.
    ordered_proof = sorted(top_tier_videos, key=lambda v: (id(v) not in window_marker, -v["views"]))

    def _as_evidence(v: dict) -> dict:
        pub_iso = v.get("published_at")
        pub_str = pub_iso[:10] if isinstance(pub_iso, str) else (pub_iso.isoformat()[:10] if pub_iso else "")
        return {
            "video_id": v["video_id"],
            "title": v["title"],
            "views": v["views"],
            "likes": v["likes"],
            "published_at": pub_str,
            "day_name": DAY_NAMES[v["day_idx"]],
            "day_short": DAY_SHORTS[v["day_idx"]],
            "hour": v["hour"] if v["has_clock"] else None,
            "time_utc": f"{v['dt'].strftime('%H:%M')} UTC" if v["has_clock"] else "—",
            "multiplier": round(v["views"] / safe_baseline, 1),
            "in_best_window": id(v) in window_marker,
        }

    top_timing_videos = [_as_evidence(v) for v in ordered_proof[:6]]

    return {
        "has_timing_data": True,
        "has_hour_data": has_hour_data,
        # The gate's verdict, recorded so no surface has to recompute it and
        # none can reach a different answer.
        "time_of_day_allowed": tod_allowed,
        "days": days_data,
        "time_slots": time_slots_data,
        "best_window": {
            "best_days": best_days_list,
            "best_day_name": primary_best_day["day"] if primary_best_day else "",
            "best_time_slot": best_slot_label,
            "best_slot_key": best_slot["slot"] if best_slot else None,
            "combined_label": copy["combined_label"],
            # Deliberately separate. Nothing may substitute one for the other.
            "day_multiplier": day_multiplier,
            "slot_multiplier": best_slot_multiplier,
            "day_sample": primary_best_day["video_count"] if primary_best_day else 0,
            "slot_sample": best_slot["video_count"] if best_slot else 0,
            "day_lift_pct": int(round((day_multiplier - 1.0) * 100)) if day_multiplier > 1.0 else 0,
            "slot_lift_pct": (
                int(round((best_slot_multiplier - 1.0) * 100))
                if best_slot_multiplier and best_slot_multiplier > 1.0
                else 0
            ),
            "day_confident": day_confident,
            "slot_confident": slot_confident,
            "top_video_proof": copy["top_video_proof"],
            "proof_count": len(day_hits),
            "window_proof_count": len(window_hits),
            "top_tier_count": top_tier_count,
            "recommendation": copy["recommendation"],
        },
        "top_timing_videos": top_timing_videos,
        # The exact list the UI cites, so the renderer and the validator can
        # never disagree about which videos were held up as evidence.
        "evidence_videos": top_timing_videos[: rules.evidence_cited],
    }
