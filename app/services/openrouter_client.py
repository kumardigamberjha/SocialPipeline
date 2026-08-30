"""Tier 3 of the analysis cascade: OpenRouter, over SSE.

Why streaming
-------------
The free Nemotron tier is a large reasoning model. A non-streaming request holds
the connection open for the whole generation with nothing on the wire, which is
exactly the shape intermediaries like to time out. Streaming keeps bytes moving
and lets us notice a stream that dies mid-answer.

Why streaming is also the risk
------------------------------
A truncated stream yields *syntactically plausible but incomplete* JSON — an
object missing its last few keys and its closing brace. Returning that as a
partial audit is worse than returning nothing, because the downstream validator
sees a well-formed-looking report with sections quietly missing. So this client
holds one rule above all others:

    **a stream that did not terminate cleanly is an error, never a result.**

``[DONE]`` must arrive, the accumulated body must be non-empty, and the model
must not have stopped because it ran out of tokens. Any of those failing raises
:class:`TruncatedStreamError`, which ``call_llm_with_retry`` classifies as
tier-fatal — the cascade advances rather than retrying a stream that will
truncate again at the same place.

Why sync
--------
``call_llm_with_retry`` invokes ``llm.call(prompt)`` inside
``asyncio.to_thread``. A sync ``httpx.Client`` is the honest fit; an async client
here would mean spinning up an event loop per call inside a worker thread.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: OpenRouter emits ``: OPENROUTER PROCESSING`` keepalives while a slow model
#: warms up. They are SSE comments and carry no payload.
_SSE_DATA_PREFIX = "data: "
_SSE_DONE = "[DONE]"


class OpenRouterError(Exception):
    """A non-2xx response from OpenRouter.

    Carries ``status_code`` so the retry helper can tell a 429/401/403/404
    (advance the tier — another attempt cannot help) from a 5xx (retry here).
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TruncatedStreamError(OpenRouterError):
    """The SSE stream ended without completing the response.

    Always tier-fatal. A stream that truncated once will truncate again, and the
    half-written JSON it produced must never reach a report.
    """


class OpenRouterLLM:
    """A crewai-``LLM``-shaped adapter around one OpenRouter model.

    Exposes the attributes ``call_llm_with_retry`` reads off an LLM object —
    ``model``, ``timeout``, ``temperature``, ``api_key`` — plus ``call(prompt)``,
    so it drops into the existing cascade with no special-casing.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        api_base: str = "https://openrouter.ai/api/v1",
        temperature: float = 0.4,
        timeout: int = 150,
        max_tokens: int | None = None,
        referer: str = "",
        title: str = "",
    ) -> None:
        if not api_key:
            raise ValueError("Missing openrouter_api_key")
        self.api_key = api_key
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._referer = referer
        self._title = title

    # ── internals ────────────────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        # Optional attribution. OpenRouter shows these on the account dashboard;
        # neither is required and an empty value is worse than an absent header.
        if self._referer:
            headers["HTTP-Referer"] = self._referer
        if self._title:
            headers["X-Title"] = self._title
        return headers

    def _payload(self, prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "stream": True,
        }
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        return payload

    @staticmethod
    def _extract_delta(frame: dict[str, Any]) -> tuple[str, str | None]:
        """One frame's text delta and finish_reason.

        Reasoning models put their scratchpad in a separate ``reasoning`` field.
        Only ``content`` is accumulated — the scratchpad is not part of the JSON
        answer and folding it in would break every parse.
        """
        choices = frame.get("choices") or []
        if not choices:
            return "", None
        choice = choices[0] or {}
        delta = choice.get("delta") or {}
        return delta.get("content") or "", choice.get("finish_reason")

    # ── public API ───────────────────────────────────────────────────────────
    def call(self, prompt: str) -> str:
        """Stream one completion and return the fully assembled text.

        Raises rather than returning anything partial. See the module docstring.
        """
        chunks: list[str] = []
        saw_done = False
        finish_reason: str | None = None

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream(
                    "POST",
                    f"{self.api_base}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(prompt),
                ) as response:
                    if response.status_code >= 400:
                        # The body has not been consumed yet on a streamed
                        # response; read it so the error carries the provider's
                        # own explanation instead of an opaque status.
                        body = response.read().decode("utf-8", "replace")[:500]
                        raise OpenRouterError(
                            f"OpenRouter {response.status_code}: {body}",
                            status_code=response.status_code,
                        )

                    for line in response.iter_lines():
                        if not line:
                            continue
                        if not line.startswith(_SSE_DATA_PREFIX):
                            # SSE comment / keepalive.
                            continue
                        data = line[len(_SSE_DATA_PREFIX):].strip()
                        if data == _SSE_DONE:
                            saw_done = True
                            break
                        try:
                            frame = json.loads(data)
                        except json.JSONDecodeError:
                            # A single unparseable frame is not necessarily fatal
                            # — but it does mean we have a hole in the answer, so
                            # it must not pass silently.
                            raise TruncatedStreamError(
                                f"OpenRouter sent an unparseable SSE frame: {data[:200]}"
                            ) from None
                        if frame.get("error"):
                            err = frame["error"]
                            raise OpenRouterError(
                                f"OpenRouter stream error: {err}",
                                status_code=(err or {}).get("code")
                                if isinstance(err, dict)
                                else None,
                            )
                        text, reason = self._extract_delta(frame)
                        if text:
                            chunks.append(text)
                        if reason:
                            finish_reason = reason
        except httpx.HTTPError as exc:
            # Transport-level: connection reset, read timeout mid-stream. Not
            # tier-fatal on its own — the retry helper decides.
            raise OpenRouterError(f"OpenRouter transport failure: {exc}") from exc

        assembled = "".join(chunks)

        if not saw_done:
            raise TruncatedStreamError(
                "OpenRouter stream ended without [DONE] after "
                f"{len(assembled)} chars; refusing to use a partial response"
            )
        if finish_reason == "length":
            raise TruncatedStreamError(
                "OpenRouter stopped at the token limit; the response is incomplete"
            )
        if not assembled.strip():
            raise TruncatedStreamError("OpenRouter stream completed but carried no content")

        logger.debug(
            "OpenRouter %s streamed %d chars (finish_reason=%s)",
            self.model,
            len(assembled),
            finish_reason,
        )
        return assembled


def build_openrouter_llm(
    settings,
    temperature: float = 0.4,
    model: str | None = None,
    timeout: int | None = None,
    max_tokens: int | None = None,
) -> OpenRouterLLM:
    """Builder matching the signature shape of the ones in ``app.llm``."""
    return OpenRouterLLM(
        api_key=settings.openrouter_api_key or "",
        model=model or settings.openrouter_model,
        api_base=settings.openrouter_api_base,
        temperature=temperature,
        timeout=timeout or settings.openrouter_timeout,
        max_tokens=max_tokens,
        referer=getattr(settings, "openrouter_referer", ""),
        title=getattr(settings, "openrouter_title", ""),
    )
