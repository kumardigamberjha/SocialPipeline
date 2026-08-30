"""The strict cascade: what advances a tier, and what must not.

The incident this suite exists for: a WillPower Star audit lost its Gemini quota,
silently fell through to a local Qwen 2.5, and the resulting report — which
recommended the channel's four worst weekdays and called an eight-video format
"unexplored" — was still exportable as a client-facing PDF.

The rule: when fallbacks exist, every tier gets exactly ONE attempt. Any error
— transient 503, timeout, quota, auth — advances to the next tier immediately.
Retrying a dead provider burned 90+ seconds and prevented fallbacks from ever
running. The cascade itself provides redundancy (backup Gemini key, OpenRouter,
Ollama); per-tier retries are wasteful.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from app.provider_tiers import CLIENT_GRADE, INTERNAL_ONLY, ProviderTier
from app.services.blog_pipeline import utils as u
from app.services.openrouter_client import TruncatedStreamError

GOOD_JSON = '{"verdict": "ok"}'


class Verdict(BaseModel):
    verdict: str


@pytest.fixture(autouse=True)
def _clear_cooldowns():
    """The exhausted-provider map is module-global and would leak across tests.

    Without this, the first test to trip a 429 parks that model for 30 minutes
    and every later test silently starts at the next tier.
    """
    u._PROVIDER_COOLDOWN.clear()
    yield
    u._PROVIDER_COOLDOWN.clear()


# ── Scripted providers ───────────────────────────────────────────────────────
class ProviderError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def _tier(index, grade=CLIENT_GRADE, key="t"):
    return ProviderTier(
        index=index,
        key=f"{key}{index}",
        name=f"Tier {index}",
        builder="gemini",
        model_field="analysis_model",
        api_key_field=None,
        grade=grade,
        timeout_field="gemini_tier_timeout",
    )


class FakeLLM:
    """Replays a script of outcomes and counts how often it was called.

    An entry is either an exception (raised) or a string (returned). The last
    entry repeats forever, so `[err]` means "this tier is always down".
    """

    def __init__(self, model, script, tier=None):
        self.model = model
        self.timeout = 30
        self.temperature = 0.4
        self.calls = 0
        self._script = list(script)
        if tier is not None:
            self.provider_tier = tier

    def call(self, prompt):
        self.calls += 1
        step = self._script[min(self.calls - 1, len(self._script) - 1)]
        if isinstance(step, Exception):
            raise step
        return step


def run(primary, chain, used=None, max_retries=5):
    """Drive the cascade the way the codebase does — bare asyncio.run."""
    return asyncio.run(
        u.call_llm_with_retry(
            primary,
            "prompt",
            Verdict,
            temperature=0.4,
            max_retries=max_retries,
            agent_name="AuditTest",
            fallback_chain=chain,
            deadline=None,
            used=used,
        )
    )


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    """Backoff is real time; the assertions are about counts, not clocks."""
    async def _instant(_seconds):
        return None

    monkeypatch.setattr(u.asyncio, "sleep", _instant)


# ── Advancing: only on a fault another attempt cannot fix ───────────────────
@pytest.mark.parametrize(
    "exc",
    [
        ProviderError("RESOURCE_EXHAUSTED: you exceeded your current quota", 429),
        ProviderError("429 Too Many Requests", 429),
        ProviderError("401 Unauthorized: API key not valid", 401),
        ProviderError("403 Forbidden: permission denied", 403),
        ProviderError("404 model not found: gemini-9.9-flash", 404),
        TruncatedStreamError("stream ended without [DONE] after 812 chars"),
    ],
    ids=["quota-text", "quota-429", "auth-401", "auth-403", "model-404", "truncated"],
)
def test_tier_fatal_faults_advance_immediately(exc):
    """One attempt, then move on. Retrying these burns the cascade deadline."""
    t1 = _tier(1)
    t2 = _tier(2)
    primary = FakeLLM("gemini/gemini-3.7-flash", [exc], tier=t1)
    backup = FakeLLM("gemini/gemini-3.7-flash", [GOOD_JSON], tier=t2)

    used: dict = {}
    result = run(primary, [("Tier 2", backup)], used=used)

    assert result.verdict == "ok"
    assert primary.calls == 1, "a tier-fatal fault must not be retried in place"
    assert backup.calls == 1
    assert used["tier_index"] == 2
    assert used["tier_grade"] == CLIENT_GRADE


def test_quota_exhaustion_records_the_tier_that_actually_answered():
    """The exact WillPower failure — but now the report knows who wrote it."""
    t1, t3 = _tier(1), _tier(3, grade=INTERNAL_ONLY)
    primary = FakeLLM("gemini/gemini-3.7-flash", [ProviderError("quota exceeded", 429)], tier=t1)
    nemotron = FakeLLM("nvidia/nemotron-3-ultra-550b-a55b:free", [GOOD_JSON], tier=t3)

    used: dict = {}
    run(primary, [("Tier 3", nemotron)], used=used)

    assert used["tier_index"] == 3
    assert used["tier_grade"] == INTERNAL_ONLY, "a fallback audit must not pass as client-grade"
    assert used["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"


# ── Transient faults advance immediately when fallbacks exist ────────────────
def test_transient_5xx_advances_immediately_to_fallback():
    """A 503 'high demand' advances to the next tier with zero retries."""
    busy = ProviderError(
        "503 UNAVAILABLE: This model is currently experiencing high demand. "
        "Spikes in demand are usually temporary. Please try again later.",
        503,
    )
    t1, t2 = _tier(1), _tier(2)
    primary = FakeLLM("gemini/gemini-3.7-flash", [busy], tier=t1)
    backup = FakeLLM("gemini/gemini-3.7-flash", [GOOD_JSON], tier=t2)

    used: dict = {}
    result = run(primary, [("Tier 2", backup)], used=used)

    assert result.verdict == "ok"
    assert primary.calls == 1, "one attempt then advance — no retries"
    assert backup.calls == 1, "fallback must be used immediately"
    assert used["tier_index"] == 2


def test_timeout_advances_immediately_to_fallback():
    """A timeout advances to the next tier — waiting wastes the cascade budget."""
    t1, t2 = _tier(1), _tier(2)
    primary = FakeLLM(
        "gemini/gemini-3.7-flash", [TimeoutError("call timed out")], tier=t1
    )
    backup = FakeLLM("gemini/gemini-3.7-flash", [GOOD_JSON], tier=t2)

    used: dict = {}
    result = run(primary, [("Tier 2", backup)], used=used)

    assert result.verdict == "ok"
    assert primary.calls == 1, "one attempt then advance — no retries"
    assert backup.calls == 1, "fallback must be used immediately"


def test_transient_allowance_is_one_attempt_then_advance():
    """With fallbacks, each tier gets exactly one attempt."""
    busy = ProviderError("503 high demand", 503)
    t1, t2 = _tier(1), _tier(2)
    primary = FakeLLM("gemini/gemini-3.7-flash", [busy], tier=t1)   # always down
    backup = FakeLLM("gemini/gemini-3.7-flash", [GOOD_JSON], tier=t2)

    used: dict = {}
    result = run(primary, [("Tier 2", backup)], used=used)

    assert result.verdict == "ok"
    assert primary.calls == 1, "one attempt per tier, no retries"
    assert used["tier_index"] == 2


# ── Provenance ───────────────────────────────────────────────────────────────
def test_used_model_never_carries_an_api_key_fragment():
    """`used["model"]` is persisted and returned to the browser.

    It used to be built by `_llm_key`, which appends the last 8 characters of the
    API key for cooldown bookkeeping.
    """
    tier = _tier(1)
    llm = FakeLLM("gemini/gemini-3.7-flash", [GOOD_JSON], tier=tier)
    llm.api_key = "AIzaSyTOPSECRETVALUE"

    used: dict = {}
    run(llm, [], used=used)

    assert used["model"] == "gemini/gemini-3.7-flash"
    assert "#" not in used["model"]
    assert "SECRET" not in used["model"] and "VALUE" not in used["model"]
    # The cooldown key may still discriminate on the credential — it is internal.
    assert "#" in u._llm_key(llm)


def test_llm_without_a_tier_stamp_is_treated_as_internal_only():
    """Unknown provenance must never mean exportable."""
    llm = FakeLLM("some/unregistered-model", [GOOD_JSON])  # no provider_tier
    used: dict = {}
    run(llm, [], used=used)
    assert used["tier_grade"] == INTERNAL_ONLY
    assert used["tier_index"] is None


def test_full_five_tier_cascade_escalation():
    """Verify clean step-by-step cascade from Tier 1 -> Tier 2 -> Tier 3 -> Tier 4 -> Tier 5."""
    t1 = _tier(1, grade=CLIENT_GRADE, key="gemini_primary")
    t2 = _tier(2, grade=CLIENT_GRADE, key="gemini_backup")
    t3 = _tier(3, grade=INTERNAL_ONLY, key="openrouter_nemotron")
    t4 = _tier(4, grade=INTERNAL_ONLY, key="ollama_cloud")
    t5 = _tier(5, grade=INTERNAL_ONLY, key="ollama_local")

    err_503 = ProviderError("503 high demand", 503)
    err_429 = ProviderError("429 quota exhausted", 429)

    tier1 = FakeLLM("gemini/gemini-3.7-flash", [err_503], tier=t1)
    tier2 = FakeLLM("gemini/gemini-3.7-flash", [err_429], tier=t2)
    tier3 = FakeLLM("nvidia/nemotron-3-ultra-550b-a55b:free", [err_503], tier=t3)
    tier4 = FakeLLM("ollama/gemma4:31b-cloud", [GOOD_JSON], tier=t4)
    tier5 = FakeLLM("ollama/qwen2.5:latest", [GOOD_JSON], tier=t5)

    chain = [
        ("Tier 2: Gemini (backup key)", tier2),
        ("Tier 3: OpenRouter (Nemotron 3 Ultra)", tier3),
        ("Tier 4: Ollama Cloud (Gemma 4 31B)", tier4),
        ("Tier 5: Ollama local (Qwen 2.5)", tier5),
    ]

    used: dict = {}
    result = run(tier1, chain, used=used)

    assert result.verdict == "ok"
    assert tier1.calls == 1  # 503 → advance immediately
    assert tier2.calls == 1  # 429 quota → advance immediately
    assert tier3.calls == 1  # 503 → advance immediately
    assert tier4.calls == 1  # Tier 4 answers!
    assert tier5.calls == 0  # Tier 5 not needed
    assert used["tier_index"] == 4
    assert used["tier_name"] == "Tier 4"


def test_extract_json_strips_think_tags_from_reasoning_models():
    """Reasoning models (Nemotron, DeepSeek) return <think>...</think> blocks that must not break JSON parsing."""
    raw = (
        "<think>\n"
        "Let me evaluate this channel.\n"
        "Some internal json snippet: {\"draft\": true}\n"
        "</think>\n"
        "```json\n"
        "{\"verdict\": \"ok\", \"notes\": [\"great growth\"]}\n"
        "```"
    )
    extracted = u.extract_json(raw)
    assert extracted["verdict"] == "ok"
    assert extracted["notes"] == ["great growth"]
