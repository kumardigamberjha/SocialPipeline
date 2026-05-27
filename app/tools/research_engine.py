"""
Multi-Source Research Engine for Wings of AI.

Searches ALL of these sources concurrently using asyncio.gather():
    1. DuckDuckGo News Search
    2. Hacker News Algolia API
    3. Reddit JSON API (r/MachineLearning, r/artificial, r/programming, r/webdev, r/LocalLLaMA)
    4. DEV.to API
    5. ArXiv API (for AI research papers)
    6. GitHub Trending (HTML scrape filtered by topic keywords)
    7. Product Hunt (website search)

Features:
    - All source fetches run concurrently via asyncio.gather()
    - Deduplication by URL and title similarity (difflib.SequenceMatcher, threshold 0.85)
    - Composite scoring: recency (48h=+3, 7d=+1), engagement (upvotes/comments), source authority
    - Returns top 15 results sorted by composite score
    - Results cached in SQLite for 6 hours via content_tracker

Usage:
    from app.tools.research_engine import ResearchEngine

    engine = ResearchEngine()
    results = await engine.search("AI agents", max_results_per_source=5)
    formatted = engine.format_results(results)

    # Synchronous convenience:
    from app.tools.research_engine import run_multi_source_search
    text = run_multi_source_search("AI agents")
"""

import asyncio
import difflib
import hashlib
import logging
import math
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

REQUEST_TIMEOUT = 12  # seconds per source

REDDIT_SUBREDDITS = [
    "MachineLearning",
    "artificial",
    "programming",
    "webdev",
    "LocalLLaMA",
]

REDDIT_USER_AGENT = "python:wings-of-ai-research:v1.0.0 (by /u/nexus_wings)"

ARXIV_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# Source authority weights — higher = more trusted for tech content
SOURCE_AUTHORITY = {
    "Hacker News":      5,
    "ArXiv":            5,
    "Reddit":           3,
    "GitHub Trending":  4,
    "DEV.to":           3,
    "DuckDuckGo News":  2,
    "DuckDuckGo":       1,
    "Product Hunt":     3,
}

DEDUP_TITLE_THRESHOLD = 0.85  # SequenceMatcher ratio for fuzzy title matching
TOP_N_RESULTS = 15


# ── Data Structures ──────────────────────────────────────────────────────────


@dataclass
class ResearchResult:
    """A single research finding from any source."""
    title: str
    url: str
    summary: str
    source: str
    score: float = 0.0
    published_at: str = ""
    # Internal fields used before final scoring
    raw_engagement: int = 0
    author: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class AggregatedResults:
    """Aggregated, deduplicated, scored results from all sources."""
    items: list[ResearchResult] = field(default_factory=list)
    sources_succeeded: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    total_raw: int = 0  # before dedup


# ── Research Engine ──────────────────────────────────────────────────────────


