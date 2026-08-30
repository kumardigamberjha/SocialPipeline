"""
Shared helpers for the blog pipeline: JSON extraction, slugify, LLM model
builder, and the validate-with-retry LLM caller.

LLM note
--------
This project uses crewai.LLM (built via app.llm.build_llm), whose ``.call()``
method is *synchronous* and returns a plain string. There is no ``ainvoke``.
So the async retry helper below runs ``llm.call`` inside ``asyncio.to_thread``
to avoid blocking the event loop, and sets temperature / max_tokens on the LLM
instance before each call (crewai.LLM reads these attributes at call time).
"""

import asyncio
import json
import logging
import random
import re
import time
import unicodedata

from typing import Any, get_args, get_origin
from pydantic import BaseModel, model_validator

from app.config import get_settings
from app.provider_tiers import UNKNOWN_GRADE
from app.llm import build_llm

logger = logging.getLogger(__name__)


class AgentFailedError(Exception):
    """Raised when an agent fails to produce schema-valid JSON after all retries."""


# ── Per-provider output-token ceilings ──────────────────────────────────────
# Section calls are small; the researcher's grounding pack is the large one.
# Values stay within each provider's documented completion-token max.
_PROVIDER_MAX_TOKENS = {
    "groq": 32000,
    "nvidia": 16384,
    "ollama": 16384,
}


def make_llm(provider: str, temperature: float, max_tokens: int = 4096):
    """Build a crewai.LLM for the given provider with a fixed temperature and a
    raised (but provider-capped) output-token ceiling.

    A fresh instance is returned per agent so concurrent agents never race on a
    shared temperature attribute.
    """
    settings = get_settings()
    llm = build_llm(provider, settings)
    cap = _PROVIDER_MAX_TOKENS.get((provider or "").lower(), max_tokens)
    try:
        llm.temperature = temperature
        llm.max_tokens = min(max_tokens, cap)
    except Exception:  # pragma: no cover — crewai.LLM always exposes these
        pass
    return llm


def _sanitize_control_chars(text: str) -> str:
    """Escape literal control characters inside JSON string literals.

    Local models (Ollama) often emit raw newlines/tabs inside JSON strings
    instead of the required \\n/\\t escape sequences, causing json.loads to
    raise 'Invalid control character'. This state-machine walks the JSON text
    and fixes only characters inside string values, leaving structural chars
    (braces, colons, commas) untouched.
    """
    result: list[str] = []
    in_string = False
    escape_next = False
    _ESC = {'\n': '\\n', '\r': '\\r', '\t': '\\t', '\b': '\\b', '\f': '\\f'}
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
        elif ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ord(ch) < 0x20:
            result.append(_ESC.get(ch, f'\\u{ord(ch):04x}'))
        else:
            result.append(ch)
    return ''.join(result)


def extract_json(raw: str) -> dict:
    """
    Robustly extract a JSON object/array from LLM output that may contain:
      - Markdown fences (```json ... ```)
      - Surrounding prose
      - Trailing commas (a common small-model mistake)
      - Literal control characters inside string values (local model quirk)
    """
    if raw is None:
        raise ValueError("No JSON found in LLM output: <empty>")

    text = str(raw)

    # Step 1: strip think tags and markdown fences
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)

    # Step 2: find the outermost { ... } or [ ... ]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in LLM output: {text.strip()[:200]}")

    candidate = match.group(0)

    # Step 2.5: fix literal control characters that local models emit inside strings
    candidate = _sanitize_control_chars(candidate)

    # Step 3: fix trailing commas (small models love these)
    candidate = re.sub(r",\s*}", "}", candidate)
    candidate = re.sub(r",\s*]", "]", candidate)

    data = json.loads(candidate)
    if isinstance(data, list):
        # Some prompts may return a bare array; wrap so callers always get a dict
        # only when the schema expects one. Researcher/outline arrays are handled
        # by the caller, so return as-is under a conventional key.
        return {"items": data}
    return data


def slugify(title: str) -> str:
    """URL-safe slug from a title."""
    title = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    title = title.lower().strip()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"[\s_-]+", "-", title)
    title = re.sub(r"^-+|-+$", "", title)
    return title or "untitled-post"


