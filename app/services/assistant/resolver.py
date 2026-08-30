"""LLM call #1: question → QueryPlan.

This prompt sees **no user data** — only today's date, the vocabularies, and the
last two turns for pronoun resolution. That is deliberate: the resolver's job is
to choose what to look up, and giving it rows to look at would tempt it to answer
from them instead, which is the failure mode the two-call split exists to avoid.

It never raises. A resolver that times out or exhausts the cascade falls back to
the daily digest for today — a provider outage must not stop "aaj kya hai?" from
working, because that path is pure SQL once the range is known.
"""

from __future__ import annotations

import logging
import time
from datetime import date

from app.config import get_settings
from app.services.assistant.schemas import QueryPlan
from app.services.blog_pipeline.utils import AgentFailedError, call_llm_with_retry

logger = logging.getLogger(__name__)

RESOLVER_TEMPERATURE = 0.1
# Enough for one full cascade fall-through on a ~600-token prompt; the answerer
# gets whatever is left of the shared deadline.
RESOLVER_BUDGET_SECONDS = 22

_SCHEMA_HINT = """{
  "intent": "daily_digest",
  "date_expression": "aaj",
  "date_from": "2026-08-23",
  "date_to": "2026-08-23",
  "platforms": [],
  "statuses": [],
  "search_terms": [],
  "needs_analytics": false,
  "language": "hinglish"
}"""

RESOLVER_PROMPT = """You convert a content creator's question into a database query plan.
You do NOT answer the question. You only decide what to look up.

Today is {today} ({weekday}) in the user's timezone (Asia/Kolkata).

INTENTS (pick exactly one):
- daily_digest    "what should I post today", a general "what's up"
- schedule_lookup a specific day/week/month's scheduled items
- review_queue    drafts waiting to be approved or rejected
- backlog         uncovered/saved topics not yet planned
- overdue         items past their scheduled date and not yet published
                  ("what's overdue", "kya pending hai", "bacha hua", "what did I miss")
- analytics       performance, counts, how am I doing
- item_lookup     a specific item found by words in its topic
- action_request  the user asks to change something (publish/reschedule/generate/approve/reject)
- smalltalk       greetings, thanks
- unknown         anything else

PLATFORMS: youtube, instagram, linkedin, blog, x, tiktok. Empty list = all.
STATUSES: pending, script_generated, presentation_created, video_created,
video_edited, video_published (YouTube) | idea, in_production, scheduled,
published (everything else). Empty list = all.

DATE RULES — always output YYYY-MM-DD, anchored to today ({today}):
- "today" / "aaj"                  -> today .. today
- "tomorrow" / "kal" (future)      -> today+1 .. today+1
- "yesterday" / "kal" (past tense) -> today-1 .. today-1
- "this week" / "is hafte"         -> Monday .. Sunday of the week containing today
- "next week" / "agle hafte"       -> Monday+7 .. Sunday+7
- "this month" / "is mahine"       -> first .. last day of this month
- no date mentioned                -> today .. today

The "overdue" intent takes NO dates: set date_from and date_to to null and
date_expression to "overdue". The server computes that window itself, and it
reaches further back than any range you could write — an item missed in June is
still overdue today. date_expression is always a string, never null.

"kal" means BOTH yesterday and tomorrow in Hindi. Decide from the verb:
"kal ka video kaunsa HAI" (present/future) -> tomorrow.
"kal kya publish HUA" (past) -> yesterday.
When there is no tense signal, choose tomorrow — this is a planning tool.

LANGUAGE: set "hinglish" if the question mixes Hindi words (aaj, kal, kya,
mujhe, hai, dikha, karna) or uses Devanagari; otherwise "en".

search_terms: only for item_lookup — the distinctive words from the topic the
user named. Never the whole question.

needs_analytics: true only when the user asks about performance, totals, or how
they are doing. The overdue intent carries its own count — do not set this for it.

RECENT TURNS (for pronoun resolution only):
{history}

QUESTION:
{question}

SCHEMA:
{schema}

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences."""


def _build_llm_and_chain():
    from app.llm import build_fallback_cascade

    settings = get_settings()
    primary, chain = build_fallback_cascade(settings, temperature=RESOLVER_TEMPERATURE)
    model = getattr(primary, "model", None) or settings.analysis_model
    return primary, chain, model


def _render_history(history: list[dict]) -> str:
    if not history:
        return "(none)"
    return "\n".join(f"{h['role']}: {h['content']}" for h in history[-2:])


def default_plan(today: date, language: str = "en") -> QueryPlan:
    """What we answer when the resolver cannot run: today's digest."""
    iso = today.isoformat()
    return QueryPlan(
        intent="daily_digest",
        date_expression="today",
        date_from=iso,
        date_to=iso,
        language=language,  # type: ignore[arg-type]
    )


async def resolve_query(
    question: str,
    history: list[dict],
    today: date,
    deadline: float | None = None,
    used: dict | None = None,
) -> tuple[QueryPlan, bool]:
    """Return (plan, fell_back).

    ``fell_back`` is recorded on the message's meta so a degraded answer is
    diagnosable after the fact rather than looking like a bad model.
    """
    sub_deadline = time.monotonic() + RESOLVER_BUDGET_SECONDS
    if deadline is not None:
        sub_deadline = min(sub_deadline, deadline)

    prompt = RESOLVER_PROMPT.format(
        today=today.isoformat(),
        weekday=today.strftime("%A"),
        history=_render_history(history),
        question=question.strip()[:2000],
        schema=_SCHEMA_HINT,
    )

    try:
        primary, chain, _model = _build_llm_and_chain()
        plan: QueryPlan = await call_llm_with_retry(
            primary,
            prompt,
            QueryPlan,
            temperature=RESOLVER_TEMPERATURE,
            max_retries=2,
            agent_name="AssistantResolver",
            fallback_chain=chain,
            deadline=sub_deadline,
            used=used,
        )
        return plan, False
    except (AgentFailedError, Exception) as exc:  # noqa: BLE001 — never propagate
        logger.warning("assistant: resolver fell back to daily digest: %s", exc)
        return default_plan(today), True
