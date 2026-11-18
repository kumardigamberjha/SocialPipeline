"""Thresholds, cadence, underperformance and contradiction checks for the audit.

Every figure in a prospect report is quoted to a stranger who owns the channel and
can check it. The failures this module exists to prevent were all of one shape:
**two parts of the document deriving the same fact independently and disagreeing.**

    "13 of top 10 breakout videos"      numerator and denominator, different sets
    "publish 12:00-15:00 UTC"           above a table whose winner was 09:00-12:00
    "8-10 day loop" / "3-4 per month"   / "1 per week" / 8 items over 4 weeks
    "published Saturdays"               above four Tuesday dates
    a roadmap citing, as a proven pillar, the video the audit called failing

So the tunables, the cadence, the flagged-video list and the final consistency
sweep live here, and every caller reads them from here rather than deriving its
own copy.

Three things this module deliberately does NOT do:

* It does not compute metrics. ``app.services.youtube_metrics`` owns that; this
  module only checks the result and, where a claim cannot be supported, removes it.
* It does not trust LLM prose for any number. The audit and roadmap models are
  told the cadence; whatever they write is reconciled against the computed value.
* It does not repair an arithmetic impossibility. A subset larger than its
  superset means the counting code broke, so that raises rather than degrading —
  see ``ReportIntegrityError``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


# ── Tunables ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReportRules:
    """Every sample floor and threshold the report obeys, in one place.

    Callers take ``rules: ReportRules = DEFAULT_RULES``; tests construct variants
    rather than monkey-patching module constants.
    """

    # The N in every "X of top N". Both sides of that fraction are counted out of
    # this many videos, from one list.
    top_breakout_n: int = 10

    # A time-of-day window needs this many uploads *in the winning slot* before
    # it may be recommended, and the catalogue needs ``min_clock_sample`` uploads
    # carrying a publish time at all. Both floors are deliberately higher than
    # the day floor: there are 8 windows and 7 days, but a window claim is far
    # more specific and far easier to disprove. See
    # ``youtube_metrics.time_of_day_recommendation_allowed`` — the one gate.
    min_clock_sample: int = 8
    min_slot_sample: int = 5
    min_day_sample: int = 3

    # How many evidence videos the report cites, and how much of that evidence
    # must actually sit inside the recommended window for the claim to survive.
    evidence_cited: int = 3
    min_evidence_agreement: float = 0.5

    # A video younger than this is still accumulating views and cannot be judged
    # against a lifetime baseline.
    fresh_upload_days: int = 21

    # A length bucket below this many videos is noise and may not drive a claim.
    min_bucket_sample: int = 3

    # A video at or below this share of the channel baseline is flagged.
    underperform_ratio: float = 0.75

    # How many times a roadmap item that cites a flagged video may be regenerated
    # before its justification is stripped instead.
    max_item_regens: int = 2

    def as_payload(self) -> dict:
        """The subset the dashboard needs, so the UI stops hardcoding its own."""
        return {
            "top_breakout_n": self.top_breakout_n,
            "min_clock_sample": self.min_clock_sample,
            "min_slot_sample": self.min_slot_sample,
            "min_day_sample": self.min_day_sample,
            "evidence_cited": self.evidence_cited,
            "fresh_upload_days": self.fresh_upload_days,
            "min_bucket_sample": self.min_bucket_sample,
        }


DEFAULT_RULES = ReportRules()


class ReportIntegrityError(RuntimeError):
    """An arithmetic invariant was violated.

    Raised only for conditions that cannot arise from unusual data — a count
    exceeding the list it was counted from, for instance. Those mean the
    generator is broken, and rendering the result would publish the proof of it.
    Everything else degrades: the claim is dropped and a ``Conflict`` is logged.
    """


@dataclass
class Conflict:
    """One internal contradiction, and what was done about it."""

    check: str
    section: str
    detail: str
    action_taken: str

    def as_dict(self) -> dict:
        return {
            "check": self.check,
            "section": self.section,
            "detail": self.detail,
            "action_taken": self.action_taken,
        }


def _log(conflicts: list[Conflict], check: str, section: str, detail: str, action: str) -> None:
    logger.warning("report integrity [%s/%s]: %s -> %s", section, check, detail, action)
    conflicts.append(Conflict(check=check, section=section, detail=detail, action_taken=action))


# ── Cadence: computed once, read everywhere ───────────────────────────────────

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True)
class Cadence:
    """The single authority on how often this channel should publish, and when.

    Previously four independent authors: the audit model's ``format_insights``,
    its ``priorities``, a block of literals inside ``generate_roadmap``, and the
    number of items the model happened to emit. They contradicted each other in
    the same document. Now they all read this.
    """

    items_per_week: int
    uploads_per_week: float
    label: str
    publish_days: tuple[str, ...] = ()

    def total_items(self, weeks: int) -> int:
        return self.items_per_week * max(0, weeks)

    @property
    def publish_day_indices(self) -> list[int]:
        return [WEEKDAY_NAMES.index(d) for d in self.publish_days if d in WEEKDAY_NAMES]

    def describe_days(self) -> str:
        return " & ".join(self.publish_days) if self.publish_days else ""


_CADENCE_LABELS = {
    1: "1 video/week (3-4 releases/month)",
    2: "2 videos/week (~8 releases/month)",
    3: "3 videos/week",
}


def compute_cadence(
    metrics: dict, upload_timing: dict | None = None, rules: ReportRules = DEFAULT_RULES
) -> Cadence:
    """Derive the recommended cadence and publishing days from measured history.

    ``publish_days`` is truncated to ``items_per_week``: a channel publishing once
    a week gets one day, not the two-day list the timing analysis ranked, because
    the roadmap then has to place exactly that many dates.
    """
    upw = metrics.get("uploads_per_week")
    if upw is None:
        freq = (metrics.get("upload_frequency") or "").lower()
        if "daily" in freq or "3 uploads" in freq:
            upw = 3.0
        elif "2 uploads" in freq or "2-3" in freq:
            upw = 2.0
        else:
            upw = 1.0
    upw = float(upw or 0.0)

    if upw >= 2.8:
        items = 3
    elif upw >= 1.8:
        items = 2
    else:
        items = 1

    days: tuple[str, ...] = ()
    best_win = (upload_timing or {}).get("best_window") or {}
    if best_win.get("day_confident"):
        ranked = [d for d in (best_win.get("best_days") or []) if d in WEEKDAY_NAMES]
        days = tuple(ranked[:items])

    return Cadence(
        items_per_week=items,
        uploads_per_week=round(upw, 2),
        label=_CADENCE_LABELS[items],
        publish_days=days,
    )


# ── Cadence claims hiding in LLM prose ────────────────────────────────────────

_WEEKS_PER_MONTH = 4.345

# Each pattern yields uploads-per-week so competing phrasings become comparable.
_CADENCE_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    # "8 to 10 day publishing loop", "8-10 day cycle"
    (re.compile(r"\b(\d+)\s*(?:to|-|–|—)\s*(\d+)\s*[- ]?day\b[^.]{0,30}?\b(?:loop|cycle|cadence|rhythm|gap|interval|schedule)", re.I), "day_range"),
    # "every 10 days"
    (re.compile(r"\bevery\s+(\d+)\s*days?\b", re.I), "day_single"),
    # "3 to 4 releases per month", "4 videos a month"
    (re.compile(r"\b(\d+)\s*(?:to|-|–|—)\s*(\d+)\s*(?:videos?|uploads?|releases?|posts?)\s*(?:per|a|/)\s*month\b", re.I), "month_range"),
    (re.compile(r"\b(\d+)\s*(?:videos?|uploads?|releases?|posts?)\s*(?:per|a|/)\s*month\b", re.I), "month_single"),
    # "2 videos per week", "1 long-form documentary per week"
    (re.compile(r"\b(\d+)\s*(?:to|-|–|—)\s*(\d+)\s*[\w-]{0,20}?\s*(?:videos?|uploads?|releases?|posts?|documentar\w+)\s*(?:per|a|/)\s*week\b", re.I), "week_range"),
    (re.compile(r"\b(\d+)\s*[\w-]{0,20}?\s*(?:videos?|uploads?|releases?|posts?|documentar\w+)\s*(?:per|a|/)\s*week\b", re.I), "week_single"),
)


def extract_cadence_claims(text: str) -> list[float]:
    """Every cadence stated in a piece of prose, normalised to uploads/week."""
    if not text:
        return []
    out: list[float] = []
    for pattern, kind in _CADENCE_PATTERNS:
        for m in pattern.finditer(text):
            try:
                nums = [float(g) for g in m.groups() if g is not None]
            except (TypeError, ValueError):
                continue
            if not nums:
                continue
            mid = sum(nums) / len(nums)
            if mid <= 0:
                continue
            if kind.startswith("day"):
                out.append(7.0 / mid)
            elif kind.startswith("month"):
                out.append(mid / _WEEKS_PER_MONTH)
            else:
                out.append(mid)
    return out


def canonical_cadence_claims(cadence: Cadence) -> list[float]:
    """Every rate the canonical cadence itself asserts, in uploads/week.

    The label "1 video/week (3-4 releases/month)" states two: 1.0/week and
    ~0.81-0.92/week. Prose is checked against all of them, so a bullet that
    restates the monthly half of the canonical phrasing is not mistaken for a
    contradiction of the weekly half.
    """
    claims = extract_cadence_claims(cadence.label)
    return claims or [float(cadence.items_per_week)]


def _cadence_agrees(claim: float, canonical: list[float], tolerance: float = 0.20) -> bool:
    """Compatible with any rate the canonical cadence asserts."""
    return any(abs(claim - c) <= c * tolerance for c in canonical if c > 0)


def strip_cadence_conflicts(
    audit: dict, cadence: Cadence, conflicts: list[Conflict]
) -> None:
    """Drop audit bullets that state a cadence the canonical one contradicts.

    Scope note: this removes *numeric* disagreement — a bullet claiming twice or
    half the canonical rate — not stylistic variety. "An 8-to-10 day publishing
    loop" works out to ~0.8 uploads/week, which is what "1 video/week (3-4
    releases/month)" already means, so it survives; the audit prompt is what
    steers phrasing toward the canonical wording. What made the shipped report
    incoherent was a genuine rate conflict (eight roadmap items across four weeks
    against a stated one-per-week), and that is now impossible because the item
    count is derived from this same Cadence.
    """
    if not audit:
        return
    canonical = canonical_cadence_claims(cadence)
    for section in ("format_insights", "priorities", "whats_working", "underperforming"):
        if section not in audit:
            continue
        kept: list[str] = []
        for bullet in audit.get(section) or []:
            bad = [c for c in extract_cadence_claims(str(bullet)) if not _cadence_agrees(c, canonical)]
            if bad:
                _log(
                    conflicts,
                    "cadence_conflict",
                    f"audit.{section}",
                    f"states {bad[0]:.2f} uploads/week, canonical is {cadence.label!r}: {bullet!r}",
                    "bullet dropped",
                )
                continue
            kept.append(bullet)
        audit[section] = kept


# ── Video age and underperformance ────────────────────────────────────────────


def _published_dt(video: dict) -> datetime | None:
    from app.services.youtube_metrics import _parse_iso_datetime

    return _parse_iso_datetime(video.get("published_at"))


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def split_by_age(
    videos: list[dict], now: datetime | None = None, fresh_days: int = DEFAULT_RULES.fresh_upload_days
) -> tuple[list[dict], list[dict]]:
    """Split into (mature, fresh). Undated videos count as mature.

    A video published this week has not finished accumulating views. Comparing it
    to a lifetime median and calling the gap "underperforming" is a statement
    about its age, not its quality.
    """
    ref = _now(now)
    cutoff = ref - timedelta(days=fresh_days)
    mature, fresh = [], []
    for v in videos:
        dt = _published_dt(v)
        (fresh if dt is not None and dt > cutoff else mature).append(v)
    return mature, fresh


def views_per_hour(video: dict, now: datetime | None = None) -> float | None:
    """Views per hour since publication — the only fair comparison across ages."""
    dt = _published_dt(video)
    if dt is None:
        return None
    hours = (_now(now) - dt).total_seconds() / 3600.0
    if hours < 1:
        return None
    return round(int(video.get("views") or 0) / hours, 2)


def early_signal(
    videos: list[dict], now: datetime | None = None, rules: ReportRules = DEFAULT_RULES
) -> list[dict]:
    """Fresh uploads assessed at matched age, never against lifetime totals.

    Each fresh video's views/hour is compared with the views/hour the mature
    catalogue had achieved *by the same age*, so a three-day-old video is measured
    against three-day-old history rather than against finished lifetimes.
    """
    mature, fresh = split_by_age(videos, now, rules.fresh_upload_days)
    if not fresh:
        return []

    ref = _now(now)
    out = []
    for v in fresh:
        dt = _published_dt(v)
        vph = views_per_hour(v, ref)
        if dt is None or vph is None:
            continue
        age_hours = (ref - dt).total_seconds() / 3600.0

        # What the mature catalogue looked like at this same age. Without
        # per-day view history the best available proxy is lifetime views/hour,
        # which understates early velocity — so this is a floor, and it is
        # labelled as an early signal rather than a verdict.
        peers = [p for p in (views_per_hour(m, ref) for m in mature) if p]
        peer_median = sorted(peers)[len(peers) // 2] if peers else None

        out.append({
            "video_id": v.get("video_id") or "",
            "title": v.get("title") or "",
            "views": int(v.get("views") or 0),
            "published_at": dt.isoformat()[:10],
            "age_days": round(age_hours / 24.0, 1),
            "views_per_hour": vph,
            "peer_views_per_hour": peer_median,
            "ratio": round(vph / peer_median, 2) if peer_median else None,
        })
    return sorted(out, key=lambda x: x["age_days"])


def flag_underperforming_videos(
    videos: list[dict],
    baseline: float,
    rules: ReportRules = DEFAULT_RULES,
    now: datetime | None = None,
) -> list[dict]:
    """The videos the report is allowed to call underperforming.

    Deterministic and structured, not prose — the roadmap validator has to be
    able to match a generated justification against this list, which it cannot do
    against a sentence like "abstract theory content underdelivers".

    Fresh uploads are excluded by construction (see ``split_by_age``), so a video
    can never be flagged for the crime of having been published recently.
    """
    if baseline <= 0:
        return []
    mature, _fresh = split_by_age(videos, now, rules.fresh_upload_days)
    threshold = baseline * rules.underperform_ratio
    flagged = [
        {
            "video_id": v.get("video_id") or "",
            "title": v.get("title") or "",
            "views": int(v.get("views") or 0),
            "published_at": (v.get("published_at") or "")[:10]
            if isinstance(v.get("published_at"), str)
            else "",
            "ratio": round(int(v.get("views") or 0) / baseline, 2) if baseline else None,
        }
        for v in mature
        if int(v.get("views") or 0) < threshold and (v.get("title") or "").strip()
    ]
    return sorted(flagged, key=lambda x: x["views"])


# ── Matching a generated justification against the flagged list ───────────────

_TOKEN_STOPWORDS = {
    "the", "and", "for", "with", "your", "you", "this", "that", "from", "into",
    "about", "what", "when", "why", "how", "video", "videos", "channel", "part",
    "episode", "full", "official", "series", "watch", "best", "top", "new",
}


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").casefold()).strip()


def _distinctive_tokens(text: str) -> set[str]:
    return {
        t for t in _normalise(text).split()
        if len(t) >= 4 and t not in _TOKEN_STOPWORDS
    }


def cites_flagged_video(text: str, flagged: list[dict]) -> dict | None:
    """Does this justification point at a video the audit flagged as failing?

    Exact-substring catches a quoted title; the token test catches the paraphrase
    that actually shipped — a roadmap item calling "I Found A Neuroscience Paper
    On Messi's Brain" a proven "Messi brain research pillar".
    """
    if not text or not flagged:
        return None
    norm = _normalise(text)
    text_tokens = _distinctive_tokens(text)

    for item in flagged:
        title = item.get("title") or ""
        if not title.strip():
            continue
        norm_title = _normalise(title)
        if norm_title and norm_title in norm:
            return item
        title_tokens = _distinctive_tokens(title)
        if not title_tokens:
            continue
        overlap = title_tokens & text_tokens
        if len(overlap) >= 2 and len(overlap) / len(title_tokens) >= 0.4:
            return item
    return None


# ── External metric / popularity signal checks (FIX 2) ─────────────────────────

# A NUMBER attached to an off-platform popularity unit is what makes a phrase a
# borrowed metric. The bare words are ordinary English outside this repo's
# original niche, and the bare forms used to fire on them: an astronomy channel's
# "your videos about stars", a film channel's "five-star reviews" and a football
# channel's "the star player teardown" were all flagged as external-metric
# violations, forced a roadmap regeneration, and then had the clause deleted
# outright by strip_external_metric_phrases. The platform names stay — they are
# proper nouns, and naming one in a rationale is still off-limits in any niche.
EXTERNAL_METRIC_PATTERNS = (
    r"\b\d[\d,.]*\s*[kKmM]?[\s-]*(?:stars?|upvotes?|followers?|forks?|claps?|points?)\b",
    r"\b(?:stars?|upvotes?|points?)\s*/\s*day\b",
    r"\btrended\b",
    r"\bwent\s+viral\b",
    r"\bproduct\s*hunt\b",
    r"\bgithub\b",
)

EXTERNAL_METRIC_RE = re.compile(
    "|".join(EXTERNAL_METRIC_PATTERNS),
    re.IGNORECASE,
)


def mentions_external_metric(text: str) -> bool:
    """True when text cites raw external metrics, star counts, upvotes, or platform trends."""
    return bool(text) and bool(EXTERNAL_METRIC_RE.search(str(text)))


def strip_external_metric_phrases(text: str) -> str:
    """Remove raw external metric citations, preserving channel-data performance justifications.

    If an item justification contains an external popularity signal or raw metric
    (e.g., "CUDA cutlass trended on GitHub (9 stars/day)", "Product Hunt's God's Eye View went viral"),
    strip that clause while keeping any channel-grounded evidence.
    """
    if not mentions_external_metric(text):
        return str(text or "")

    sentences = _SENTENCE_SPLIT_RE.split(str(text))
    kept_sentences: list[str] = []

    for sentence in sentences:
        if not mentions_external_metric(sentence):
            kept_sentences.append(sentence.strip())
            continue

        # Split into sub-clauses by comma, semicolon, dash, or conjunctions
        clauses = re.split(r"([,;—–]|\b(?:while|as|following|after)\b)", sentence)
        repaired_parts: list[str] = []
        for clause in clauses:
            if not mentions_external_metric(clause):
                repaired_parts.append(clause)

        repaired = _tidy("".join(repaired_parts))
        words = re.findall(r"[A-Za-z0-9]{2,}", repaired)
        if words and not mentions_external_metric(repaired):
            if not repaired.endswith((".", "!", "?")):
                repaired += "."
            kept_sentences.append(repaired)

    result = _tidy(" ".join(kept_sentences))
    return result if not mentions_external_metric(result) else ""


# ── The validation sweep ──────────────────────────────────────────────────────


def _drop_time_claim(timing: dict, reason: str, conflicts: list[Conflict], check: str) -> None:
    """Remove the time-of-day recommendation, keeping the day finding intact."""
    from app.services.youtube_metrics import compose_window_copy

    win = timing.get("best_window") or {}
    _log(conflicts, check, "upload_timing", reason, "time-of-day recommendation dropped")

    # Close the gate itself, not just this one field: every other surface reads
    # ``timing_allows_time_of_day``, and a window dropped here must be silent in
    # the prose too. ``has_hour_data`` is deliberately left alone — it says the
    # breakdown table has enough data to be worth printing, which is still true
    # when a specific window failed its evidence check.
    timing["time_of_day_allowed"] = False
    win["best_time_slot"] = None
    win["best_slot_key"] = None
    win["slot_multiplier"] = None
    win["slot_lift_pct"] = 0
    win["slot_sample"] = 0
    win["slot_confident"] = False
    win["window_proof_count"] = 0

    copy = compose_window_copy(
        win.get("best_days") or [], None, win.get("day_multiplier") or 0.0, None,
        win.get("proof_count") or 0, win.get("top_tier_count") or 0, 0,
    )
    win.update(copy)

    for bucket in ("top_timing_videos", "evidence_videos"):
        for v in timing.get(bucket) or []:
            v["in_best_window"] = False


def _check_timing(report: dict, rules: ReportRules, conflicts: list[Conflict]) -> None:
    timing = (report.get("metrics") or {}).get("upload_timing") or {}
    win = timing.get("best_window")
    if not win:
        return

    # 1. Arithmetic. A subset cannot exceed the list it was drawn from; if it
    # does, the counting logic is broken and the report must not render.
    proof, tier = win.get("proof_count") or 0, win.get("top_tier_count") or 0
    window_proof = win.get("window_proof_count") or 0
    if proof > tier:
        raise ReportIntegrityError(
            f"breakout proof counts {proof} videos out of a top tier of {tier} — "
            f"the numerator and denominator are not from the same list"
        )
    if window_proof > proof:
        raise ReportIntegrityError(
            f"window proof ({window_proof}) exceeds the day proof ({proof}) it is a subset of"
        )

    if not win.get("best_time_slot"):
        return

    # 2. The recommended window must be the highest-average qualifying bucket.
    slots = timing.get("time_slots") or []
    qualifying = [s for s in slots if (s.get("video_count") or 0) >= rules.min_slot_sample]
    if not qualifying:
        _drop_time_claim(
            timing,
            f"no time window has {rules.min_slot_sample}+ uploads",
            conflicts, "window_sample",
        )
        return

    winner = max(qualifying, key=lambda s: s.get("avg_views") or 0)
    if winner.get("slot") != win.get("best_slot_key"):
        _drop_time_claim(
            timing,
            f"recommended {win.get('best_slot_key')} but {winner.get('slot')} has the "
            f"highest average ({winner.get('avg_views'):,} vs "
            f"{next((s.get('avg_views') for s in slots if s.get('slot') == win.get('best_slot_key')), 0):,})",
            conflicts, "window_not_winner",
        )
        return

    # 3. The cited evidence must actually back the claim.
    evidence = timing.get("evidence_videos") or []
    if evidence:
        agreement = sum(1 for v in evidence if v.get("in_best_window")) / len(evidence)
        if agreement < rules.min_evidence_agreement:
            _drop_time_claim(
                timing,
                f"only {agreement:.0%} of the {len(evidence)} cited evidence videos fall "
                f"inside {win.get('best_time_slot')}",
                conflicts, "evidence_disagrees",
            )


def _check_buckets(report: dict, rules: ReportRules, conflicts: list[Conflict]) -> None:
    """No claim may name a length bucket that is below the sample floor."""
    metrics = report.get("metrics") or {}
    thin = {
        name for name, st in (metrics.get("buckets") or {}).items()
        if (st.get("count") or 0) < rules.min_bucket_sample
    }
    if not thin:
        return

    headline = report.get("headline")
    if headline and headline.get("kind") == "duration_bucket" and headline.get("label") in thin:
        _log(
            conflicts, "thin_bucket_claim", "headline",
            f"headline names {headline['label']} with n={headline.get('sample')} "
            f"(floor is {rules.min_bucket_sample})",
            "headline dropped",
        )
        report["headline"] = None
        report["outreach_line"] = ""
        report["outreach_hooks"] = {}


def _check_roadmap(
    report: dict, cadence: Cadence | None, flagged: list[dict], rules: ReportRules,
    conflicts: list[Conflict],
) -> None:
    from datetime import date as _date

    roadmap = report.get("roadmap") or {}
    weeks = roadmap.get("weeks") or []

    # 1. One cadence, stated once, authored in Python.
    if cadence is not None:
        if roadmap.get("cadence") != cadence.label:
            _log(
                conflicts, "cadence_conflict", "roadmap.cadence",
                f"roadmap says {roadmap.get('cadence')!r}, canonical is {cadence.label!r}",
                "overwritten with the canonical cadence",
            )
            roadmap["cadence"] = cadence.label

        # 2. Every date must land on a recommended publishing day.
        allowed = set(cadence.publish_day_indices)
        if allowed:
            for week in weeks:
                for item in week.get("items") or []:
                    raw = item.get("date")
                    if not raw:
                        continue
                    try:
                        when = _date.fromisoformat(str(raw))
                    except ValueError:
                        _log(conflicts, "bad_date", "roadmap", f"unparseable date {raw!r}", "date removed")
                        item.pop("date", None)
                        continue
                    if when.weekday() not in allowed:
                        _log(
                            conflicts, "date_weekday_mismatch", "roadmap",
                            f"{raw} is a {WEEKDAY_NAMES[when.weekday()]}, "
                            f"but the plan publishes {cadence.describe_days()}",
                            "date removed",
                        )
                        item.pop("date", None)

    # 3. No item may cite a video the audit flagged as underperforming.
    for week in weeks:
        for item in week.get("items") or []:
            blob = " ".join(
                str(item.get(k) or "") for k in ("rationale", "title", "theme")
            )
            hit = cites_flagged_video(blob, flagged)
            if hit:
                _log(
                    conflicts, "cites_flagged_video", "roadmap",
                    f"item {item.get('title')!r} cites {hit['title']!r} "
                    f"({hit['views']:,} views, flagged underperforming)",
                    "justification stripped",
                )
                item["rationale"] = ""

    # 4. No item may cite raw external metrics or platform popularity signals.
    for week in weeks:
        for item in week.get("items") or []:
            rat = str(item.get("rationale") or "")
            if mentions_external_metric(rat):
                cleaned = strip_external_metric_phrases(rat)
                _log(
                    conflicts, "external_metric_violation", "roadmap",
                    f"item {item.get('title')!r} cited raw external metrics: {rat!r}",
                    "clause stripped" if cleaned else "rationale stripped",
                )
                item["rationale"] = cleaned


# ── Narrative claims vs. computed data ───────────────────────────────────────
# The two checks below exist because of one shipped report. A fallback model,
# handed the channel's real numbers, wrote a strategy that inverted them: it
# recommended the four *worst* weekdays for uploading, and said short-form
# "hasn't been explored yet" for a channel with eight short videos already up.
#
# Both claims were flatly contradicted by tables printed in the same document.
# Neither the prose nor the tables were wrong in isolation — nothing compared
# them. These checks do that comparison, on every tier including the primary,
# because a strong model on an off day makes the same class of mistake.

#: The prose sections of the audit. Same four that strip_cadence_conflicts walks.
NARRATIVE_SECTIONS = ("whats_working", "underperforming", "format_insights", "priorities")

#: Every audit field a reader sees as prose. Wider than NARRATIVE_SECTIONS on
#: purpose: the day/format checks need a claim to check, but "no hour anywhere"
#: has to hold in the verdict and the content gaps too, or the contradiction
#: simply moves one paragraph up.
TIME_CLAIM_SECTIONS = NARRATIVE_SECTIONS + ("verdict", "content_gaps")

#: The roadmap fields that can carry a *scheduling claim*. Deliberately not the
#: title: "The 5AM Discipline Teardown" is a video about getting up early, not a
#: recommendation to upload at five, and scrubbing a creator's content idea to
#: satisfy a timing rule would be its own kind of wrong answer.
ROADMAP_PROSE_FIELDS = ("rationale",)

_DAY_RE = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b", re.IGNORECASE
)

# A day name alone is not a claim. "Tuesday uploads underperform" *names* Tuesday
# in order to advise against it, and flagging that would be exactly backwards.
# Only prescriptive phrasing counts.
_RECOMMEND_RE = re.compile(
    r"\b(?:post|posting|publish|publishing|upload|uploading|release|releasing|"
    r"schedule|scheduling|shift|move|switch|focus|concentrate|prioriti[sz]e|"
    r"target|aim|stick|lean|double\s+down|best\s+day|optimal|ideal|"
    r"recommend\w*|should)\b",
    re.IGNORECASE,
)

# Phrases that turn a recommendation into its opposite. "Avoid posting on
# Tuesday" matches _RECOMMEND_RE via "posting"; this is what saves it.
_AVOID_RE = re.compile(
    r"\b(?:avoid|stop|cease|away\s+from|instead\s+of|rather\s+than|"
    r"not\s+on|never|drop|abandon|reduce|cut\s+back|"
    r"underperform\w*|worst|weakest|poorly|lowest)\b",
    re.IGNORECASE,
)

# Claims that a format is absent or untried.
_ABSENCE_RE = re.compile(
    r"(?:has(?:n't|\s+not)\s+been\s+(?:explored|tried|attempted|tested|used|touched)"
    r"|hasn't\s+explored"
    r"|no\s+content\s+in\s+this\s+category"
    r"|no\s+(?:existing\s+)?(?:videos?|content|uploads?)\s+in"
    r"|has\s+yet\s+to\s+(?:be\s+)?(?:explore|try|attempt|test|publish|upload)"
    r"|yet\s+to\s+be\s+(?:explored|tried|attempted|tested)"
    r"|never\s+(?:been\s+)?(?:explored|tried|attempted|published|uploaded|used)"
    r"|(?:entirely|completely|totally)\s+(?:absent|missing|unexplored|untapped)"
    r"|(?:remains?|is|are)\s+(?:unexplored|untapped|untouched|absent|missing|nonexistent)"
    r"|under-?utili[sz]ed"
    r"|under-?explored"
    r"|un(?:explored|tapped|touched|tried)"
    r"|absent\s+from\s+the\s+catalog"
    r"|zero\s+(?:videos?|content|uploads?)"
    r"|lacks?\s+(?:any\s+)?(?:short|long)"
    r"|missing\s+entirely)",
    re.IGNORECASE,
)

#: Words a narrative uses for each computed length bucket. The bucket labels
#: themselves ("Shorts (<=1m)") never appear in prose, so matching has to go
#: through aliases; each alias is anchored on a word boundary to keep "1-5 min"
#: from matching inside "11-5 min".
_BUCKET_ALIASES: dict[str, tuple[str, ...]] = {
    "Shorts (<=1m)": (
        "short-form", "short form", "shortform", "shorts", "youtube shorts",
        "sub-minute", "under a minute", "vertical video", "vertical content",
    ),
    "1-5 min": ("1-5 min", "1 to 5 minute", "one to five minute", "short videos"),
    "5-15 min": ("5-15 min", "5 to 15 minute", "mid-length", "mid length"),
    "15-30 min": ("15-30 min", "15 to 30 minute"),
    "30+ min": (
        "30+ min", "30 plus minute", "long-form", "long form", "longform",
        "deep dive", "documentary", "extended format",
    ),
}


def _ranked_days(upload_timing: dict, rules: ReportRules) -> list[dict]:
    """Days with enough uploads to judge, strongest first."""
    days = (upload_timing or {}).get("days") or []
    qualifying = [
        d for d in days
        if int(d.get("video_count") or 0) >= rules.min_day_sample
        and d.get("multiplier") is not None
    ]
    return sorted(qualifying, key=lambda d: d.get("multiplier") or 0, reverse=True)


def _acceptable_days(upload_timing: dict, rules: ReportRules) -> tuple[set[str], list[dict]]:
    """The days a narrative may legitimately recommend.

    Anchored on the computed ``best_days`` where they exist, then widened to
    include any day that performs at least as well as the weakest of them. The
    widening matters: two days can be statistically indistinguishable, and
    failing a report for naming the second one would be pedantry, not integrity.
    """
    ranked = _ranked_days(upload_timing, rules)
    if not ranked:
        return set(), ranked

    best = {
        str(d) for d in ((upload_timing.get("best_window") or {}).get("best_days") or [])
    }
    known = {d["day"] for d in ranked}
    best &= known
    if not best:
        best = {ranked[0]["day"]}

    floor = min(d["multiplier"] for d in ranked if d["day"] in best)
    return {d["day"] for d in ranked if (d.get("multiplier") or 0) >= floor}, ranked


def check_day_claims(
    audit: dict, upload_timing: dict, rules: ReportRules = DEFAULT_RULES
) -> list[tuple[str, str, str]]:
    """Narrative day recommendations that the computed multipliers contradict.

    Returns ``(section, bullet, reason)`` for each offending bullet.
    """
    if not audit or not upload_timing:
        return []
    acceptable, ranked = _acceptable_days(upload_timing, rules)
    if not acceptable:
        # Not enough data to rank days; a day claim cannot be checked, and an
        # unverifiable claim is not the same as a false one.
        return []

    # `ranked` (sample floor applied) sets the bar; `judgeable` is every day
    # with any data at all. Recommending a 1.0x day over a 1.55x one is a
    # contradiction whether or not the weak day clears the sample floor — the
    # floor exists to stop thin data *making* a recommendation, not to make a
    # thin day immune from being one.
    judgeable = {
        d["day"]: d
        for d in (upload_timing.get("days") or [])
        if int(d.get("video_count") or 0) > 0 and d.get("multiplier") is not None
    }
    floor = min(
        (d["multiplier"] for d in ranked if d["day"] in acceptable),
        default=0,
    )
    top_label = ", ".join(
        f"{d['day']} ({d['multiplier']}x)" for d in ranked if d["day"] in acceptable
    )

    findings: list[tuple[str, str, str]] = []
    for section in NARRATIVE_SECTIONS:
        for bullet in audit.get(section) or []:
            text = str(bullet)
            named = {m.group(1).capitalize() for m in _DAY_RE.finditer(text)}
            if not named:
                continue
            if not _RECOMMEND_RE.search(text) or _AVOID_RE.search(text):
                continue
            bad = sorted(
                d for d in named
                if d in judgeable
                and d not in acceptable
                and (judgeable[d].get("multiplier") or 0) < floor
            )
            if bad:
                worst = ", ".join(
                    f"{d} ({judgeable[d]['multiplier']}x)" for d in bad
                )
                findings.append((
                    section,
                    text,
                    f"recommends {worst} but the computed top performers are {top_label}",
                ))
    return findings


# ── Time-of-day claims the gate has already ruled out ─────────────────────────
#
# The shipped contradiction: page 2's timing widget printed "Not enough uploads
# carry a publish time to recommend a time of day" and showed the window as "—",
# while page 1's Format & Cadence narrative and Strategic Priorities both
# recommended "Saturday & Sunday between 09:00-12:00 UTC (2.27x channel median)".
# The widget consulted the gate; the narrative model was handed the raw hour
# buckets and invented a window from them.
#
# The prompt now forbids it (see ``youtube_ai_analysis.TIME_OF_DAY_FORBIDDEN``)
# and the context no longer ships the hour breakdown when the gate is closed.
# What follows is the last line: prose that names an hour anyway is repaired
# before it can render.

#: A clock time, a meridiem, or a timezone label. Deliberately narrow — day
#: names, multipliers, "30+ min" and "8-10 day loop" must all pass through
#: untouched, and a part-of-day word ("morning routine") is a topic on plenty of
#: channels, not a scheduling claim.
_TIME_TOKEN = (
    r"(?:\b[0-2]?\d:[0-5]\d\b"                      # 09:00, 9:30
    r"|\b\d{1,2}\s?(?:[ap]\.m\.|[ap]m\b)"           # 9am, 5 p.m.
    r"|\b\d{1,2}\s?(?:o'clock)\b"
    r"|\bUTC\b|\bGMT\b)"
)
_TIME_CLAIM_RE = re.compile(_TIME_TOKEN, re.IGNORECASE)

#: A parenthetical containing a clock time — "(09:00-12:00 UTC)".
_TIME_PARENS_RE = re.compile(rf"\s*\([^()]*?{_TIME_TOKEN}[^()]*?\)", re.IGNORECASE)

#: A weekday, never eaten however much else goes: "at 9am on Saturdays" must
#: come out as "on Saturdays", not as nothing. "on" is likewise absent from the
#: preposition list below for the same reason.
_DAY_AHEAD = r"(?!\s*\b(?:on|every|each|and|&)?\s*(?:mon|tues|wednes|thurs|fri|satur|sun)day)"

#: The prepositional clause that carries the window, plus any figure hanging off
#: it. "(2.27x the channel median)" after "between 09:00-12:00 UTC" is the *slot*
#: multiplier; leaving it attached to the surviving day clause would re-label a
#: time-of-day number as a day-of-week one, which is the same bug wearing a hat.
_TIME_CLAUSE_RE = re.compile(
    r"[,;:]?\s*\b(?:between|from|at|around|near|by|before|after|during|in|into|"
    r"within|to|toward|towards)\b\s+[^,;]{0,40}?"
    rf"{_TIME_TOKEN}"
    rf"(?:{_DAY_AHEAD}[^,;.()]){{0,40}}"   # the rest of the window, never a bracket
    r"[^\s,;.()]*"                        # ...and never half a word
    r"(?:\s*\([^()]*\))?",                # the figure hanging off it comes too
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _tidy(text: str) -> str:
    """Close the gaps a removed clause leaves behind."""
    text = re.sub(r"\s{2,}", " ", text)
    # An adverb left stranded by the clause it modified — ", ideally, where..."
    text = re.sub(
        r",\s*(?:ideally|preferably|specifically|namely|typically|especially|"
        r"particularly|roughly|around)\s*(?=[,.])",
        "", text, flags=re.IGNORECASE,
    )
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,;:])\s*([.!?])", r"\2", text)
    text = re.sub(r"(^|\s)[,;:]\s*", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    return text.strip(" \t-–—,;:")


def mentions_time_of_day(text: str) -> bool:
    """True when a piece of prose names a clock time, an hour or a UTC window."""
    return bool(text) and bool(_TIME_CLAIM_RE.search(str(text)))


def strip_time_of_day_phrases(text: str) -> str:
    """Remove the hour claim from a bullet, keeping everything else it says.

    Clause surgery first, sentence removal only as a fallback, because the day
    finding usually lives in the same sentence as the window — "Publish on
    Saturday & Sunday between 09:00-12:00 UTC" must come out as "Publish on
    Saturday & Sunday", not as nothing at all. A sentence still naming an hour
    after surgery (or reduced to a fragment by it) is dropped whole; a bullet
    with nothing left is dropped by the caller.
    """
    if not mentions_time_of_day(text):
        return str(text or "")

    kept: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(str(text)):
        if not mentions_time_of_day(sentence):
            kept.append(sentence.strip())
            continue

        ends_sentence = sentence.rstrip().endswith((".", "!", "?"))
        repaired = _TIME_PARENS_RE.sub(" ", sentence)
        repaired = _TIME_CLAUSE_RE.sub(" ", repaired)
        repaired = _tidy(repaired)

        # Still an hour in it, or nothing left worth reading: the sentence goes.
        # A surviving weekday earns its keep on its own — "Saturday & Sunday" is
        # the finding this whole exercise exists to preserve, and a word count
        # would throw it away.
        words = re.findall(r"[A-Za-z0-9]{2,}", repaired)
        if mentions_time_of_day(repaired):
            continue
        if len(words) < 4 and not _DAY_RE.search(repaired):
            continue
        if ends_sentence and not repaired.endswith((".", "!", "?")):
            repaired += "."
        kept.append(repaired)

    return _tidy(" ".join(k for k in kept if k))


def check_time_of_day_claims(
    audit: dict, upload_timing: dict, rules: ReportRules = DEFAULT_RULES
) -> list[tuple[str, str, str]]:
    """Narrative hour claims made while the timing gate is closed.

    Returns ``(section, bullet, reason)``, the same shape as the other narrative
    checks, so a violation feeds the one regeneration pass before anything is
    stripped programmatically.
    """
    from app.services.youtube_metrics import timing_allows_time_of_day

    if not audit or timing_allows_time_of_day(upload_timing):
        return []

    findings: list[tuple[str, str, str]] = []
    for section in TIME_CLAIM_SECTIONS:
        value = audit.get(section)
        bullets = [value] if isinstance(value, str) else (value or [])
        for bullet in bullets:
            text = str(bullet)
            if not mentions_time_of_day(text):
                continue
            findings.append((
                section,
                text,
                "names a time of day, but too few uploads carry a publish time for "
                "this channel to support an hour-level recommendation — days of the "
                "week only",
            ))
    return findings


def check_absence_claims(
    audit: dict, buckets: dict, rules: ReportRules = DEFAULT_RULES
) -> list[tuple[str, str, str]]:
    """"We've never tried X" claims about a format the channel already publishes.

    Checked against the actual per-bucket video counts, so a claim only survives
    if the bucket really is empty.
    """
    if not audit or not buckets:
        return []

    findings: list[tuple[str, str, str]] = []
    for section in NARRATIVE_SECTIONS:
        for bullet in audit.get(section) or []:
            text = str(bullet)
            if not _ABSENCE_RE.search(text):
                continue
            lowered = text.lower()
            for label, aliases in _BUCKET_ALIASES.items():
                stats = buckets.get(label) or {}
                # Buckets are built with "count"; a bucket with no videos is
                # absent from the dict entirely, so .get() returning None is
                # the "claim is true" case and must stay silent.
                count = int(stats.get("count") or stats.get("video_count") or 0)
                if count <= 0:
                    continue  # the claim is true for this bucket
                if not any(
                    re.search(rf"(?<!\w){re.escape(alias)}", lowered) for alias in aliases
                ):
                    continue
                findings.append((
                    section,
                    text,
                    f"claims {label!r} is unexplored, but the channel has "
                    f"{count} video{'s' if count != 1 else ''} in that bucket",
                ))
                break
    return findings


def narrative_violations(
    audit: dict, metrics: dict, rules: ReportRules = DEFAULT_RULES
) -> list[tuple[str, str, str]]:
    """Every narrative claim contradicted by the channel's own computed data."""
    metrics = metrics or {}
    timing = metrics.get("upload_timing") or {}
    return (
        check_day_claims(audit, timing, rules)
        + check_absence_claims(audit, metrics.get("buckets") or {}, rules)
        + check_time_of_day_claims(audit, timing, rules)
    )


