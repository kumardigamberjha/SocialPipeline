"""One test per shipped contradiction, against the WillPower Star figures.

Each test names the claim that reached a real creator and asserts it can no
longer be produced from the same data.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.youtube_ai_analysis import _format_flagged_videos
from app.services.youtube_metrics import analyze_upload_timing
from app.services.youtube_prospect_service import build_prospect_context, pick_headline_metric
from app.services.youtube_report_rules import (
    DEFAULT_RULES,
    EXTERNAL_METRIC_RE,
    NARRATIVE_SECTIONS,
    Cadence,
    ReportIntegrityError,
    ReportRules,
    cites_flagged_video,
    compute_cadence,
    early_signal,
    extract_cadence_claims,
    flag_underperforming_videos,
    mentions_external_metric,
    narrative_violations,
    split_by_age,
    strip_cadence_conflicts,
    strip_external_metric_phrases,
    validate_report,
)
from conftest import (
    AFTERNOON_AVG,
    CHANNEL_MEDIAN,
    MESSI_VIDEO,
    MESSI_VIEWS,
    SHORT_BUCKET_VIEWS,
)


# ── BUG 1 — "13 of top 10 breakout videos" ───────────────────────────────────


def test_bug1_proof_counted_from_one_list(willpower_timing):
    win = willpower_timing["best_window"]
    assert win["proof_count"] <= win["top_tier_count"], "numerator exceeds its own denominator"
    assert win["window_proof_count"] <= win["proof_count"], "window hits are a subset of day hits"
    assert f"{win['proof_count']} of top {win['top_tier_count']}" in win["top_video_proof"]


def test_bug1_denominator_is_configurable_top_n(willpower_videos):
    timing = analyze_upload_timing(
        willpower_videos, CHANNEL_MEDIAN, rules=ReportRules(top_breakout_n=4)
    )
    assert timing["best_window"]["top_tier_count"] == 4


def test_bug1_impossible_count_raises_rather_than_rendering(willpower_metrics):
    """X > N can only mean the counting code broke, so it must not render."""
    report = {"metrics": willpower_metrics, "roadmap": {}, "headline": None}
    report["metrics"]["upload_timing"]["best_window"]["proof_count"] = 13
    report["metrics"]["upload_timing"]["best_window"]["top_tier_count"] = 10
    with pytest.raises(ReportIntegrityError, match="not from the same list"):
        validate_report(report)


# ── BUG 2 — a recommended window the report's own table contradicts ──────────


def test_bug2_window_is_the_highest_average_bucket(willpower_timing):
    win = willpower_timing["best_window"]
    slots = {s["slot"]: s for s in willpower_timing["time_slots"]}
    qualifying = [s for s in slots.values() if s["video_count"] >= DEFAULT_RULES.min_slot_sample]
    assert win["best_slot_key"] == max(qualifying, key=lambda s: s["avg_views"])["slot"]
    assert win["best_slot_key"] == "09:00-12:00"
    assert slots["09:00-12:00"]["avg_views"] > slots["12:00-15:00"]["avg_views"]


def test_bug2_volume_does_not_beat_performance(willpower_timing):
    """12:00-15:00 has the most uploads. It must still lose to the stronger window."""
    slots = {s["slot"]: s for s in willpower_timing["time_slots"]}
    assert slots["12:00-15:00"]["video_count"] > slots["09:00-12:00"]["video_count"]
    assert willpower_timing["best_window"]["best_slot_key"] != "12:00-15:00"


def test_bug2_no_window_below_the_sample_floor(willpower_videos):
    timing = analyze_upload_timing(
        willpower_videos, CHANNEL_MEDIAN, rules=ReportRules(min_slot_sample=50)
    )
    win = timing["best_window"]
    assert win["best_time_slot"] is None
    assert win["slot_multiplier"] is None
    assert win["slot_confident"] is False
    assert win["best_days"], "the day finding survives on its own"
    assert "14:00" not in win["recommendation"], "no invented fallback window"


def test_bug2_day_and_slot_never_share_a_value(willpower_timing):
    win = willpower_timing["best_window"]
    assert "multiplier" not in win, "the merged max(day, slot) field is gone"
    assert "lift_pct" not in win
    assert win["day_sample"] != 0 and win["slot_sample"] != 0
    # Independently computed from different populations, so they must differ here.
    assert win["day_multiplier"] != win["slot_multiplier"]


# ── BUG 3 — evidence that contradicts the recommendation ─────────────────────


def test_bug3_cited_evidence_is_the_validated_list(willpower_timing):
    assert len(willpower_timing["evidence_videos"]) == DEFAULT_RULES.evidence_cited
    assert willpower_timing["evidence_videos"] == willpower_timing["top_timing_videos"][:3]


def test_bug3_evidence_backs_the_recommended_window(willpower_timing):
    win = willpower_timing["best_window"]
    lo, hi = int(win["best_slot_key"][:2]), int(win["best_slot_key"][6:8])
    for v in willpower_timing["evidence_videos"]:
        if v["in_best_window"]:
            assert v["day_name"] in win["best_days"]
            assert lo <= v["hour"] < hi


def test_bug3_disagreeing_evidence_drops_the_time_claim(willpower_metrics):
    """The shipped case: Sat 11:30, Sun 03:30, Fri 12:30 under a 12:00-15:00 claim."""
    report = {"metrics": willpower_metrics, "roadmap": {}, "headline": None}
    timing = report["metrics"]["upload_timing"]
    for v in timing["evidence_videos"]:
        v["in_best_window"] = False

    conflicts = validate_report(report)

    assert timing["best_window"]["best_time_slot"] is None
    assert timing["best_window"]["slot_multiplier"] is None
    assert any(c.check == "evidence_disagrees" for c in conflicts)
    assert timing["best_window"]["best_days"], "the day finding is kept"


def test_bug3_window_that_is_not_the_winner_is_dropped(willpower_metrics):
    report = {"metrics": willpower_metrics, "roadmap": {}, "headline": None}
    timing = report["metrics"]["upload_timing"]
    timing["best_window"]["best_slot_key"] = "12:00-15:00"
    timing["best_window"]["best_time_slot"] = "12:00 – 15:00 UTC"

    conflicts = validate_report(report)

    assert timing["best_window"]["best_time_slot"] is None
    assert any(c.check == "window_not_winner" for c in conflicts)


# ── BUG 4 — the roadmap citing what the audit flagged ────────────────────────


def test_bug4_messi_video_is_flagged(willpower_metrics):
    titles = [v["title"] for v in willpower_metrics["flagged_videos"]]
    assert MESSI_VIDEO in titles


def test_bug4_flagged_titles_reach_the_roadmap_prompt(willpower_metrics):
    block = _format_flagged_videos(willpower_metrics["flagged_videos"])
    assert MESSI_VIDEO in block
    assert f"{MESSI_VIEWS:,}" in block
    assert "DO NOT CITE AS POSITIVE EVIDENCE" in block


@pytest.mark.parametrize(
    "rationale,expected",
    [
        ("Building on the high-engagement Messi brain research pillar", True),
        ("Our neuroscience paper on Messi's brain proved this format works", True),
        (f"Follow-up to {MESSI_VIDEO}", True),
        ("Doubling down on applied discipline builds that already win", False),
        ("A practical morning routine teardown", False),
    ],
)
def test_bug4_detects_citations_including_paraphrase(willpower_metrics, rationale, expected):
    flagged = willpower_metrics["flagged_videos"]
    assert bool(cites_flagged_video(rationale, flagged)) is expected


def test_bug4_offending_justification_is_stripped_before_render(willpower_metrics):
    cadence = Cadence(1, 1.0, "1 video/week (3-4 releases/month)", ("Saturday",))
    report = {
        "metrics": willpower_metrics,
        "headline": None,
        "roadmap": {
            "cadence": cadence.label,
            "weeks": [{
                "week_number": 1,
                "items": [{
                    "title": "The Neuroscience of Elite Genius",
                    "rationale": "Extends the high-engagement Messi brain research pillar.",
                }],
            }],
        },
    }
    conflicts = validate_report(report, cadence, willpower_metrics["flagged_videos"])

    item = report["roadmap"]["weeks"][0]["items"][0]
    assert item["rationale"] == ""
    assert any(c.check == "cites_flagged_video" for c in conflicts)


# ── BUG 5 — cadence stated four different ways ───────────────────────────────


@pytest.mark.parametrize(
    "prose,expected",
    [
        ("8 to 10 day publishing loop", 0.78),
        ("3 to 4 releases per month", 0.81),
        ("1 long-form documentary per week", 1.0),
        ("2 videos per week", 2.0),
    ],
)
def test_bug5_every_phrasing_normalises_to_uploads_per_week(prose, expected):
    assert extract_cadence_claims(prose)[0] == pytest.approx(expected, abs=0.02)


def test_bug5_one_cadence_across_every_section(willpower_metrics):
    cadence = compute_cadence(willpower_metrics, willpower_metrics["upload_timing"])
    weeks = 4
    report = {
        "metrics": willpower_metrics,
        "headline": None,
        "roadmap": {"cadence": "1 long-form documentary per week", "weeks": []},
    }
    validate_report(report, cadence, [])

    # The roadmap header, the item budget and the canonical label agree.
    assert report["roadmap"]["cadence"] == cadence.label
    assert cadence.total_items(weeks) == cadence.items_per_week * weeks


def test_bug5_item_count_is_derived_not_hardcoded(willpower_metrics):
    cadence = compute_cadence(willpower_metrics, willpower_metrics["upload_timing"])
    # The shipped report listed 8 items across 4 weeks while claiming 1/week.
    assert cadence.total_items(4) != 8 or cadence.items_per_week == 2


def test_bug5_contradicting_audit_bullet_is_dropped():
    cadence = Cadence(1, 1.0, "1 video/week (3-4 releases/month)", ("Saturday",))
    audit = {
        "format_insights": ["Ship 3 videos per week", "15-30 min holds attention best"],
        "priorities": ["Target 3 to 4 releases per month"],
    }
    conflicts: list = []
    strip_cadence_conflicts(audit, cadence, conflicts)

    assert "Ship 3 videos per week" not in audit["format_insights"]
    assert "15-30 min holds attention best" in audit["format_insights"]
    # Compatible with the canonical label's own monthly phrasing, so it stays.
    assert audit["priorities"] == ["Target 3 to 4 releases per month"]
    assert any(c.check == "cadence_conflict" for c in conflicts)


# ── BUG 6 — "published Saturdays" over Tuesday dates ─────────────────────────


def test_bug6_dates_land_on_the_recommended_weekday():
    from app.routers.youtube_analytics import _assign_roadmap_dates

    weeks = [{"week_number": i + 1, "items": [{"title": f"V{i}"}]} for i in range(4)]
    out = _assign_roadmap_dates(weeks, date(2026, 9, 1), preferred_days=["Saturday"])

    dates = [date.fromisoformat(w["items"][0]["date"]) for w in out]
    assert {d.weekday() for d in dates} == {5}
    assert dates[0] == date(2026, 9, 5)


def test_bug6_no_fallback_to_the_generation_weekday():
    """Sep 1 2026 is a Tuesday. With no signal, dates are omitted, not invented."""
    from app.routers.youtube_analytics import _assign_roadmap_dates

    weeks = [{"week_number": 1, "items": [{"title": "V"}]}]
    out = _assign_roadmap_dates(weeks, date(2026, 9, 1))
    assert "date" not in out[0]["items"][0]


def test_bug6_validator_removes_a_mismatched_date(willpower_metrics):
    cadence = Cadence(1, 1.0, "1 video/week (3-4 releases/month)", ("Saturday",))
    report = {
        "metrics": willpower_metrics,
        "headline": None,
        "roadmap": {
            "cadence": cadence.label,
            "weeks": [{"items": [{"title": "V", "date": "2026-09-01"}]}],  # a Tuesday
        },
    }
    conflicts = validate_report(report, cadence, [])
    assert "date" not in report["roadmap"]["weeks"][0]["items"][0]
    assert any(c.check == "date_weekday_mismatch" for c in conflicts)


# ── BUG 7 — fresh uploads judged against lifetime baselines ──────────────────


def test_bug7_fresh_upload_is_not_flagged(willpower_metrics):
    titles = [v["title"] for v in willpower_metrics["flagged_videos"]]
    assert "Brand New Documentary Drop" not in titles, "3 days old and still climbing"
    assert MESSI_VIDEO in titles, "mature underperformers are still flagged"


def test_bug7_split_respects_the_threshold(willpower_videos, now):
    mature, fresh = split_by_age(willpower_videos, now, fresh_days=21)
    assert [v["video_id"] for v in fresh] == ["fresh1"]
    assert len(mature) == len(willpower_videos) - 1


def test_bug7_threshold_is_configurable(willpower_videos, now):
    _mature, fresh = split_by_age(willpower_videos, now, fresh_days=1)
    assert fresh == []


def test_bug7_fresh_video_assessed_at_matched_age(willpower_videos, now):
    signal = early_signal(willpower_videos, now=now)
    assert len(signal) == 1
    entry = signal[0]
    assert entry["video_id"] == "fresh1"
    assert 3.0 <= entry["age_days"] < DEFAULT_RULES.fresh_upload_days
    assert entry["views_per_hour"] > 0
    assert entry["ratio"] is not None, "compared against same-age history, not raw totals"


def test_bug7_context_labels_the_two_cohorts_differently(willpower_metrics):
    ctx = build_prospect_context({"title": "WillPower Star", "handle": "@w"}, willpower_metrics)
    assert "FLAGGED UNDERPERFORMING" in ctx
    assert "EARLY SIGNAL" in ctx
    assert "never call one" in ctx
    # Untrusted channel titles stay inside the prompt-injection fence.
    assert ctx.index("<<<USER_DATA") < ctx.index("EARLY SIGNAL") < ctx.rindex("USER_DATA>>>")


# ── BUG 8 — a single video presented as a finding ────────────────────────────


def test_bug8_thin_bucket_exists_but_cannot_be_the_headline(willpower_metrics):
    bucket = willpower_metrics["buckets"]["1-5 min"]
    assert bucket["count"] == 1
    assert bucket["avg_views"] == SHORT_BUCKET_VIEWS
    headline = pick_headline_metric(willpower_metrics)
    assert headline is None or headline.get("label") != "1-5 min"


def test_bug8_context_marks_the_thin_bucket(willpower_metrics):
    ctx = build_prospect_context({"title": "WillPower Star", "handle": "@w"}, willpower_metrics)
    line = next(ln for ln in ctx.splitlines() if ln.strip().startswith("1-5 min:"))
    assert "below sample threshold" in line


def test_bug8_validator_drops_a_headline_built_on_one_video(willpower_metrics):
    report = {
        "metrics": willpower_metrics,
        "roadmap": {},
        "headline": {"kind": "duration_bucket", "label": "1-5 min", "sample": 1,
                     "value": SHORT_BUCKET_VIEWS},
        "outreach_line": "Ran your channel through something I built...",
    }
    conflicts = validate_report(report)
    assert report["headline"] is None
    assert report["outreach_line"] == ""
    assert any(c.check == "thin_bucket_claim" for c in conflicts)


def test_bug8_floor_is_configurable(willpower_metrics):
    report = {
        "metrics": willpower_metrics, "roadmap": {},
        "headline": {"kind": "duration_bucket", "label": "1-5 min", "sample": 1, "value": 1},
    }
    validate_report(report, rules=ReportRules(min_bucket_sample=1))
    assert report["headline"] is not None, "n=1 is acceptable when the floor says so"


# ── Cross-cutting ────────────────────────────────────────────────────────────


def test_clean_report_reports_no_conflicts(willpower_metrics):
    cadence = compute_cadence(willpower_metrics, willpower_metrics["upload_timing"])
    report = {
        "metrics": willpower_metrics,
        "headline": pick_headline_metric(willpower_metrics),
        "roadmap": {"cadence": cadence.label, "weeks": []},
    }
    assert validate_report(report, cadence, willpower_metrics["flagged_videos"]) == []


def test_rules_are_shipped_to_the_dashboard(willpower_metrics):
    """The UI must read the floors, not keep its own copy."""
    assert willpower_metrics["rules"]["min_bucket_sample"] == DEFAULT_RULES.min_bucket_sample
    assert willpower_metrics["rules"]["min_slot_sample"] == DEFAULT_RULES.min_slot_sample


# ── Prompt wiring: the models are actually told, not just handed an argument ──


def _capture_prompt(monkeypatch, module):
    """Run an LLM-calling coroutine without an LLM, keeping the rendered prompt."""
    seen: dict = {}

    async def _fake(llm, prompt, schema, **kw):
        seen["prompt"] = prompt
        return schema()

    monkeypatch.setattr(module, "call_llm_with_retry", _fake)
    monkeypatch.setattr(module, "_build_analysis_llm_and_chain", lambda: (None, [], "stub"))
    return seen


def test_bug5_cadence_reaches_the_audit_prompt(monkeypatch):
    import asyncio

    import app.services.youtube_ai_analysis as mod

    seen = _capture_prompt(monkeypatch, mod)
    cadence = Cadence(1, 1.0, "1 video/week (3-4 releases/month)", ("Saturday",))
    asyncio.run(mod.analyze_strategy("ctx", "web", "all_time", "BASE", cadence=cadence))

    assert cadence.label in seen["prompt"]
    assert "CADENCE IS ALREADY COMPUTED" in seen["prompt"]
    assert "BASE" in seen["prompt"], "existing directives are preserved"


def test_bug4_flagged_videos_reach_the_roadmap_prompt(monkeypatch, willpower_metrics):
    import asyncio

    import app.services.youtube_ai_analysis as mod

    seen = _capture_prompt(monkeypatch, mod)
    cadence = Cadence(1, 1.0, "1 video/week (3-4 releases/month)", ("Saturday",))
    result = asyncio.run(mod.generate_roadmap(
        "ctx", "web", weeks=4, cadence=cadence,
        flagged_videos=willpower_metrics["flagged_videos"],
    ))

    assert MESSI_VIDEO in seen["prompt"]
    assert "DO NOT CITE AS POSITIVE EVIDENCE" in seen["prompt"]
    # The cadence the report shows is authored here, not read back from the model.
    assert result["cadence"] == cadence.label


def test_bug1_window_subcount_is_stated_separately(willpower_timing):
    """The day count must not be presented as the window count.

    "9 of top 10 went out on Sat & Tue, 09:00-12:00 UTC" asserts all nine were in
    the window. Only the ones in ``window_proof_count`` were.
    """
    win = willpower_timing["best_window"]
    proof = win["top_video_proof"]
    assert f"{win['proof_count']} of top {win['top_tier_count']}" in proof
    if win["best_time_slot"]:
        assert f"{win['window_proof_count']} of those" in proof
        assert win["window_proof_count"] <= win["proof_count"]


# ── BUG 9 — narrative that contradicts the tables printed beside it ──────────
# The fallback-model audit that prompted the strict cascade said two things the
# same document disproved: it recommended the channel's worst weekdays, and it
# called short-form "unexplored" for a channel with eight shorts published.
# Everything below is checked against the computed numbers, on every tier.


@pytest.fixture
def willpower_with_shorts(willpower_metrics):
    """The fixture metrics, plus the eight shorts the real channel had.

    The synthetic catalogue's shortest video is 200s, so it produces no Shorts
    bucket at all — and "unexplored" would be *true*. The incident's whole point
    is a non-empty bucket called empty, so the bucket has to exist to test it.
    """
    willpower_metrics["buckets"]["Shorts (<=1m)"] = {
        "count": 8,
        "avg_views": 120_000,
        "median_views": 90_000,
        "total_views": 960_000,
    }
    return willpower_metrics


def test_bug9_recommending_the_worst_weekdays_is_caught(willpower_with_shorts):
    """The shipped claim, verbatim in shape: the four weakest days recommended."""
    audit = {
        "priorities": [
            "Shift the publishing schedule to Wednesday, Friday, Monday and Thursday."
        ]
    }
    findings = narrative_violations(audit, willpower_with_shorts)

    assert len(findings) == 1
    section, bullet, reason = findings[0]
    assert section == "priorities"
    # Saturday (1.55x) and Tuesday (1.19x) are the computed winners.
    assert "Saturday" in reason and "Tuesday" in reason
    assert "Wednesday" in reason and "Friday" in reason


def test_bug9_describing_a_weak_day_as_weak_is_not_a_violation(willpower_with_shorts):
    """A day name is not a recommendation.

    "Wednesday underperforms" names the worst day precisely in order to advise
    against it. Flagging that would invert the check.
    """
    audit = {
        "underperforming": [
            "Wednesday and Friday uploads underperform; avoid posting then.",
            "Avoid scheduling anything on Monday.",
        ]
    }
    assert narrative_violations(audit, willpower_with_shorts) == []


def test_bug9_recommending_the_computed_winners_passes(willpower_with_shorts):
    audit = {
        "priorities": ["Publish on Saturday, with Tuesday as the secondary slot."],
        "whats_working": ["Saturday uploads at 10:30 carry the channel."],
    }
    assert narrative_violations(audit, willpower_with_shorts) == []


def test_bug9_absence_claim_about_a_populated_bucket_is_caught(willpower_with_shorts):
    """The other shipped claim: "hasn't been explored" over eight videos."""
    audit = {"format_insights": ["Short-form hasn't been explored yet — a clear opening."]}
    findings = narrative_violations(audit, willpower_with_shorts)

    assert len(findings) == 1
    _section, _bullet, reason = findings[0]
    assert "Shorts (<=1m)" in reason
    assert "8 videos" in reason


@pytest.mark.parametrize(
    "claim",
    [
        "Short-form hasn't been explored yet.",
        "There is no content in this category for shorts.",
        "Shorts remain untapped for this channel.",
        "Short-form is underutilized.",
        "The channel has yet to try short-form video.",
    ],
    ids=["hasnt-explored", "no-content", "untapped", "underutilized", "yet-to-try"],
)
def test_bug9_absence_phrasings_are_all_caught(willpower_with_shorts, claim):
    """The model does not reuse one wording, so one pattern is not enough."""
    findings = narrative_violations({"format_insights": [claim]}, willpower_with_shorts)
    assert findings, f"missed absence claim: {claim!r}"


def test_bug9_absence_claim_about_a_genuinely_empty_bucket_survives(willpower_metrics):
    """The check must not fire when the claim is simply true.

    The fixture catalogue has no video under a minute, so this is accurate
    reporting and has to reach the reader intact.
    """
    assert "Shorts (<=1m)" not in willpower_metrics["buckets"]
    audit = {"format_insights": ["Short-form hasn't been explored yet."]}
    assert narrative_violations(audit, willpower_metrics) == []


def test_bug9_every_narrative_section_is_checked(willpower_with_shorts):
    """A contradiction is no more acceptable in one section than another."""
    for section in NARRATIVE_SECTIONS:
        audit = {section: ["Move the schedule to Wednesday and Friday."]}
        assert narrative_violations(audit, willpower_with_shorts), (
            f"{section} was not checked"
        )


def test_bug9_validate_report_drops_the_contradicted_bullets(willpower_with_shorts):
    """The last gate strips what survived regeneration, and records why."""
    report = {
        "metrics": willpower_with_shorts,
        "roadmap": {},
        "headline": None,
        "audit": {
            "priorities": [
                "Shift the publishing schedule to Wednesday and Friday.",
                "Keep the Saturday slot; it is the strongest day.",
            ],
            "format_insights": ["Short-form hasn't been explored yet."],
        },
    }

    conflicts = validate_report(report)

    audit = report["audit"]
    assert audit["priorities"] == ["Keep the Saturday slot; it is the strongest day."]
    assert audit["format_insights"] == []
    checks = [c.check for c in conflicts]
    assert checks.count("narrative_contradicts_data") == 2


def test_bug9_a_clean_audit_passes_validate_report_untouched(willpower_with_shorts):
    report = {
        "metrics": willpower_with_shorts,
        "roadmap": {},
        "headline": None,
        "audit": {
            "priorities": ["Publish on Saturday, with Tuesday as the secondary slot."],
            "format_insights": ["The 8 shorts published so far average 120,000 views."],
        },
    }
    before = {k: list(v) for k, v in report["audit"].items()}

    conflicts = validate_report(report)

    assert report["audit"] == before
    assert not [c for c in conflicts if c.check == "narrative_contradicts_data"]


def test_bug9_unrankable_days_produce_no_claim(willpower_metrics):
    """With no day clearing the sample floor, a day claim cannot be judged.

    An unverifiable claim is not a false one, and inventing a violation would be
    the same category of error the checks exist to prevent.
    """
    timing = willpower_metrics["upload_timing"]
    for day in timing["days"]:
        day["video_count"] = 1
    timing["best_window"]["best_days"] = []

    audit = {"priorities": ["Move the schedule to Wednesday and Friday."]}
    assert narrative_violations(audit, willpower_metrics) == []


# ── FIX 2 — Roadmap justifications must not cite raw external metrics ────────

@pytest.mark.parametrize(
    "text,expected_match",
    [
        ("CUDA cutlass trended on GitHub (9 stars/day)", True),
        ("Product Hunt's God's Eye View went viral last week", True),
        ("Received 150 upvotes on launch day", True),
        ("350 stars on the open source release", True),
        ("Extends the proven 1.03M view discipline documentary format.", False),
        ("Anchored to top performer Discipline Deep Dive 0 (1.5M views).", False),
    ],
)
def test_mentions_external_metric(text, expected_match):
    assert mentions_external_metric(text) is expected_match


def test_strip_external_metric_phrases_removes_offending_clauses():
    raw = (
        "CUDA cutlass trended on GitHub (9 stars/day), while discipline documentaries "
        "consistently average 1.03M views."
    )
    cleaned = strip_external_metric_phrases(raw)
    assert not mentions_external_metric(cleaned)
    assert "discipline documentaries" in cleaned
    assert "1.03M" in cleaned


def test_strip_external_metric_phrases_drops_fully_dirty_rationale():
    raw = "Product Hunt's God's Eye View went viral with 450 upvotes."
    cleaned = strip_external_metric_phrases(raw)
    assert cleaned == ""


def test_validate_report_strips_external_metrics_from_roadmap():
    report = {
        "metrics": {"upload_timing": {"best_window": {}, "days": []}},
        "audit": {},
        "headline": None,
        "roadmap": {
            "weeks": [
                {
                    "items": [
                        {
                            "title": "CUDA Optimization Deep Dive",
                            "rationale": "CUDA cutlass trended on GitHub (9 stars/day), extending the 1.03M documentary format.",
                        },
                        {
                            "title": "Product Hunt Teardown",
                            "rationale": "Went viral on Product Hunt with 300 upvotes.",
                        },
                        {
                            "title": "Clean Discipline System",
                            "rationale": "Anchors directly to Discipline Deep Dive 0 (1.5M views).",
                        },
                    ]
                }
            ]
        },
    }

    conflicts = validate_report(report)
    items = report["roadmap"]["weeks"][0]["items"]

    assert not mentions_external_metric(items[0]["rationale"])
    assert "extending the 1.03M documentary format" in items[0]["rationale"]
    assert items[1]["rationale"] == ""
    assert items[2]["rationale"] == "Anchors directly to Discipline Deep Dive 0 (1.5M views)."

    conflict_checks = [c.check for c in conflicts]
    assert conflict_checks.count("external_metric_violation") == 2