# ── Transient-failure handling ──────────────────────────────────────────────
# Two very different things can make an LLM call fail:
#   * the model returned something we could not parse/validate (our problem —
#     retry immediately, the next sample is usually fine), and
#   * the provider is overloaded or rate-limiting us (503 "high demand",
#     429, 5xx, connection resets). Hammering those every second just burns
#     the retry budget while the spike is still going, so they get
#     exponential backoff with jitter and a couple of extra attempts.
_SCHEMA_RETRY_DELAY = 1.0     # seconds, for "model wrote bad JSON" retries
_BASE_BACKOFF = 2.0           # seconds, first provider-side backoff
_MAX_BACKOFF = 10.0           # ceiling per sleep, so a call cannot stall forever
_TRANSIENT_GRACE = 2          # historical; superseded by _TRANSIENT_ATTEMPTS below
# Attempts a tier gets on a *transient* fault before the cascade gives up on
# it. One: with a backup Gemini key and OpenRouter in the chain, retrying the
# same dead provider just wastes the cascade deadline. A 503 "high demand"
# from Gemini persists for minutes — three retries with backoff burned 90+
# seconds before fallback could even start. One shot, then move on.
_TRANSIENT_ATTEMPTS = 1

# ── Time budgets ────────────────────────────────────────────────────────────
# Each tier's wall-clock budget lives on the LLM object itself, as ``llm.timeout``
# set by the builders in app/llm.py. Reading it back off the object keeps one
# source of truth: a parallel tier-name → seconds table here would silently drift
# the moment a model or provider changed.
#
# This replaces a hardcoded ``20.0 if has_fallback else 60.0``, which every
# analysis call hit (they all pass a fallback chain). 20s is unreachable for the
# slower tiers — DeepSeek runs at roughly 8 tok/s here — so those tiers failed
# 100% of the time and every request walked the whole cascade into a 502.
_DEFAULT_TIER_TIMEOUT = 60.0
# asyncio.wait_for cannot kill the OS thread that asyncio.to_thread started, so
# the *client's* own timeout has to fire first or the abandoned call keeps
# running (and keeps holding a thread-pool worker). The outer wait_for is only a
# backstop for a client that ignores its timeout, so it gets a grace margin.
_CLIENT_TIMEOUT_GRACE = 5.0


def _tier_budget(llm) -> float:
    """This tier's wall-clock budget, as set by the builders in app/llm.py."""
    try:
        value = float(getattr(llm, "timeout", None) or 0)
    except (TypeError, ValueError):
        return _DEFAULT_TIER_TIMEOUT
    return value if value > 0 else _DEFAULT_TIER_TIMEOUT


# ── Exhausted-provider cooldown ─────────────────────────────────────────────
# A provider that has burned its quota will keep saying so for every request in
# the window. Retrying it each time costs a wasted attempt, a scary provider
# error panel in the logs, and (worst) a slice of the cascade deadline. Park it
# until the quota is plausibly back and start at the next tier instead.
_PROVIDER_COOLDOWN: dict[str, float] = {}
_QUOTA_COOLDOWN_DEFAULT = 60.0     # a per-minute rate limit
_QUOTA_COOLDOWN_DAILY = 1800.0     # a per-day quota; retryDelay lies about these
_QUOTA_COOLDOWN_MAX = 3600.0

_QUOTA_PATTERNS = re.compile(
    r"resource.?exhausted|exceeded your current quota|quota exceeded"
    r"|insufficient_quota|billing|rate.?limit",
    re.IGNORECASE,
)
_DAILY_QUOTA_PATTERNS = re.compile(r"per.?day|daily|freetier|free_tier", re.IGNORECASE)


def _llm_key(llm) -> str:
    """Cooldown-map identity. **Internal only — never surfaced.**

    Two tiers can run the same model on different API keys (Gemini primary vs
    backup), and parking one for quota must not park the other, so the key has
    to discriminate on the credential. It therefore embeds a fragment of the
    API key and must never reach a response, a database row or a log line that
    a user can read. Use :func:`_public_model` for anything outward-facing.
    """
    model = str(getattr(llm, "model", None) or type(llm).__name__)
    key = getattr(llm, "api_key", None)
    if key:
        key_id = str(key)[-8:]
        return f"{model}#{key_id}"
    return model


