"""End-to-end wiring of generate_prospect_report, with the two LLM calls stubbed.

The per-bug suite proves each rule in isolation. This proves the orchestration
actually applies them: that the audit is told the cadence, that the roadmap is
handed the flagged videos, that an item citing one triggers regeneration and is
stripped if the model keeps doing it, and that the validator runs before the
report dict is returned — upstream of persistence, cache, web view and PDF.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.services import youtube_prospect_service as svc
from conftest import MESSI_VIDEO

CHANNEL = {"title": "WillPower Star", "handle": "@willpowerstar", "channel_id": "UC123",
           "subscriber_count": 2_400_000}


class _Recorder:
    """Captures what the orchestration passed to each model call."""

    def __init__(self, roadmap_items):
        self.audit_calls: list[dict] = []
        self.roadmap_calls: list[dict] = []
        self._roadmap_items = list(roadmap_items)

    async def analyze_strategy(self, context, web_context, time_range="", directives="",
                               cadence=None, time_of_day_allowed=True):
        self.audit_calls.append({
            "directives": directives, "cadence": cadence, "context": context,
            "time_of_day_allowed": time_of_day_allowed,
        })
        return {
            "verdict": "ok",
            "whats_working": ["Long-form discipline documentaries"],
            "underperforming": ["Abstract theory framings"],
            "format_insights": ["Ship 3 videos per week"],  # contradicts the cadence
            "content_gaps": ["Applied routines"],
            "priorities": ["Pivot away from abstract theory"],
            "model": "stub",
        }

    async def generate_roadmap(self, context, web_context, weeks=4, directives="",
                               audit_strategy=None, upload_timing=None, cadence=None,
                               flagged_videos=None, violation_note="",
                               time_of_day_allowed=None):
        self.roadmap_calls.append({
            "cadence": cadence, "flagged_videos": flagged_videos,
            "violation_note": violation_note, "audit_strategy": audit_strategy,
            "time_of_day_allowed": time_of_day_allowed,
        })
        items = self._roadmap_items.pop(0) if self._roadmap_items else []
        return {
            "cadence": cadence.label,
            "weeks": [{"focus": f"Week {i+1}", "items": list(items)} for i in range(weeks)],
            "model": "stub",
        }


@pytest.fixture
def run_report(monkeypatch, willpower_videos):
    def _run(roadmap_items):
        rec = _Recorder(roadmap_items)

        class _Stub:
            analyze_strategy = staticmethod(rec.analyze_strategy)
            generate_roadmap = staticmethod(rec.generate_roadmap)

        import app.services.youtube_ai_analysis as real
        monkeypatch.setattr(real, "analyze_strategy", rec.analyze_strategy)
        monkeypatch.setattr(real, "generate_roadmap", rec.generate_roadmap)
        monkeypatch.setattr(
            "app.services.youtube_competitor.search_youtube_channels_direct",
            lambda *a, **k: [],
        )
        report = asyncio.run(
            svc.generate_prospect_report(dict(CHANNEL), willpower_videos, True, 4, "")
        )
        return report, rec

    return _run


CLEAN_ITEM = [{"title": "The 5AM Discipline Teardown", "format": "deep-dive",
               "theme": "Applied routines", "rationale": "Extends the winning documentary format."}]
DIRTY_ITEM = [{"title": "The Neuroscience of Elite Genius", "format": "deep-dive",
               "theme": "Brain research",
               "rationale": "Builds on the high-engagement Messi brain research pillar."}]


def test_audit_and_roadmap_get_the_same_cadence_object(run_report):
    """The orchestration hands one Cadence to both models and to the payload."""
    report, rec = run_report([CLEAN_ITEM])
    audit_cadence = rec.audit_calls[0]["cadence"]
    roadmap_cadence = rec.roadmap_calls[0]["cadence"]

    assert audit_cadence is not None
    assert audit_cadence is roadmap_cadence, "one object, not two derivations"
    assert report["cadence"]["label"] == audit_cadence.label
    assert report["roadmap"]["cadence"] == audit_cadence.label


def test_roadmap_receives_the_flagged_videos_as_data(run_report):
    _report, rec = run_report([CLEAN_ITEM])
    titles = [v["title"] for v in rec.roadmap_calls[0]["flagged_videos"]]
    assert MESSI_VIDEO in titles


def test_contradicting_audit_cadence_bullet_is_stripped(run_report):
    report, _rec = run_report([CLEAN_ITEM])
    assert "Ship 3 videos per week" not in report["audit"]["format_insights"]
    assert any(c["check"] == "cadence_conflict" for c in report["integrity"]["conflicts"])


def test_citing_a_flagged_video_triggers_regeneration(run_report):
    """First attempt cites the Messi video; the retry does not."""
    report, rec = run_report([DIRTY_ITEM, CLEAN_ITEM])

    assert len(rec.roadmap_calls) == 2, "one regeneration"
    assert "PREVIOUS ATTEMPT VIOLATED" in rec.roadmap_calls[1]["violation_note"]
    assert MESSI_VIDEO in rec.roadmap_calls[1]["violation_note"]
    item = report["roadmap"]["weeks"][0]["items"][0]
    assert item["title"] == "The 5AM Discipline Teardown"
    assert item["rationale"], "a clean item keeps its justification"


def test_persistent_offender_is_stripped_not_looped(run_report):
    """A model that keeps citing the flagged video is bounded, then sanitised."""
    report, rec = run_report([DIRTY_ITEM, DIRTY_ITEM, DIRTY_ITEM, DIRTY_ITEM])

    assert len(rec.roadmap_calls) == 1 + svc.DEFAULT_RULES.max_item_regens
    for week in report["roadmap"]["weeks"]:
        for item in week["items"]:
            assert item["rationale"] == "", "the citation never reaches render"
    assert any(c["check"] == "cites_flagged_video" for c in report["integrity"]["conflicts"])


def test_report_carries_its_own_integrity_record(run_report):
    report, _rec = run_report([CLEAN_ITEM])
    assert "integrity" in report and "checked_at" in report["integrity"]
    assert isinstance(report["integrity"]["conflicts"], list)


def test_every_roadmap_date_matches_the_publishing_days(run_report):
    report, _rec = run_report([CLEAN_ITEM])
    allowed = set(report["cadence"]["publish_days"])
    assert allowed, "the fixture has a confident best day"
    for week in report["roadmap"]["weeks"]:
        for item in week["items"]:
            if item.get("date"):
                assert date.fromisoformat(item["date"]).strftime("%A") in allowed


def test_item_count_matches_the_stated_cadence(run_report):
    report, _rec = run_report([CLEAN_ITEM])
    per_week = report["cadence"]["items_per_week"]
    for week in report["roadmap"]["weeks"]:
        assert len(week["items"]) <= per_week
    assert report["roadmap"]["cadence"] == report["cadence"]["label"]


EXTERNAL_METRIC_ITEM = [
    {
        "title": "CUDA Kernel Optimizer",
        "format": "deep-dive",
        "theme": "CUDA Development",
        "rationale": "CUDA cutlass trended on GitHub (9 stars/day), while discipline documentaries avg 1.03M views.",
    }
]


def test_external_metrics_in_roadmap_triggers_regeneration(run_report):
    """First attempt cites GitHub stars/day; retry fixes it to clean justification."""
    report, rec = run_report([EXTERNAL_METRIC_ITEM, CLEAN_ITEM])

    assert len(rec.roadmap_calls) == 2, "one regeneration pass triggered"
    assert "PREVIOUS ATTEMPT VIOLATED" in rec.roadmap_calls[1]["violation_note"]
    assert "raw external metrics" in rec.roadmap_calls[1]["violation_note"]
    item = report["roadmap"]["weeks"][0]["items"][0]
    assert item["title"] == "The 5AM Discipline Teardown"
    assert "Extends the winning documentary format." in item["rationale"]


def test_persistent_external_metrics_offender_is_stripped_by_validator(run_report):
    """A model that repeatedly outputs raw external metrics has offending clauses stripped."""
    report, rec = run_report([EXTERNAL_METRIC_ITEM, EXTERNAL_METRIC_ITEM])

    assert len(rec.roadmap_calls) == 2
    item = report["roadmap"]["weeks"][0]["items"][0]
    assert not any(bad in item["rationale"].lower() for bad in ("stars", "github", "/day"))
    assert "discipline documentaries avg 1.03M views" in item["rationale"]
    assert any(c["check"] == "external_metric_violation" for c in report["integrity"]["conflicts"])

