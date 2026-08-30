"""The LLM contract.

Everything the model is allowed to return, and nothing else. Three rules govern
these shapes:

* **Closed enums wherever a wrong value is dangerous.** ``intent`` and ``verb``
  are ``Literal``s, so a hallucinated value fails validation inside
  ``call_llm_with_retry`` — which treats a ValidationError as non-transient and
  re-prompts the same tier rather than falling through the cascade. That is the
  repair loop doing its job.
* **Server-side filtering wherever a wrong value is merely imprecise.**
  ``platforms`` and ``statuses`` are plain ``list[str]`` and are intersected
  against the real vocabularies in ``context.py``, dropping unknowns with a
  warning. "youtube video" degrading to "all platforms" is a slightly broad
  answer; raising would 502 a perfectly answerable question.
* **Exactly one field carries natural language:** ``AssistantAnswer.answer_markdown``.

Everything here subclasses ``CoercingBaseModel`` so a weak tier answering
``[{"platform": "youtube"}]`` where ``list[str]`` was expected gets repaired
rather than rejected.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import field_validator

from app.services.blog_pipeline.utils import CoercingBaseModel

Intent = Literal[
    "daily_digest",
    "schedule_lookup",
    "review_queue",
    "backlog",
    "overdue",
    "analytics",
    "item_lookup",
    "action_request",
    "smalltalk",
    "unknown",
]

ActionVerb = Literal[
    "mark_published",
    "reschedule",
    "generate_content",
    "approve_draft",
    "reject_draft",
]

REVIEW_VERBS = frozenset({"approve_draft", "reject_draft"})


class QueryPlan(CoercingBaseModel):
    """What the user is asking for, in machine terms. LLM call #1's output."""

    intent: Intent = "unknown"
    # The phrase the model matched, verbatim ("aaj", "is hafte"). Echoed back to
    # the user so a mis-parse is visible rather than silent.
    date_expression: str = ""
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    platforms: list[str] = []
    statuses: list[str] = []
    # Free text, matched server-side with ILIKE — never interpreted by the LLM.
    # The one field legitimately allowed to be Hinglish, because the topics it
    # matches may themselves be romanized.
    search_terms: list[str] = []
    needs_analytics: bool = False
    language: Literal["en", "hinglish"] = "en"

    @field_validator("date_expression", mode="before")
    @classmethod
    def _null_expression_is_blank(cls, v):
        """A JSON ``null`` here must not sink the whole plan.

        ``CoercingBaseModel`` repairs ``list[str]`` fields only, so an explicit
        null for this plain ``str`` is a hard ValidationError — and a
        ValidationError is treated as non-transient, spending the cascade on
        re-prompts and landing on the daily-digest fallback. The overdue intent
        is told to send no dates, and weak tiers read that as
        ``"date_expression": null`` too, so "what's overdue" would answer with
        today's schedule: the very bug this field exists to make visible.
        """
        return "" if v is None else v

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def _iso_date_only(cls, v):
        """Reject anything that is not a real ISO date.

        Load-bearing, and easy to assume is unnecessary: ``CoercingBaseModel``
        only repairs ``list[str]`` fields, so without this a model answering
        ``"date_from": "kal"`` would pass validation, reach
        ``IsoDate.process_bind_param`` and raise a bare ValueError from inside
        the query layer — a 500 instead of a retry.
        """
        if v in (None, "", "null", "None"):
            return None
        s = str(v).strip()[:10]
        date.fromisoformat(s)  # ValueError -> schema repair retry
        return s


class ProposedAction(CoercingBaseModel):
    """A write the model suggests. Never executed on the turn it is proposed.

    Nothing here is trusted. ``item_id``/``content_id`` are checked for
    membership in the context pack and then re-read from the database
    owner-scoped; ``label`` is discarded and rebuilt server-side.
    """

    verb: ActionVerb
    item_id: str = ""
    # Required for the two review verbs, forbidden for the other three — the
    # pairing is enforced by a CHECK constraint on assistant_actions.
    content_id: Optional[str] = None
    label: str = ""
    scheduled_date: Optional[str] = None
    event_time: Optional[str] = None
    content_type: Optional[Literal["linkedin", "blog", "youtube_script"]] = None
    # Only honoured when the user explicitly asked to regenerate; costs a run.
    regenerate: bool = False

    @field_validator("scheduled_date", mode="before")
    @classmethod
    def _iso_date_only(cls, v):
        if v in (None, "", "null", "None"):
            return None
        s = str(v).strip()[:10]
        date.fromisoformat(s)
        return s


class AssistantAnswer(CoercingBaseModel):
    """LLM call #2's output: the prose, plus anything it wants to propose."""

    answer_markdown: str
    proposed_actions: list[ProposedAction] = []
    # Advisory only. The frontend renders source chips from the server's own
    # pack, so a fabricated citation here simply never reaches the UI.
    cited_item_ids: list[str] = []
