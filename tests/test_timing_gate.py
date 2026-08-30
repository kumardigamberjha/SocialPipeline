"""BUG 10 — one report, two answers about the time of day.

The shipped audit for WillPower Star said both of these, three inches apart:

    page 2, Optimal Upload Timing & Day Velocity
        "Not enough uploads carry a publish time to recommend a time of day"
        window: —

    page 1, Format & Cadence / Strategic Priorities
        "Saturday & Sunday between 09:00–12:00 UTC (2.27× channel median)"

Neither section was wrong about the data it had. Nothing compared them: the
widget consulted the sufficiency check, and the narrative model was handed the
raw hour buckets with no instruction attached and wrote a window out of them.

There is now one gate — ``time_of_day_recommendation_allowed`` — and four
defences behind it: the prompt context withholds the hour buckets, both models
are told the constraint, a violating audit is regenerated once, and anything
that survives is stripped before render. The day-of-week finding (Saturday
2.98×) is valid and must come through all four untouched.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services import youtube_prospect_service as svc
from app.services.youtube_metrics import (
    analyze_upload_timing,
    time_of_day_recommendation_allowed,
    timing_allows_time_of_day,
)
from app.services.youtube_prospect_service import build_prospect_context
from app.services.youtube_report_rules import (
    TIME_CLAIM_SECTIONS,
    Cadence,
    ReportRules,
    check_time_of_day_claims,
    mentions_time_of_day,
    narrative_violations,
    strip_time_of_day_phrases,
    validate_report,
)
from conftest import DATEONLY_MEDIAN, SATURDAY_MULTIPLIER

CHANNEL = {"title": "WillPower Star", "handle": "@willpowerstar", "channel_id": "UC123",
           "subscriber_count": 2_400_000}

#: The claim as it shipped, in both sections that carried it.
SHIPPED_WINDOW_BULLET = (
    "Publish on Saturday & Sunday between 09:00–12:00 UTC "
    "(2.27× channel median) to catch the weekend audience."
)


def _prose(report: dict) -> list[str]:
    """Every string a reader sees, from both pages of the rendered report."""
    out: list[str] = []
    audit = report.get("audit") or {}
    for section in TIME_CLAIM_SECTIONS:
        value = audit.get(section)
        out += [value] if isinstance(value, str) else [str(b) for b in (value or [])]
    win = (report["metrics"].get("upload_timing") or {}).get("best_window") or {}
    out += [str(win.get(k) or "") for k in ("recommendation", "combined_label", "top_video_proof")]
    for week in (report.get("roadmap") or {}).get("weeks") or []:
        out.append(str(week.get("focus") or ""))
        for item in week.get("items") or []:
            # Titles are excluded on purpose — see ROADMAP_PROSE_FIELDS.
            out.append(str(item.get("rationale") or ""))
    return [t for t in out if t]


# ── The gate itself ──────────────────────────────────────────────────────────


def test_gate_is_closed_when_no_upload_carries_a_time(dateonly_videos):
    """A date-only feed normalises to midnight. That is missing data, not 00:00."""
    assert time_of_day_recommendation_allowed(dateonly_videos) is False


def test_gate_is_open_for_a_catalogue_with_real_timestamps(willpower_videos):
    assert time_of_day_recommendation_allowed(willpower_videos) is True


def test_gate_needs_enough_timestamps_overall(willpower_videos):
    """Floor one: the catalogue must carry ``min_clock_sample`` publish times."""
    rules = ReportRules(min_clock_sample=len(willpower_videos) + 1)
    assert time_of_day_recommendation_allowed(willpower_videos, rules) is False


def test_gate_needs_enough_uploads_in_the_winning_bucket(willpower_videos):
    """Floor two: timestamps spread across eight windows support none of them."""
    rules = ReportRules(min_slot_sample=50)
    assert time_of_day_recommendation_allowed(willpower_videos, rules) is False


def test_both_floors_are_configurable(willpower_videos):
    assert time_of_day_recommendation_allowed(
        willpower_videos, ReportRules(min_clock_sample=1, min_slot_sample=1)
    ) is True


def test_the_timing_analysis_records_the_gates_verdict(dateonly_timing, willpower_timing):
    """Computed once, read everywhere — no surface re-derives it."""
    assert dateonly_timing["time_of_day_allowed"] is False
    assert dateonly_timing["has_hour_data"] is False
    assert timing_allows_time_of_day(dateonly_timing) is False

    assert willpower_timing["time_of_day_allowed"] is True
    assert timing_allows_time_of_day(willpower_timing) is True


def test_a_validator_drop_closes_the_gate_too(willpower_metrics):
    """A window that fails its evidence check must silence the prose as well."""
    report = {"metrics": willpower_metrics, "roadmap": {}, "headline": None}
    timing = report["metrics"]["upload_timing"]
    for v in timing["evidence_videos"]:
        v["in_best_window"] = False

    validate_report(report)

    assert timing["time_of_day_allowed"] is False
    assert timing_allows_time_of_day(timing) is False
    assert timing["has_hour_data"] is True, "the breakdown table still has data to show"


# ── The day finding is untouched ─────────────────────────────────────────────


def test_the_day_recommendation_survives_the_closed_gate(dateonly_timing):
    win = dateonly_timing["best_window"]
    assert win["best_days"] == ["Saturday", "Sunday"]
    assert win["day_confident"] is True
    assert win["day_multiplier"] == SATURDAY_MULTIPLIER
    assert win["best_time_slot"] is None
    assert win["slot_multiplier"] is None


def test_page_two_states_the_day_and_declines_the_hour(dateonly_timing):
    """The widget copy, verbatim: a day, a lift, and no clock."""
    win = dateonly_timing["best_window"]
    assert "Saturday & Sunday" in win["recommendation"]
    assert "Not enough uploads carry a publish time" in win["recommendation"]
    assert win["combined_label"] == "Saturday & Sunday"
    assert not mentions_time_of_day(win["recommendation"])
    assert not mentions_time_of_day(win["combined_label"])


def test_a_thin_slot_floor_does_not_disturb_the_day_floor(dateonly_videos):
    """Day-of-week runs on its own, less strict gate and is unaffected."""
    timing = analyze_upload_timing(
        dateonly_videos, DATEONLY_MEDIAN, rules=ReportRules(min_clock_sample=99)
    )
    assert timing["best_window"]["best_days"] == ["Saturday", "Sunday"]
    assert timing["best_window"]["day_confident"] is True


# ── The prompt layer ─────────────────────────────────────────────────────────


def test_context_withholds_the_hour_buckets_and_says_why(dateonly_metrics):
    """The model cannot invent a window out of buckets it was never shown."""
    ctx = build_prospect_context(CHANNEL, dateonly_metrics)
    assert "Time-of-Day Breakdown" not in ctx
    assert "Time of day: NOT AVAILABLE" in ctx
    assert "never a UTC window" in ctx
    assert "Day Breakdown" in ctx, "the day evidence still ships"
    assert "Sat: 2.98×" in ctx


def test_context_still_ships_the_hour_buckets_when_the_gate_is_open(willpower_metrics):
    ctx = build_prospect_context(CHANNEL, willpower_metrics)
    assert "Time-of-Day Breakdown" in ctx
    assert "Time of day: NOT AVAILABLE" not in ctx


def _capture_prompt(monkeypatch, module):
    seen: dict = {}

    async def _fake(llm, prompt, schema, **kw):
        seen["prompt"] = prompt
        return schema()

    monkeypatch.setattr(module, "call_llm_with_retry", _fake)
    monkeypatch.setattr(module, "_build_analysis_llm_and_chain", lambda: (None, [], "stub"))
    return seen


def test_the_constraint_reaches_the_audit_prompt(monkeypatch):
    import app.services.youtube_ai_analysis as mod

    seen = _capture_prompt(monkeypatch, mod)
    asyncio.run(mod.analyze_strategy("ctx", "web", "public_snapshot", "BASE",
                                     time_of_day_allowed=False))

    assert "TIME OF DAY IS NOT AVAILABLE FOR THIS CHANNEL" in seen["prompt"]
    assert "DAYS OF THE WEEK" in seen["prompt"]
    assert "BASE" in seen["prompt"], "existing directives are preserved"


def test_the_constraint_reaches_the_roadmap_prompt(monkeypatch, dateonly_metrics):
    """Scheduling notes are prose too, and default to the gate they were given."""
    import app.services.youtube_ai_analysis as mod

    seen = _capture_prompt(monkeypatch, mod)
    cadence = Cadence(1, 1.6, "1 video/week (3-4 releases/month)", ("Saturday",))
    asyncio.run(mod.generate_roadmap(
        "ctx", "web", weeks=4, cadence=cadence,
        upload_timing=dateonly_metrics["upload_timing"],
    ))

    assert "TIME OF DAY IS NOT AVAILABLE FOR THIS CHANNEL" in seen["prompt"]


def test_an_open_gate_asks_for_the_computed_window_instead(monkeypatch, willpower_metrics):
    import app.services.youtube_ai_analysis as mod

    seen = _capture_prompt(monkeypatch, mod)
    asyncio.run(mod.analyze_strategy("ctx", "web", "public_snapshot", "BASE",
                                     time_of_day_allowed=True))

    assert "TIME OF DAY IS NOT AVAILABLE" not in seen["prompt"]
    assert "name that window and no other" in seen["prompt"]


# ── Detection ────────────────────────────────────────────────────────────────


def test_the_shipped_bullet_is_a_violation(dateonly_metrics):
    audit = {"format_insights": [SHIPPED_WINDOW_BULLET], "priorities": [SHIPPED_WINDOW_BULLET]}
    findings = check_time_of_day_claims(audit, dateonly_metrics["upload_timing"])

    assert {section for section, _b, _r in findings} == {"format_insights", "priorities"}
    assert all("too few uploads carry a publish time" in r for _s, _b, r in findings)


def test_every_prose_field_is_scanned(dateonly_metrics):
    """A contradiction is no more acceptable in the verdict than in a priority."""
    for section in TIME_CLAIM_SECTIONS:
        audit = {section: SHIPPED_WINDOW_BULLET if section == "verdict"
                 else [SHIPPED_WINDOW_BULLET]}
        assert check_time_of_day_claims(audit, dateonly_metrics["upload_timing"]), (
            f"{section} was not scanned"
        )


def test_an_open_gate_permits_the_window(willpower_metrics):
    """The check exists to enforce the gate, not to ban clocks outright."""
    audit = {"format_insights": ["Saturday uploads at 10:30 UTC carry the channel."]}
    assert check_time_of_day_claims(audit, willpower_metrics["upload_timing"]) == []


@pytest.mark.parametrize(
    "text",
    [
        "Publish on Saturday & Sunday between 09:00–12:00 UTC.",
        "Post at 9am on Saturdays.",
        "Your 15:00-18:00 UTC uploads outperform.",
        "Aim for a 5 p.m. release.",
        "Shift the drop to 10:30.",
    ],
    ids=["utc-range", "meridiem", "slot-label", "dotted-meridiem", "bare-clock"],
)
def test_hour_phrasings_are_all_caught(text):
    assert mentions_time_of_day(text), f"missed hour claim: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "Publish on Saturday & Sunday — 2.98× the channel median.",
        "Double down on 15-30 min deep dives.",
        "Move to an 8-10 day publishing loop with 3-4 releases per month.",
        "Your 30+ min documentaries carry 2.27x the median.",
        "The 1-5 min bucket is a single video and proves nothing.",
    ],
    ids=["day-claim", "length", "cadence", "long-form", "thin-bucket"],
)
def test_days_lengths_and_cadences_are_not_hour_claims(text):
    assert not mentions_time_of_day(text), f"false positive: {text!r}"


# ── Repair ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "before,after",
    [
        (SHIPPED_WINDOW_BULLET,
         "Publish on Saturday & Sunday to catch the weekend audience."),
        ("Publish on Saturday & Sunday between 09:00–12:00 UTC (2.27× channel median).",
         "Publish on Saturday & Sunday."),
        ("Post at 9am on Saturdays.", "Post on Saturdays."),
        ("Lock a weekly Saturday release. Publish between 09:00 and 12:00 UTC for the lift.",
         "Lock a weekly Saturday release."),
        ("Your Saturday uploads average 2.98× the channel median.",
         "Your Saturday uploads average 2.98× the channel median."),
    ],
    ids=["shipped", "with-figure", "meridiem", "second-sentence", "untouched"],
)
def test_stripping_removes_the_clock_and_keeps_the_day(before, after):
    """Clause surgery, not deletion: the day finding is the part worth keeping."""
    assert strip_time_of_day_phrases(before) == after


def test_a_bullet_that_is_only_an_hour_claim_is_dropped():
    assert strip_time_of_day_phrases("Your best window is 09:00–12:00 UTC.") == ""


# ── The validator: nothing reaches render ────────────────────────────────────


def test_validate_report_strips_the_hour_and_keeps_the_day(dateonly_metrics):
    report = {
        "metrics": dateonly_metrics,
        "headline": None,
        "roadmap": {"weeks": [{
            "focus": "Weekend documentaries",
            "items": [{"title": "The 5AM Teardown",   # a topic, not a schedule
                       "rationale": "Ship it Saturday at 10:00 UTC to ride the peak."}],
        }]},
        "audit": {
            "verdict": "Strong weekend channel. Publish Saturday & Sunday at 09:00 UTC.",
            "format_insights": [SHIPPED_WINDOW_BULLET],
            "priorities": [SHIPPED_WINDOW_BULLET, "Cut the abstract theory framings."],
        },
    }

    conflicts = validate_report(report)

    assert not any(mentions_time_of_day(t) for t in _prose(report))
    assert "Saturday & Sunday" in report["audit"]["format_insights"][0]
    assert "Saturday & Sunday" in report["audit"]["priorities"][0]
    assert "Cut the abstract theory framings." in report["audit"]["priorities"]
    assert "Saturday" in report["audit"]["verdict"]
    assert "Saturday" in report["roadmap"]["weeks"][0]["items"][0]["rationale"]
    assert [c.check for c in conflicts].count("time_of_day_not_allowed") == 4


def test_an_open_gate_leaves_the_prose_alone(willpower_metrics):
    """The window this channel earned must not be scrubbed."""
    report = {
        "metrics": willpower_metrics,
        "headline": None,
        "roadmap": {},
        "audit": {"format_insights": ["Saturday uploads at 10:30 UTC carry the channel."]},
    }
    before = list(report["audit"]["format_insights"])

    conflicts = validate_report(report)

    assert report["audit"]["format_insights"] == before
    assert not [c for c in conflicts if c.check == "time_of_day_not_allowed"]


# ── End to end: page 1 and page 2 cannot disagree ────────────────────────────


class _Recorder:
    """A model that writes the shipped window claim, every time it is asked."""

    def __init__(self):
        self.audit_calls: list[dict] = []
        self.roadmap_calls: list[dict] = []

    async def analyze_strategy(self, context, web_context, time_range="", directives="",
                               cadence=None, time_of_day_allowed=True):
        self.audit_calls.append({
            "directives": directives, "context": context,
            "time_of_day_allowed": time_of_day_allowed,
        })
        return {
            "verdict": "Weekend-driven channel with a clear day signal.",
            "whats_working": ["Long-form discipline documentaries"],
            "underperforming": ["Abstract theory framings"],
            "format_insights": [SHIPPED_WINDOW_BULLET],
            "content_gaps": ["Applied routines"],
            "priorities": [SHIPPED_WINDOW_BULLET, "Cut the abstract theory framings."],
            "model": "stub",
        }

    async def generate_roadmap(self, context, web_context, weeks=4, directives="",
                               audit_strategy=None, upload_timing=None, cadence=None,
                               flagged_videos=None, violation_note="",
                               time_of_day_allowed=None):
        self.roadmap_calls.append({
            "cadence": cadence, "time_of_day_allowed": time_of_day_allowed,
            "directives": directives,
        })
        return {
            "cadence": cadence.label,
            "weeks": [{
                "focus": f"Week {i + 1}",
                "items": [{"title": "The 5AM Discipline Teardown", "format": "deep-dive",
                           "theme": "Applied routines",
                           "rationale": "Publish it between 09:00 and 12:00 UTC for the lift."}],
            } for i in range(weeks)],
            "model": "stub",
        }


@pytest.fixture
def dateonly_report(monkeypatch, dateonly_videos):
    rec = _Recorder()
    import app.services.youtube_ai_analysis as real

    monkeypatch.setattr(real, "analyze_strategy", rec.analyze_strategy)
    monkeypatch.setattr(real, "generate_roadmap", rec.generate_roadmap)
    monkeypatch.setattr(
        "app.services.youtube_competitor.search_youtube_channels_direct",
        lambda *a, **k: [],
    )
    report = asyncio.run(
        svc.generate_prospect_report(dict(CHANNEL), dateonly_videos, True, 4, "")
    )
    return report, rec


def test_the_gate_reaches_both_generators(dateonly_report):
    _report, rec = dateonly_report
    assert rec.audit_calls[0]["time_of_day_allowed"] is False
    assert rec.roadmap_calls[0]["time_of_day_allowed"] is False


def test_a_violating_audit_is_regenerated_once_with_the_rule_restated(dateonly_report):
    _report, rec = dateonly_report

    assert len(rec.audit_calls) == 2, "exactly one correction round"
    retry = rec.audit_calls[1]["directives"]
    assert "PREVIOUS ATTEMPT CONTRADICTED THE DATA" in retry
    assert "time-of-day constraint stands and is not negotiable" in retry
    assert "09:00" in retry, "the offending bullet is quoted back"


def test_no_page_of_the_rendered_report_names_an_hour(dateonly_report):
    """The model ignored the constraint twice. The reader still never sees it."""
    report, _rec = dateonly_report
    offenders = [t for t in _prose(report) if mentions_time_of_day(t)]
    assert offenders == []


def test_the_weekend_finding_survives_on_both_pages(dateonly_report):
    report, _rec = dateonly_report
    win = report["metrics"]["upload_timing"]["best_window"]

    # Page 2 — the timing widget.
    assert win["best_days"] == ["Saturday", "Sunday"]
    assert "Saturday & Sunday" in win["recommendation"]

    # Page 1 — the narrative and the priorities.
    page_one = (report["audit"]["format_insights"] + report["audit"]["priorities"])
    assert any("Saturday & Sunday" in b for b in page_one)


def test_page_one_and_page_two_make_the_same_timing_statement(dateonly_report):
    """The whole point: one document, one answer about the time of day."""
    report, _rec = dateonly_report
    timing = report["metrics"]["upload_timing"]
    win = timing["best_window"]

    assert timing_allows_time_of_day(timing) is False
    assert win["best_time_slot"] is None, "page 2 names no window"
    assert not any(mentions_time_of_day(t) for t in _prose(report)), "page 1 names none either"

    named_days = {d for d in win["best_days"]}
    for bullet in report["audit"]["priorities"]:
        if "Saturday" in bullet or "Sunday" in bullet:
            assert {d for d in named_days if d in bullet}, (
                "page 1 recommends days page 2 did not"
            )


def test_the_integrity_record_names_what_was_repaired(dateonly_report):
    report, _rec = dateonly_report
    checks = [c["check"] for c in report["integrity"]["conflicts"]]
    assert "time_of_day_not_allowed" in checks
    detail = next(c for c in report["integrity"]["conflicts"]
                  if c["check"] == "time_of_day_not_allowed")
    assert detail["action_taken"] in {"hour claim stripped", "bullet dropped"}


def test_a_clean_open_gate_report_records_no_timing_conflict(willpower_metrics):
    from app.services.youtube_report_rules import compute_cadence

    cadence = compute_cadence(willpower_metrics, willpower_metrics["upload_timing"])
    report = {
        "metrics": willpower_metrics,
        "headline": None,
        "audit": {"priorities": ["Publish on Saturday, the strongest day."]},
        "roadmap": {"cadence": cadence.label, "weeks": []},
    }
    conflicts = validate_report(report, cadence, willpower_metrics["flagged_videos"])
    assert conflicts == []


def test_pdf_export_contains_no_hours_or_utc_when_timing_gate_is_closed(dateonly_report):
    from app.services.pdf_export_service import build_report_html

    report, _rec = dateonly_report
    html_content = build_report_html(report)

    # Convert HTML to lowercase text for assertion
    import re
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", html_content)

    # Assert no hour window (e.g. 09:00, 12:00, 15:00) or UTC timing phrase appears in the prose
    assert "09:00" not in text
    assert "12:00" not in text
    assert "15:00" not in text
    assert "utc" not in text.lower()
    # And day recommendation appears consistently
    assert "Saturday" in text

