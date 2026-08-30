"""Tier 3's SSE stream, and the one rule it must never break.

A truncated stream yields JSON that *looks* fine — an object missing its last
keys and its closing brace. Handing that back as a partial audit is worse than
handing back nothing, because the validator downstream sees a well-formed report
with sections quietly absent. So: a stream that did not terminate cleanly is an
error, never a result.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services import openrouter_client as oc
from app.services.openrouter_client import (
    OpenRouterError,
    OpenRouterLLM,
    TruncatedStreamError,
)


def _frame(text=None, finish_reason=None):
    delta = {"content": text} if text is not None else {}
    return "data: " + json.dumps(
        {"choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}
    )


def _serve(monkeypatch, lines=None, status=200, body=""):
    """Point the client at a scripted SSE response."""
    payload = ("\n".join(lines) + "\n").encode() if lines is not None else b""

    def handler(request):
        if status != 200:
            return httpx.Response(status, text=body)
        return httpx.Response(
            200, content=payload, headers={"content-type": "text/event-stream"}
        )

    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(oc.httpx, "Client", fake_client)


def _llm():
    return OpenRouterLLM(
        api_key="test-key",
        model="nvidia/nemotron-3-ultra-550b-a55b:free",
        timeout=5,
    )


# ── The happy path ───────────────────────────────────────────────────────────
def test_complete_stream_assembles_the_deltas_in_order(monkeypatch):
    _serve(monkeypatch, [
        ": OPENROUTER PROCESSING",          # keepalive comment, not a frame
        _frame('{"verdict":'),
        "",                                  # blank separator lines are normal SSE
        _frame(' "strong channel"'),
        _frame("}", finish_reason="stop"),
        "data: [DONE]",
    ])
    out = _llm().call("prompt")
    assert out == '{"verdict": "strong channel"}'
    assert json.loads(out) == {"verdict": "strong channel"}


def test_reasoning_scratchpad_is_not_folded_into_the_answer(monkeypatch):
    """Nemotron streams a `reasoning` field alongside `content`.

    Concatenating it would corrupt every JSON parse.
    """
    noisy = "data: " + json.dumps(
        {"choices": [{"delta": {"reasoning": "Let me think...", "content": None}}]}
    )
    _serve(monkeypatch, [noisy, _frame('{"verdict": "ok"}', "stop"), "data: [DONE]"])
    assert _llm().call("prompt") == '{"verdict": "ok"}'


# ── Truncation is failure, never partial output ──────────────────────────────
def test_stream_ending_without_done_is_a_failure(monkeypatch):
    """The connection dropped mid-answer. The half-object must not escape."""
    _serve(monkeypatch, [
        _frame('{"verdict": "strong cha'),
    ])
    with pytest.raises(TruncatedStreamError) as err:
        _llm().call("prompt")
    assert "without [DONE]" in str(err.value)


def test_truncated_stream_returns_no_partial_json(monkeypatch):
    """Belt and braces: nothing resembling the partial body comes back."""
    _serve(monkeypatch, [_frame('{"verdict": "part')])
    with pytest.raises(TruncatedStreamError) as err:
        _llm().call("prompt")
    assert '"verdict"' not in str(err.value), "the partial body must not be handed on"


def test_hitting_the_token_limit_is_truncation(monkeypatch):
    """`finish_reason == "length"` means the JSON stopped mid-structure."""
    _serve(monkeypatch, [
        _frame('{"verdict": "a very long'),
        _frame("", finish_reason="length"),
        "data: [DONE]",
    ])
    with pytest.raises(TruncatedStreamError, match="token limit"):
        _llm().call("prompt")


def test_clean_stream_with_no_content_is_a_failure(monkeypatch):
    _serve(monkeypatch, ["data: [DONE]"])
    with pytest.raises(TruncatedStreamError, match="no content"):
        _llm().call("prompt")


def test_unparseable_frame_is_a_failure(monkeypatch):
    """A frame we cannot read is a hole in the answer; it must not pass silently."""
    _serve(monkeypatch, [_frame('{"a":'), "data: {not json", "data: [DONE]"])
    with pytest.raises(TruncatedStreamError, match="unparseable"):
        _llm().call("prompt")


# ── HTTP-level failures keep their status, so the cascade can classify them ──
@pytest.mark.parametrize("status", [401, 403, 404, 429, 503])
def test_http_errors_carry_their_status_code(monkeypatch, status):
    _serve(monkeypatch, status=status, body='{"error":{"message":"nope"}}')
    with pytest.raises(OpenRouterError) as err:
        _llm().call("prompt")
    assert err.value.status_code == status


def test_in_stream_error_frame_raises(monkeypatch):
    _serve(monkeypatch, [
        "data: " + json.dumps({"error": {"code": 429, "message": "rate limited"}}),
    ])
    with pytest.raises(OpenRouterError) as err:
        _llm().call("prompt")
    assert err.value.status_code == 429


def test_missing_api_key_is_refused_at_construction():
    with pytest.raises(ValueError, match="openrouter_api_key"):
        OpenRouterLLM(api_key="", model="x")