class ResearchEngine:
    """
    Multi-source research aggregator. All source fetches run concurrently
    via asyncio.gather(). Results are deduplicated and scored by a composite
    of recency, engagement, and source authority.

    Results are cached in SQLite for 6 hours to avoid redundant API calls.
    """

    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self.timeout = timeout

    async def search(self, query: str, max_results_per_source: int = 5) -> AggregatedResults:
        """
        Search all sources concurrently and return top 15 scored results.
        Checks SQLite cache first; if fresh results exist, returns those.

        Args:
            query:  The topic or search query.
            max_results_per_source: Max items to collect from each source.

        Returns:
            AggregatedResults with deduplicated, scored items.
        """
        start = time.perf_counter()
        clean_query = self._clean_query(query)
        query_hash = hashlib.sha256(clean_query.lower().encode()).hexdigest()[:32]

        # Check SQLite cache
        cached = self._get_cached_results(query_hash)
        if cached is not None:
            elapsed = round(time.perf_counter() - start, 2)
            logger.info("Research cache HIT for query=%r (%d items, %.2fs)", clean_query[:40], len(cached.items), elapsed)
            cached.duration_seconds = elapsed
            return cached

        # Define all source coroutines
        source_coros = {
            "Hacker News":     self._search_hackernews(clean_query, max_results_per_source),
            "DuckDuckGo":      self._search_duckduckgo(clean_query, max_results_per_source),
            "Reddit":          self._search_reddit(clean_query, max_results_per_source),
            "DEV.to":          self._search_devto(clean_query, max_results_per_source),
            "ArXiv":           self._search_arxiv(clean_query, max_results_per_source),
            "GitHub Trending": self._search_github_trending(clean_query, max_results_per_source),
            "Product Hunt":    self._search_producthunt(clean_query, max_results_per_source),
        }

        source_names = list(source_coros.keys())
        coro_list = list(source_coros.values())

        # Run ALL sources concurrently
        gathered = await asyncio.gather(*coro_list, return_exceptions=True)

        results = AggregatedResults()
        all_items: list[ResearchResult] = []

        for name, outcome in zip(source_names, gathered):
            if isinstance(outcome, Exception):
                results.sources_failed.append(name)
                logger.warning("✗ %s failed: %s", name, outcome)
            elif outcome:
                all_items.extend(outcome)
                results.sources_succeeded.append(name)
                logger.info("✓ %s returned %d items", name, len(outcome))
            else:
                results.sources_failed.append(name)
                logger.warning("✗ %s returned 0 items", name)

        results.total_raw = len(all_items)

        # Deduplicate
        deduped = self._deduplicate(all_items)

        # Score
        scored = self._score_results(deduped)

        # Sort by composite score descending, take top N
        scored.sort(key=lambda x: x.score, reverse=True)
        results.items = scored[:TOP_N_RESULTS]
        results.duration_seconds = round(time.perf_counter() - start, 2)

        # Cache to SQLite
        self._cache_results(query_hash, results)

        logger.info(
            "Research complete: %d raw → %d deduped → %d returned from %d/%d sources in %.2fs",
            results.total_raw,
            len(deduped),
            len(results.items),
            len(results.sources_succeeded),
            len(source_coros),
            results.duration_seconds,
        )
        return results

    def format_results(self, results: AggregatedResults, max_total: int = 15) -> str:
        """
        Format AggregatedResults into a structured text block suitable for
        injecting into LLM context.
        """
        if not results.items:
            return "Research returned no results across all sources."

        lines = [
            f"=== MULTI-SOURCE RESEARCH ({len(results.items)} findings from "
            f"{', '.join(results.sources_succeeded)}) ===\n",
        ]

        for i, item in enumerate(results.items[:max_total], 1):
            entry = f"{i}. [{item.title}]({item.url})"
            entry += f"  [source: {item.source}, score: {item.score:.1f}]"
            if item.published_at:
                entry += f"  [published: {item.published_at}]"
            if item.summary:
                entry += f"\n   {item.summary[:200]}"
            if item.tags:
                entry += f"\n   Tags: {', '.join(item.tags[:5])}"
            lines.append(entry)

        lines.append(f"\n=== END RESEARCH ({len(results.items)} items, {results.duration_seconds}s) ===")

        if results.sources_failed:
            lines.append(f"(Sources unavailable: {', '.join(results.sources_failed)})")

        return "\n".join(lines)

    # ── SQLite Cache Integration ─────────────────────────────────────────

    @staticmethod
    def _get_cached_results(query_hash: str) -> Optional[AggregatedResults]:
        """Check SQLite cache for non-expired results."""
        try:
            from app.db.content_tracker import get_cache
            cached = get_cache(query_hash)
            if cached is None:
                return None

            items = [ResearchResult(**item) for item in cached.get("items", [])]
            return AggregatedResults(
                items=items,
                sources_succeeded=cached.get("sources_succeeded", ["cache"]),
                sources_failed=[],
                total_raw=len(items),
            )
        except Exception as e:
            logger.debug("Cache read failed (non-fatal): %s", e)
            return None

    @staticmethod
    def _cache_results(query_hash: str, results: AggregatedResults):
        """Write results to SQLite cache with 6-hour TTL."""
        try:
            from app.db.content_tracker import set_cache
            cache_data = {
                "items": [asdict(item) for item in results.items],
                "sources_succeeded": results.sources_succeeded,
            }
            set_cache(query_hash, cache_data, ttl_hours=6)
        except Exception as e:
            logger.debug("Cache write failed (non-fatal): %s", e)

    # ── Deduplication ────────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(items: list[ResearchResult]) -> list[ResearchResult]:
        """
        Remove duplicates by exact URL match and fuzzy title similarity
        (difflib.SequenceMatcher, threshold 0.85).

        When duplicates are found, keep the one with higher raw_engagement.
        """
        seen_urls: set[str] = set()
        kept: list[ResearchResult] = []

        for item in items:
            normalized_url = item.url.rstrip("/").lower()

            if normalized_url in seen_urls:
                continue

            is_dupe = False
            for existing in kept:
                ratio = difflib.SequenceMatcher(
                    None,
                    item.title.lower(),
                    existing.title.lower(),
                ).ratio()
                if ratio >= DEDUP_TITLE_THRESHOLD:
                    if item.raw_engagement > existing.raw_engagement:
                        kept.remove(existing)
                        seen_urls.discard(existing.url.rstrip("/").lower())
                    else:
                        is_dupe = True
                    break

            if not is_dupe:
                seen_urls.add(normalized_url)
                kept.append(item)

        return kept

    # ── Scoring ──────────────────────────────────────────────────────────

    @staticmethod
    def _score_results(items: list[ResearchResult]) -> list[ResearchResult]:
        """
        Compute a composite score for each result:
            - Recency:    published within 48h = +3pts, within 7d = +1pt
            - Engagement: log-scaled from raw upvotes/comments
            - Authority:  source-level trust weight
        """
        now = datetime.now(timezone.utc)
        cutoff_48h = now - timedelta(hours=48)
        cutoff_7d = now - timedelta(days=7)

        for item in items:
            score = 0.0

            # 1. Source authority
            authority = SOURCE_AUTHORITY.get(item.source, 1)
            for key, val in SOURCE_AUTHORITY.items():
                if key in item.source:
                    authority = val
                    break
            score += authority

            # 2. Recency bonus
            if item.published_at:
                pub_dt = _parse_date(item.published_at)
                if pub_dt:
                    if pub_dt >= cutoff_48h:
                        score += 3.0
                    elif pub_dt >= cutoff_7d:
                        score += 1.0

            # 3. Engagement (log-scaled to avoid extreme outliers dominating)
            if item.raw_engagement > 0:
                score += min(math.log2(item.raw_engagement + 1), 10.0)

            item.score = round(score, 2)

        return items

    # ── Query Cleaning ───────────────────────────────────────────────────

    @staticmethod
    def _clean_query(query: str) -> str:
        """Strip instructional fluff so API searches get clean keywords."""
        if "LATEST AI TRENDS:" in query:
            return "latest AI trends"

        noise_phrases = [
            "use your web search tool to find",
            "search the internet about",
            "find the most breaking",
            "pick the absolute",
            "perform a deep trend analysis",
            "base every single subsequent",
            "critical:",
            "use short specific keywords like",
        ]
        cleaned = query.lower()
        for phrase in noise_phrases:
            cleaned = cleaned.replace(phrase, " ")

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) < 3:
            cleaned = " ".join(query.split()[:10])

        return cleaned

    # ── Source: Hacker News Algolia ───────────────────────────────────────

    async def _search_hackernews(self, query: str, max_results: int) -> list[ResearchResult]:
        def _fetch():
            encoded = urllib.parse.quote(query)
            url = (
                f"https://hn.algolia.com/api/v1/search_by_date"
                f"?query={encoded}&tags=story&hitsPerPage={max_results * 2}"
            )
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])

            items = []
            for hit in hits[:max_results]:
                title = hit.get("title", "")
                if not title:
                    continue
                story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                created = hit.get("created_at", "")
                items.append(ResearchResult(
                    title=title,
                    url=story_url,
                    source="Hacker News",
                    raw_engagement=hit.get("points", 0) or 0,
                    author=hit.get("author", ""),
                    summary=f"{hit.get('num_comments', 0)} comments",
                    published_at=created[:10] if created else "",
                ))
            return items

        return await asyncio.to_thread(_fetch)

    # ── Source: DuckDuckGo ────────────────────────────────────────────────

    async def _search_duckduckgo(self, query: str, max_results: int) -> list[ResearchResult]:
        def _fetch():
            try:
                from ddgs import DDGS
            except ImportError:
                logger.warning("ddgs not installed, skipping DuckDuckGo")
                return []

            items = []
            with DDGS() as ddgs:
                try:
                    news_results = list(ddgs.news(query, max_results=max_results))
                    for r in news_results:
                        items.append(ResearchResult(
                            title=r.get("title", ""),
                            url=r.get("url", ""),
                            source="DuckDuckGo News",
                            summary=r.get("body", "")[:200],
                            published_at=r.get("date", "")[:10] if r.get("date") else "",
                        ))
                except Exception:
                    for r in ddgs.text(query, max_results=max_results):
                        items.append(ResearchResult(
                            title=r.get("title", ""),
                            url=r.get("href", ""),
                            source="DuckDuckGo",
                            summary=r.get("body", "")[:200],
                        ))
            return items

        return await asyncio.to_thread(_fetch)

    # ── Source: Reddit ────────────────────────────────────────────────────

    async def _search_reddit(self, query: str, max_results: int) -> list[ResearchResult]:
        def _fetch():
            items = []
            per_sub = max(1, max_results // len(REDDIT_SUBREDDITS))
            session = requests.Session()
            session.headers.update({"User-Agent": REDDIT_USER_AGENT})

            for subreddit in REDDIT_SUBREDDITS:
                try:
                    encoded = urllib.parse.quote(query)
                    url = (
                        f"https://www.reddit.com/r/{subreddit}/search.json"
                        f"?q={encoded}&sort=relevance&t=week&restrict_sr=1&limit={per_sub}"
                    )
                    resp = session.get(url, timeout=self.timeout)
                    if resp.status_code == 429:
                        logger.warning("Reddit rate limited on r/%s, skipping", subreddit)
                        continue
                    resp.raise_for_status()

                    data = resp.json().get("data", {}).get("children", [])
                    for post in data:
                        d = post.get("data", {})
                        title = d.get("title", "")
                        if not title:
                            continue

                        created_utc = d.get("created_utc", 0)
                        published = ""
                        if created_utc:
                            published = datetime.fromtimestamp(
                                created_utc, tz=timezone.utc
                            ).strftime("%Y-%m-%d")

                        items.append(ResearchResult(
                            title=title,
                            url=f"https://reddit.com{d.get('permalink', '')}",
                            source=f"Reddit r/{subreddit}",
                            raw_engagement=d.get("score", 0),
                            author=d.get("author", ""),
                            summary=d.get("selftext", "")[:200],
                            tags=[f"r/{subreddit}"],
                            published_at=published,
                        ))
                except Exception as e:
                    logger.debug("Reddit r/%s search failed: %s", subreddit, e)

            items.sort(key=lambda x: x.raw_engagement, reverse=True)
            return items[:max_results]

        return await asyncio.to_thread(_fetch)

    # ── Source: DEV.to ───────────────────────────────────────────────────

    async def _search_devto(self, query: str, max_results: int) -> list[ResearchResult]:
        def _fetch():
            tag = self._extract_primary_tag(query)
            url = f"https://dev.to/api/articles?tag={tag}&top=7&per_page={max_results}"

            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            articles = resp.json()

            items = []
            for article in articles[:max_results]:
                published = article.get("published_at", "")
                items.append(ResearchResult(
                    title=article.get("title", ""),
                    url=article.get("url", ""),
                    source="DEV.to",
                    raw_engagement=article.get("positive_reactions_count", 0),
                    author=article.get("user", {}).get("username", ""),
                    summary=article.get("description", "")[:200],
                    tags=article.get("tag_list", []),
                    published_at=published[:10] if published else "",
                ))
            return items

        return await asyncio.to_thread(_fetch)

    # ── Source: ArXiv ────────────────────────────────────────────────────

    async def _search_arxiv(self, query: str, max_results: int) -> list[ResearchResult]:
        def _fetch():
            encoded = urllib.parse.quote(query)
            url = (
                f"http://export.arxiv.org/api/query"
                f"?search_query=all:{encoded}&start=0&max_results={max_results}"
                f"&sortBy=submittedDate&sortOrder=descending"
            )
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()

            root = ET.fromstring(resp.text)
            items = []

            for entry in root.findall("atom:entry", ARXIV_NAMESPACES):
                title_el = entry.find("atom:title", ARXIV_NAMESPACES)
                summary_el = entry.find("atom:summary", ARXIV_NAMESPACES)
                link_el = entry.find("atom:id", ARXIV_NAMESPACES)
                published_el = entry.find("atom:published", ARXIV_NAMESPACES)

                title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""
                if not title:
                    continue

                summary_text = ""
                if summary_el is not None and summary_el.text:
                    summary_text = summary_el.text.strip().replace("\n", " ")[:200]

                arxiv_url = link_el.text.strip() if link_el is not None and link_el.text else ""
                published = published_el.text.strip()[:10] if published_el is not None and published_el.text else ""

                authors = []
                for author_el in entry.findall("atom:author", ARXIV_NAMESPACES):
                    name_el = author_el.find("atom:name", ARXIV_NAMESPACES)
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                tags = []
                for cat_el in entry.findall("atom:category", ARXIV_NAMESPACES):
                    term = cat_el.get("term", "")
                    if term:
                        tags.append(term)

                items.append(ResearchResult(
                    title=title,
                    url=arxiv_url,
                    source="ArXiv",
                    summary=summary_text,
                    author=", ".join(authors[:3]),
                    published_at=published,
                    tags=tags[:5],
                ))

            return items

        return await asyncio.to_thread(_fetch)

    # ── Source: GitHub Trending ───────────────────────────────────────────

    async def _search_github_trending(self, query: str, max_results: int) -> list[ResearchResult]:
        def _fetch():
            url = "https://github.com/trending?spoken_language_code=en"
            resp = requests.get(url, timeout=self.timeout, headers={
                "Accept": "text/html",
                "User-Agent": REDDIT_USER_AGENT,
            })
            resp.raise_for_status()

            try:
                from bs4 import BeautifulSoup
            except ImportError:
                logger.warning("beautifulsoup4 not installed, skipping GitHub Trending")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.select("article.Box-row")

            query_words = set(query.lower().split())
            items = []

            for article in articles:
                h2 = article.select_one("h2 a")
                if not h2:
                    continue
                repo_path = h2.get("href", "").strip("/")
                repo_name = repo_path.split("/")[-1] if "/" in repo_path else repo_path

                p = article.select_one("p")
                description = p.get_text(strip=True) if p else ""

                lang_span = article.select_one("[itemprop='programmingLanguage']")
                language = lang_span.get_text(strip=True) if lang_span else ""

                stars_today = ""
                star_spans = article.select("span.d-inline-block.float-sm-right")
                if star_spans:
                    stars_today = star_spans[-1].get_text(strip=True)

                star_links = article.select("a.Link--muted.d-inline-block.mr-3")
                total_stars = 0
                if star_links:
                    star_text = star_links[0].get_text(strip=True).replace(",", "")
                    try:
                        total_stars = int(star_text)
                    except ValueError:
                        pass

                text_to_match = f"{repo_name} {description}".lower()
                if query_words and not any(word in text_to_match for word in query_words):
                    continue

                items.append(ResearchResult(
                    title=repo_path,
                    url=f"https://github.com/{repo_path}",
                    source="GitHub Trending",
                    raw_engagement=total_stars,
                    summary=description[:200],
                    tags=[language] if language else [],
                    published_at=stars_today,
                ))

                if len(items) >= max_results:
                    break

            return items

        return await asyncio.to_thread(_fetch)

    # ── Source: Product Hunt ──────────────────────────────────────────────

    async def _search_producthunt(self, query: str, max_results: int) -> list[ResearchResult]:
        def _fetch():
            encoded = urllib.parse.quote(query)
            url = f"https://www.producthunt.com/search?q={encoded}"

            resp = requests.get(url, timeout=self.timeout, headers={
                "Accept": "text/html",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            })
            resp.raise_for_status()

            try:
                from bs4 import BeautifulSoup
            except ImportError:
                logger.warning("beautifulsoup4 not installed, skipping Product Hunt")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            items = []

            for link in soup.select("a[href*='/posts/']"):
                title = link.get_text(strip=True)
                href = link.get("href", "")

                if not title or len(title) < 3:
                    continue

                full_url = href if href.startswith("http") else f"https://www.producthunt.com{href}"

                if any(item.url == full_url for item in items):
                    continue

                items.append(ResearchResult(
                    title=title[:100],
                    url=full_url,
                    source="Product Hunt",
                    summary="",
                ))

                if len(items) >= max_results:
                    break

            return items

        return await asyncio.to_thread(_fetch)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _extract_primary_tag(query: str) -> str:
        """Extract a single short tag suitable for DEV.to API from a query."""
        tag_map = {
            "machine learning": "machinelearning",
            "deep learning": "deeplearning",
            "large language model": "llm",
            "natural language processing": "nlp",
            "computer vision": "computervision",
            "web development": "webdev",
            "artificial intelligence": "ai",
            "open source": "opensource",
        }

        lower = query.lower()
        for phrase, tag in tag_map.items():
            if phrase in lower:
                return tag

        stop_words = {"the", "a", "an", "in", "on", "for", "with", "and", "or", "latest", "trends", "today"}
        words = [w for w in lower.split() if w not in stop_words and len(w) > 2]
        return words[0] if words else "ai"


# ── Date parsing helper ──────────────────────────────────────────────────────

def _parse_date(date_str: str) -> Optional[datetime]:
    """Best-effort parse of a date string into a timezone-aware datetime."""
    if not date_str:
        return None

    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(date_str[:26], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return None


# ── Module-level convenience ─────────────────────────────────────────────────

_engine: Optional[ResearchEngine] = None


def get_research_engine() -> ResearchEngine:
    """Return a module-level singleton ResearchEngine instance."""
    global _engine
    if _engine is None:
        _engine = ResearchEngine()
    return _engine


def run_multi_source_search(query: str, max_results_per_source: int = 5) -> str:
    """
    Synchronous convenience function: run the async multi-source search
    and return formatted text. Safe to call from sync code (Celery workers,
    CrewAI callbacks, etc.) — creates its own event loop if needed.

    This is the drop-in replacement for the old run_web_search() function.
    """
    engine = get_research_engine()

    async def _run():
        return await engine.search(query, max_results_per_source=max_results_per_source)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run())
            results = future.result(timeout=30)
    else:
        results = asyncio.run(_run())

    return engine.format_results(results)
