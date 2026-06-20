"""
Agent 1 — Researcher.

Runs the existing multi-source ResearchEngine, fetches the top result pages,
strips them to plain text (stdlib only), and asks the LLM to build a grounded
outline (GroundingPack) using ONLY verbatim excerpts from those pages.

Temperature: 0.4
"""

import asyncio
import json
import logging
from html.parser import HTMLParser

from app.services.blog_pipeline.schemas import GroundingPack
from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm
from app.tools.research_engine import get_research_engine

logger = logging.getLogger(__name__)

RESEARCHER_TEMPERATURE = 0.4
_MAX_PAGES = 8
_PAGE_CHARS = 500
_FETCH_TIMEOUT = 10

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


class ResearcherFailedError(Exception):
    """Raised when the researcher cannot produce a valid GroundingPack."""


# ── HTML → text (stdlib only) ────────────────────────────────────────────────


class _TextExtractor(HTMLParser):
    """Collect visible text, skipping script/style/head noise."""

    _SKIP = {"script", "style", "head", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._chunks.append(text)

    def text(self) -> str:
        return " ".join(self._chunks)


def strip_html(raw_html: str) -> str:
    """Return the visible text of an HTML document as a single whitespace-collapsed string."""
    parser = _TextExtractor()
    try:
        parser.feed(raw_html)
    except Exception:  # malformed markup — return whatever we managed to collect
        pass
    return " ".join(parser.text().split())


# ── Prompt ───────────────────────────────────────────────────────────────────

RESEARCHER_PROMPT_TEMPLATE = """
ROLE: You do exactly one thing: analyze search results and build a blog outline with grounding data.

INPUT:
- topic: {topic}
- target_keyword: {target_keyword}
- search_results: {search_results}

RULES:
- Extract ONLY facts and text present in search_results. Do not invent any claim.
- Identify serp_gaps: topics the search results failed to cover well or at all.
- Each section must have 3-6 key_points derived directly from search_results.
- source_snippets must be SHORT real excerpts (max 40 words each) copied from search_results.
- word_target per section: between 400 and 800 words.
- Create between 6 and 10 sections. First section is always introduction, last is always conclusion.
- The most important rule: source_snippets must be verbatim short excerpts from the provided search_results, not paraphrases.

OUTPUT: Return ONLY valid JSON matching this exact schema. No prose. No markdown fences. No explanation.
{schema}

EXAMPLE of one correct section in the outline:
{example}
"""

_GROUNDING_SCHEMA_HINT = json.dumps(
    {
        "title": "string",
        "target_keyword": "string",
        "outline": [
            {
                "heading": "string",
                "intent": "string",
                "key_points": ["string", "string", "string"],
                "source_snippets": ["verbatim excerpt <= 40 words", "..."],
                "word_target": 600,
            }
        ],
        "serp_gaps": ["string", "string"],
    },
    indent=2,
)

_SECTION_EXAMPLE = json.dumps(
    {
        "heading": "Why chunk size silently breaks retrieval",
        "intent": "Show the reader the single highest-leverage RAG knob and prove it with a concrete number.",
        "key_points": [
            "512-token chunks beat 1024 on retrieval precision",
            "overlap of 50 tokens preserves context across boundaries",
            "embedding models cap effective chunk length",
        ],
        "source_snippets": [
            "cutting chunk size from 1024 to 512 tokens lifted recall@5 from 0.61 to 0.78",
            "an overlap window of ~50 tokens avoided splitting mid-sentence",
        ],
        "word_target": 600,
    },
    indent=2,
)


class ResearcherAgent:
    def __init__(self, llm_provider: str):
        self.llm_provider = llm_provider
        self.llm = make_llm(llm_provider, RESEARCHER_TEMPERATURE, max_tokens=8000)

    async def run(self, topic: str, target_keyword: str) -> GroundingPack:
        # 1. Multi-source search (async, concurrent across all sources)
        engine = get_research_engine()
        try:
            aggregated = await engine.search(topic, max_results_per_source=5)
        except Exception as exc:
            logger.error("ResearchEngine.search failed: %s", exc)
            raise ResearcherFailedError(f"Research search failed: {exc}") from exc

        items = aggregated.items[:_MAX_PAGES]

        # 2. Fetch the top result pages concurrently and strip them to text
        pages = await self._fetch_pages([it.url for it in items])

        # 3. Build the search_results string fed to the model
        blocks: list[str] = []
        for idx, it in enumerate(items, 1):
            page_text = pages.get(it.url) or it.summary or ""
            page_text = page_text[:_PAGE_CHARS].strip()
            blocks.append(
                f"[{idx}] {it.title}\nURL: {it.url}\nSOURCE: {it.source}\nTEXT: {page_text}"
            )
        search_results = "\n\n".join(blocks) if blocks else "No external results were retrievable."

        prompt = RESEARCHER_PROMPT_TEMPLATE.format(
            topic=topic,
            target_keyword=target_keyword,
            search_results=search_results,
            schema=_GROUNDING_SCHEMA_HINT,
            example=_SECTION_EXAMPLE,
        )

        # 4-7. Validate-with-retry, then guarantee the keyword/title are sane
        try:
            pack: GroundingPack = await call_llm_with_retry(
                self.llm, prompt, GroundingPack,
                temperature=RESEARCHER_TEMPERATURE, max_retries=3, agent_name="Researcher",
            )
        except Exception as exc:
            raise ResearcherFailedError(str(exc)) from exc

        if not pack.outline:
            raise ResearcherFailedError("Researcher returned an empty outline.")
        if not pack.target_keyword:
            pack.target_keyword = target_keyword
        if not pack.title:
            pack.title = topic
        return pack

    async def _fetch_pages(self, urls: list[str]) -> dict[str, str]:
        """Fetch each URL with aiohttp (10s timeout) and strip to text. Failures map to ''."""
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not installed — falling back to research summaries only")
            return {}

        results: dict[str, str] = {}
        timeout = aiohttp.ClientTimeout(total=_FETCH_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout, headers=_FETCH_HEADERS) as session:

            async def _one(url: str) -> tuple[str, str]:
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            return url, ""
                        html = await resp.text(errors="ignore")
                        return url, strip_html(html)
                except Exception as exc:
                    logger.debug("Page fetch failed for %s: %s", url, exc)
                    return url, ""

            for url, text in await asyncio.gather(*[_one(u) for u in urls], return_exceptions=False):
                results[url] = text
        return results
