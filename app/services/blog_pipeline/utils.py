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
import re
import unicodedata

from pydantic import BaseModel

from app.config import get_settings
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

    # Step 1: strip markdown fences
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


def _invoke_llm(llm, prompt: str) -> str:
    """Synchronous single call into crewai.LLM. Returns the response text."""
    response = llm.call(prompt)
    if hasattr(response, "content"):
        return response.content
    return str(response)


async def call_llm_with_retry(
    llm,
    prompt: str,
    schema_class: type[BaseModel],
    temperature: float,
    max_retries: int = 5,
    agent_name: str = "Agent",
) -> BaseModel:
    """
    Call the LLM, extract JSON, and validate it against ``schema_class``.
    Retries up to ``max_retries`` times on any failure (malformed JSON or
    schema-validation error). Raises ``AgentFailedError`` once exhausted.

    The LLM's temperature is (re)applied before every attempt so a shared
    instance can never drift.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            try:
                llm.temperature = temperature
            except Exception:
                pass
            raw = await asyncio.to_thread(_invoke_llm, llm, prompt)
            data = extract_json(raw)
            return schema_class(**data)
        except Exception as e:  # malformed JSON, schema error, or transport error
            last_error = e
            logger.warning("%s attempt %d/%d failed: %s", agent_name, attempt, max_retries, e)
            if attempt < max_retries:
                await asyncio.sleep(1)
            continue
    raise AgentFailedError(
        f"{agent_name} failed after {max_retries} attempts. Last error: {last_error}"
    )