def _enforce_time_of_day_silence(
    report: dict, rules: ReportRules, conflicts: list[Conflict]
) -> None:
    """When the gate is closed, no prose in the document may name an hour.

    Runs after the one regeneration pass the prospect service gives the model.
    A bullet is repaired rather than deleted: the day-of-week finding is valid
    and has to survive in every section that carried it, so only the clause
    making the hour claim comes out. A bullet that is *nothing but* an hour
    claim has nothing left to keep, and goes.
    """
    from app.services.youtube_metrics import timing_allows_time_of_day

    timing = (report.get("metrics") or {}).get("upload_timing") or {}
    if timing_allows_time_of_day(timing):
        return

    def _repair(section: str, text: str) -> str:
        cleaned = strip_time_of_day_phrases(text)
        if cleaned == text:
            return text
        _log(
            conflicts, "time_of_day_not_allowed", section,
            f"named a time of day with the timing gate closed: {text!r}",
            "hour claim stripped" if cleaned else "bullet dropped",
        )
        return cleaned

    audit = report.get("audit") or {}
    for section in TIME_CLAIM_SECTIONS:
        value = audit.get(section)
        if isinstance(value, str):
            audit[section] = _repair(f"audit.{section}", value)
        elif value:
            audit[section] = [
                cleaned
                for cleaned in (_repair(f"audit.{section}", str(b)) for b in value)
                if cleaned
            ]

    roadmap = report.get("roadmap") or {}
    for week in roadmap.get("weeks") or []:
        if week.get("focus"):
            week["focus"] = _repair("roadmap.focus", str(week["focus"]))
        for item in week.get("items") or []:
            for field in ROADMAP_PROSE_FIELDS:
                if item.get(field):
                    item[field] = _repair(f"roadmap.{field}", str(item[field]))