def _public_model(llm) -> str:
    """The bare model string, safe to persist and display.

    This exists because ``used["model"]`` used to be set from ``_llm_key``,
    so ``"gemini/gemini-3.7-flash#AIzaSyQ1"`` was written to Postgres and sent
    to the browser — leaking eight characters of the API key on every report.
    """
    return str(getattr(llm, "model", None) or type(llm).__name__)


def _tier_of(llm):
    """The :class:`ProviderTier` stamped on the LLM by ``build_tier_cascade``."""
    return getattr(llm, "provider_tier", None)


def _note_if_exhausted(llm, exc: Exception) -> None:
    """Park a provider that just told us it is out of quota."""
    text = str(exc)
    if not _QUOTA_PATTERNS.search(text):
        return
    if _DAILY_QUOTA_PATTERNS.search(text):
        # Gemini's free tier reports a 20/day cap with a retryDelay of ~25s.
        # Honouring that delay would just re-burn the attempt 25s later.
        cooldown = _QUOTA_COOLDOWN_DAILY
    else:
        cooldown = max(_retry_after_seconds(exc) or 0.0, _QUOTA_COOLDOWN_DEFAULT)
    cooldown = min(cooldown, _QUOTA_COOLDOWN_MAX)
    _PROVIDER_COOLDOWN[_llm_key(llm)] = time.monotonic() + cooldown
    logger.warning(
        "%s is out of quota; skipping it for %.0fs", _llm_key(llm), cooldown
    )


def cooldown_remaining_for_key(key: str) -> float:
    """Seconds until the provider behind ``key`` is worth trying again.

    Public because ``app.llm.describe_chain`` reports parked tiers on
    ``/api/health``, and needs to do so without building the cascade.
    """
    expiry = _PROVIDER_COOLDOWN.get(key)
    if expiry is None:
        return 0.0
    left = expiry - time.monotonic()
    if left <= 0:
        _PROVIDER_COOLDOWN.pop(key, None)
        return 0.0
    return left


def _cooldown_remaining(llm) -> float:
    """Seconds until this provider is worth trying again (0 when it is now)."""
    return cooldown_remaining_for_key(_llm_key(llm))


def _apply_timeout(llm, seconds: float) -> None:
    """
    Narrow this call's client-side timeout to ``seconds``.

    Needed because asyncio.wait_for cannot kill the OS thread asyncio.to_thread
    started: unless the provider client aborts the HTTP request itself, an
    abandoned call keeps running — and keeps holding a thread-pool worker — long
    after the cascade moved on.

    crewai's OpenAI-compatible providers (both Ollama tiers) build their SDK
    client once, in a model_validator at construction, and cache it on
    ``_client`` / ``_async_client``. Setting ``.timeout`` alone would therefore
    change nothing, so the cached clients are dropped and rebuilt on next use.
    """
    try:
        llm.timeout = seconds
    except Exception:
        # A provider whose class has no timeout field (crewai's native Gemini);
        # app/llm.py routes that one through litellm so this should not happen.
        logger.debug("%s does not accept a timeout; relying on the outer guard", type(llm).__name__)
        return
    for attr in ("_client", "_async_client"):
        if getattr(llm, attr, None) is not None:
            try:
                setattr(llm, attr, None)
            except Exception:
                pass


def _remaining(deadline: float | None) -> float:
    """Seconds left on the cascade-wide deadline (inf when there isn't one)."""
    if deadline is None:
        return float("inf")
    return deadline - time.monotonic()


# litellm/openai-style exception classes that always mean "try again later".
_TRANSIENT_EXC_NAMES = {
    "APIConnectionError",
    "APIError",
    "InternalServerError",
    "RateLimitError",
    "ServiceUnavailableError",
    "ServiceUnavailable",
    "Timeout",
    "APITimeoutError",
}

_TRANSIENT_PATTERNS = re.compile(
    r"\b(?:404|429|500|502|503|504)\b"
    r"|overload|unavailable|high demand|temporarily"
    r"|rate.?limit|quota|resource.?exhausted|not.?found|no longer available|deprecated"
    r"|timed?.?out|connection (?:error|reset|aborted|refused)",
    re.IGNORECASE,
)

# Providers advertise their own wait: OpenAI-style `retry-after`, Gemini-style
# `"retryDelay": "27s"`. Honour it when present instead of guessing.
_RETRY_AFTER_RE = re.compile(
    r"retry[-_ ]?(?:after|delay)\"?\s*[:=]\s*\"?(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Keys a model tends to reach for when it wraps a list item in an object, e.g.
# `priorities: [{"action": "...", "priority": 1}]` against a `list[str]` field.
_TEXTY_KEYS = ("action", "text", "title", "item", "value", "name", "description", "summary")


def coerce_str_list(value: Any) -> Any:
    """
    Normalise a ``list[str]`` field that a model returned as ``list[dict]``.

    Weaker models routinely answer a "ranked list of actions" prompt with
    ``[{"action": "...", "priority": 1}, ...]``. That is a reasonable reading of
    the instruction, so repair it instead of failing the whole report. Anything
    already well-formed passes through untouched.
    """
    if not isinstance(value, list):
        return value
    out: list[Any] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            for key in _TEXTY_KEYS:
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    out.append(candidate)
                    break
            else:
                # No known key: keep the first non-empty string value, else the
                # whole dict rendered, so nothing is silently dropped.
                strings = [v for v in item.values() if isinstance(v, str) and v.strip()]
                out.append(strings[0] if strings else json.dumps(item, ensure_ascii=False))
        else:
            out.append(item)
    return out


class CoercingBaseModel(BaseModel):
    """
    Base model that repairs the JSON shapes weak models actually return.

    Every ``list[str]`` field accepts ``list[dict]`` and is flattened via
    :func:`coerce_str_list`. Subclass this instead of ``BaseModel`` for anything
    validated straight out of an LLM response.
    """

    @model_validator(mode="before")
    @classmethod
    def _coerce_str_lists(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        repaired = dict(data)
        for name, field in cls.model_fields.items():
            annotation = field.annotation
            if get_origin(annotation) is list and get_args(annotation) == (str,):
                key = field.alias or name
                if key in repaired:
                    repaired[key] = coerce_str_list(repaired[key])
                elif name in repaired:
                    repaired[name] = coerce_str_list(repaired[name])
        return repaired


def _is_transient(exc: Exception) -> bool:
    """True when the failure is the provider's, not the model output's."""
    if type(exc).__name__ in _TRANSIENT_EXC_NAMES:
        return True
    # Our own parse/validation failures (extract_json's ValueError, pydantic's
    # ValidationError, json.JSONDecodeError) are all ValueErrors — never treat
    # a stray "503" inside echoed model output as a provider outage.
    if isinstance(exc, ValueError):
        return False
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status == 404 or status == 429 or status >= 500):
        return True
    return bool(_TRANSIENT_PATTERNS.search(str(exc)))


# Only these advance the cascade. Everything else transient — 5xx, connection
# resets, read timeouts — is the provider having a bad minute, and the *same*
# tier is still the best available answer, so it gets retried in place.
#
# The distinction is the whole point of the strict cascade: the old code
# advanced on any timeout, which meant one slow Gemini response was enough to
# drop a client audit onto a local 7B model.
_AUTH_FAILURE_RE = re.compile(
    r"\b(?:401|403)\b|unauthorized|forbidden|permission.?denied"
    r"|api.?key.not.valid|invalid.api.key|authentication",
    re.IGNORECASE,
)
_MODEL_MISSING_RE = re.compile(
    r"\b404\b|not.?found|no longer available|deprecated|unknown model",
    re.IGNORECASE,
)
_QUOTA_STATUS_RE = re.compile(r"\b429\b", re.IGNORECASE)


def _tier_fatal_reason(exc: Exception) -> str | None:
    """Why this tier cannot succeed on a retry, or ``None`` to retry it.

    Returns a stable machine-readable reason so the escalation log is
    greppable: ``quota_exhausted`` | ``auth_failed`` | ``model_not_found`` |
    ``stream_truncated``.
    """
    # A truncated stream will truncate again at the same place; and its
    # half-written JSON must never be treated as a partial success.
    if type(exc).__name__ == "TruncatedStreamError":
        return "stream_truncated"

    # Our own parse/validation failures are ValueErrors. A model echoing "429"
    # inside its output must not be read as a provider status.
    if isinstance(exc, ValueError):
        return None

    text = str(exc)
    status = getattr(exc, "status_code", None)

    if status in (401, 403) or _AUTH_FAILURE_RE.search(text):
        return "auth_failed"
    if status == 404 or _MODEL_MISSING_RE.search(text):
        return "model_not_found"
    if status == 429 or _QUOTA_STATUS_RE.search(text) or _QUOTA_PATTERNS.search(text):
        return "quota_exhausted"
    return None


def _retry_after_seconds(exc: Exception) -> float | None:
    """Provider-supplied wait, clamped to something a request can survive."""
    match = _RETRY_AFTER_RE.search(str(exc))
    if not match:
        return None
    try:
        return min(float(match.group(1)), _MAX_BACKOFF * 3)
    except ValueError:
        return None


def _invoke_llm(llm, prompt: str) -> str:
    """Synchronous single call into crewai.LLM. Returns the response text."""
    response = llm.call(prompt)
    if hasattr(response, "content"):
        return response.content
    return str(response)


def build_fallback_chain(temperature: float = 0.4, max_tokens: int | None = None):
    """Build the resilient LLM cascade. Order lives in ``app.provider_tiers``."""
    from app.llm import build_fallback_cascade
    settings = get_settings()
    return build_fallback_cascade(settings, temperature=temperature, max_tokens=max_tokens)


def _log_tier_advance(
    agent_name: str,
    llm,
    reason: str,
    exc: Exception,
    extra: str = "",
) -> None:
    """WARNING on every tier advance, with a machine-readable reason.

    Degradation used to be visible only as an INFO line, which is why nobody
    noticed an audit had been written by a fallback model until it was read in
    a PDF. Anything that drops the cascade a rung is a warning.
    """
    tier = _tier_of(llm)
    logger.warning(
        "LLM tier advance: agent=%s from_tier=%s from_grade=%s model=%s "
        "reason=%s %s| %s",
        agent_name,
        getattr(tier, "index", "?"),
        getattr(tier, "grade", "unknown"),
        _public_model(llm),
        reason,
        f"({extra}) " if extra else "",
        exc,
    )


async def call_llm_with_retry(
    llm,
    prompt: str,
    schema_class: type[BaseModel],
    temperature: float,
    max_retries: int = 5,
    agent_name: str = "Agent",
    fallback_llm=None,
    fallback_chain: list[tuple[str, Any]] | None = None,
    deadline: float | None = None,
    is_fallback_tier: bool = False,
    used: dict[str, Any] | None = None,
) -> BaseModel:
    """
    Call the LLM, extract JSON, and validate it against ``schema_class``.
    Retries on transient errors (429 quota exhaustion, 503 high demand, timeouts)
    and schema parse failures.

    Retries on a *transient* fault (5xx, timeout, connection reset) stay on the
    same tier — ``_TRANSIENT_ATTEMPTS`` of them, with exponential backoff. The
    cascade advances only when another attempt cannot help: quota exhausted,
    credentials rejected, model not found, or a truncated stream. See
    ``_tier_fatal_reason``.

    The chain itself is declared in ``app.provider_tiers``, not here.

    ``deadline`` is a ``time.monotonic()`` stamp shared by the whole cascade, so
    the total time spent across every tier is bounded. It must stay inside the
    caller's own limit — these run in synchronous request handlers behind a
    ~100s Cloudflare proxy timeout. When omitted, it defaults to
    ``settings.llm_timeout`` from the first (non-fallback) call.
    """
    if fallback_chain is None and fallback_llm is None:
        try:
            _, auto_chain = build_fallback_chain(temperature=temperature)
            fallback_chain = auto_chain
        except Exception as err:
            logger.debug("Could not auto-build fallback chain: %s", err)

    has_fallback = (fallback_chain is not None and len(fallback_chain) > 0) or (fallback_llm is not None)
    can_escalate = has_fallback or is_fallback_tier

    if deadline is None:
        try:
            settings = get_settings()
            if has_fallback:
                usable_chain = getattr(settings, "usable_provider_chain", [])
                tier_sum = sum(t.timeout(settings) for t in usable_chain) if usable_chain else 0
                cascade_timeout = max(
                    float(getattr(settings, "audit_llm_timeout", 300) or 300),
                    float(tier_sum),
                    450.0,
                )
                deadline = time.monotonic() + cascade_timeout
            else:
                deadline = time.monotonic() + float(settings.llm_timeout)
        except Exception:
            deadline = time.monotonic() + (450.0 if has_fallback else _DEFAULT_TIER_TIMEOUT)

    tier_budget = _tier_budget(llm)
    last_error: Exception | None = None
    last_was_transient = False
    transient_failures = 0
    budget = max_retries
    attempt = 0

    # A primary that is parked has somewhere to go; don't spend an attempt on it.
    cooling = _cooldown_remaining(llm)
    if cooling > 0 and has_fallback:
        tier = _tier_of(llm)
        logger.warning(
            "Primary AI key exhausted / parked for quota (cooling for %.0fs); running on fallback tiers. agent=%s, tier=%s, model=%s",
            cooling,
            agent_name,
            getattr(tier, "name", "Tier 1"),
            _public_model(llm),
        )
        budget = 0
        last_error = RuntimeError(f"{_public_model(llm)} out of quota for another {cooling:.0f}s")
        last_was_transient = True

    # When there are fallbacks, one shot per tier — no retry. The cascade
    # itself provides redundancy; retrying a failed tier wastes the deadline
    # and prevents fallbacks from ever running.
    if can_escalate:
        budget = 1

    while attempt < budget:
        attempt += 1
        effective_timeout = min(tier_budget, _remaining(deadline))
        if effective_timeout <= 0:
            if is_fallback_tier or has_fallback:
                effective_timeout = min(tier_budget, 45.0)
            else:
                logger.warning(
                    "%s: cascade deadline exhausted before attempt %d; not starting a doomed call",
                    agent_name,
                    attempt,
                )
                last_error = last_error or TimeoutError("cascade deadline exhausted")
                last_was_transient = True
                break
        try:
            try:
                model_str = str(getattr(llm, "model", "") or "")
                if "gemini-3" in model_str or "gemini-2.5" in model_str:
                    llm.temperature = 1.0
                else:
                    llm.temperature = temperature
            except Exception:
                pass
            _apply_timeout(llm, effective_timeout)
            raw = await asyncio.wait_for(
                asyncio.to_thread(_invoke_llm, llm, prompt),
                timeout=effective_timeout + _CLIENT_TIMEOUT_GRACE,
            )
            data = extract_json(raw)
            # model_validate, not schema_class(**data): a chatty model that adds
            # one extra top-level key would otherwise raise TypeError and burn a
            # retry on output that was otherwise perfectly good.
            validated = schema_class.model_validate(data)
            if used is not None:
                # Report the tier that actually answered. Callers used to label
                # every result with the *primary* model, so a report written by
                # Ollama still claimed to be Gemini.
                #
                # _public_model, not _llm_key: the latter carries an API-key
                # fragment and this dict is persisted and returned to the client.
                used["model"] = _public_model(llm)
                used["agent"] = agent_name
                tier = _tier_of(llm)
                if tier is not None:
                    used["tier_index"] = tier.index
                    used["tier_name"] = tier.name
                    used["tier_grade"] = tier.grade
                    used["tier"] = tier.name
                else:
                    # An LLM built outside build_tier_cascade has no provenance.
                    # Unknown provenance is treated as internal_only downstream.
                    used["tier_index"] = None
                    used["tier_name"] = agent_name
                    used["tier_grade"] = UNKNOWN_GRADE
                    used["tier"] = agent_name
            if is_fallback_tier:
                tier_obj = _tier_of(llm)
                logger.warning(
                    "LLM generation answered by fallback tier: agent=%s tier=%s (grade=%s, model=%s)",
                    agent_name,
                    getattr(tier_obj, "name", "fallback"),
                    getattr(tier_obj, "grade", "unknown"),
                    _public_model(llm),
                )
            return validated
        except Exception as e:  # malformed JSON, schema error, or transport error
            last_error = e
            _note_if_exhausted(llm, e)
            last_was_transient = _is_transient(e) or isinstance(e, (asyncio.TimeoutError, TimeoutError))
            fatal_reason = _tier_fatal_reason(e)
            if last_was_transient:
                transient_failures += 1
            logger.warning(
                "%s attempt %d/%d failed (%s): %s",
                agent_name,
                attempt,
                budget,
                fatal_reason
                or ("provider unavailable" if last_was_transient else "invalid output"),
                e,
            )

            # When fallbacks exist, advance immediately on ANY error — no
            # retries. The cascade has backup keys and other providers;
            # retrying a broken tier just wastes the deadline.
            if can_escalate:
                reason = fatal_reason or ("provider_unavailable" if last_was_transient else "invalid_output")
                _log_tier_advance(agent_name, llm, reason, e)
                break

            # No fallback chain — retry with backoff (this is the last resort).
            if last_was_transient:
                delay = _retry_after_seconds(e) or _BASE_BACKOFF * 2 ** (
                    transient_failures - 1
                )
                delay = min(delay, _MAX_BACKOFF)
                delay += random.uniform(0, delay * 0.25)
            else:
                delay = _SCHEMA_RETRY_DELAY

            if attempt < budget and _remaining(deadline) > delay:
                await asyncio.sleep(delay)

    # ── Fallback Cascade ────────────────────────────────────────────────────────
    # A tier that keeps returning the wrong shape is escalated too: the previous
    # behaviour gated this on `last_was_transient`, so a model that reliably
    # produced malformed JSON could never hand off to one that would get it right.
    if fallback_chain:
        usable = [(n, c) for n, c in fallback_chain if c is not None]
        for position, (tier_name, fallback_candidate) in enumerate(usable):
            is_last_resort = position == len(usable) - 1
            # Skip a parked provider — but never the last one standing, or a
            # quota blip on every tier would leave the request with nothing.
            cooling = _cooldown_remaining(fallback_candidate)
            if cooling > 0 and not is_last_resort:
                logger.info(
                    "%s: skipping %s, out of quota for another %.0fs",
                    agent_name, tier_name, cooling,
                )
                continue
            # Ensure the fallback candidate has at least its tier budget
            cand_budget = _tier_budget(fallback_candidate)
            if _remaining(deadline) < cand_budget:
                deadline = time.monotonic() + cand_budget + _CLIENT_TIMEOUT_GRACE
            fatal_reason = _tier_fatal_reason(last_error) if last_error else ("quota_exhausted" if cooling > 0 else ("provider_unavailable" if last_was_transient else "invalid_output"))
            tier_obj = _tier_of(fallback_candidate)
            logger.warning(
                "LLM generation running on fallback tier below primary: agent=%s target_tier=%s (grade=%s, model=%s) reason=%s | error=%s",
                agent_name,
                tier_name,
                getattr(tier_obj, "grade", "unknown"),
                _public_model(fallback_candidate),
                fatal_reason,
                last_error,
            )
            try:
                # fallback_chain=[] (not None) so the callee neither auto-builds a
                # fresh chain nor re-walks the tail this loop already owns. Passing
                # the remaining tail down *and* iterating here meant a depth-n chain
                # could attempt up to 2^n tiers.
                return await call_llm_with_retry(
                    fallback_candidate,
                    prompt,
                    schema_class,
                    temperature,
                    max_retries=1,
                    agent_name=f"{agent_name}[{tier_name}]",
                    fallback_chain=[],
                    deadline=deadline,
                    is_fallback_tier=True,
                    used=used,
                )
            except AgentFailedError as fallback_err:
                logger.warning("%s: %s failed (%s), trying next fallback in chain", agent_name, tier_name, fallback_err)
                last_error = fallback_err
                continue

    elif fallback_llm is not None:
        logger.warning(
            "%s: primary LLM unusable after %d attempts, retrying on fallback LLM",
            agent_name,
            attempt,
        )
        try:
            return await call_llm_with_retry(
                fallback_llm,
                prompt,
                schema_class,
                temperature,
                max_retries=2,
                agent_name=f"{agent_name}[fallback]",
                fallback_chain=[],
                deadline=deadline,
                is_fallback_tier=True,
                used=used,
            )
        except AgentFailedError as fallback_error:
            logger.warning("%s: fallback LLM also failed: %s", agent_name, fallback_error)
            last_error = fallback_error

    raise AgentFailedError(
        f"{agent_name} failed after {attempt} attempts. Last error: {last_error}"
    )