def _check_narrative(report: dict, rules: ReportRules, conflicts: list[Conflict]) -> None:
    """Strip narrative bullets the data contradicts.

    This is the last line, not the first: the prospect service regenerates an
    offending section once before the report reaches here (see
    ``_regenerate_contradicted_sections``). Anything still contradicted at this
    point has survived a correction round, so it is dropped rather than retried.

    Hour claims are handled separately by ``_enforce_time_of_day_silence`` — they
    are repaired in place instead of deleted, because the bullet's day-of-week
    half is usually correct and must be preserved.
    """
    audit = report.get("audit") or {}
    metrics = report.get("metrics") or {}
    findings = (
        check_day_claims(audit, metrics.get("upload_timing") or {}, rules)
        + check_absence_claims(audit, metrics.get("buckets") or {}, rules)
    )
    if not findings:
        return

    doomed: dict[str, set[str]] = {}
    for section, bullet, reason in findings:
        doomed.setdefault(section, set()).add(bullet)
        _log(
            conflicts,
            "narrative_contradicts_data",
            f"audit.{section}",
            reason,
            "bullet dropped after regeneration failed",
        )

    for section, bullets in doomed.items():
        audit[section] = [b for b in (audit.get(section) or []) if str(b) not in bullets]


def validate_report(
    report: dict,
    cadence: Cadence | None = None,
    flagged: list[dict] | None = None,
    rules: ReportRules = DEFAULT_RULES,
) -> list[Conflict]:
    """Final sweep for internal contradictions. Mutates ``report`` in place.

    Runs after generation and before the report dict is returned — upstream of
    persistence, the cache, the web view and the PDF — so one call covers every
    surface. Returns the conflicts found and repaired; raises
    ``ReportIntegrityError`` only for the arithmetic invariants.
    """
    conflicts: list[Conflict] = []
    _check_timing(report, rules, conflicts)
    _check_buckets(report, rules, conflicts)
    _check_narrative(report, rules, conflicts)
    _check_roadmap(report, cadence, flagged or [], rules, conflicts)
    # Last, and after _check_timing may have closed the gate itself: no section
    # of a rendered report may name an hour the gate does not allow.
    _enforce_time_of_day_silence(report, rules, conflicts)
    return conflicts
