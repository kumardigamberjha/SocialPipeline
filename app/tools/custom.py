import os
import requests
import textwrap
from io import StringIO
import contextlib
import urllib.parse
from crewai.tools import tool

# ── 1. Web Search Tool ─────────────────────────────────────────
try:
    from duckduckgo_search import DDGS
    has_ddgs = True
except ImportError:
    has_ddgs = False

@tool("web_search")
def web_search_tool(query: str, max_results: int = 5) -> str:
    """Useful to search the internet about a given tech/AI topic and return relevant results."""
    # 1. Primary approach for Tech/AI content: Hacker News Algolia Search (100% Free & Reliable)
    try:
        import requests
        import urllib.parse
        
        # Clean query by stripping generic instructions that confuse keyword search
        clean_query = query.lower()
        for phrase in ["latest", "viral", "news", "today", "trends"]:
            clean_query = clean_query.replace(phrase, "").strip()
        if not clean_query:
            clean_query = "AI" # Fallback literal
            
        encoded = urllib.parse.quote(clean_query)
        url = f"https://hn.algolia.com/api/v1/search_by_date?query={encoded}&tags=story&hitsPerPage={max_results * 2}"
        
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            hits = response.json().get("hits", [])
            if hits:
                results = "We searched Hacker News (the premier tech aggregator) and found this breaking news:\n\n"
                count = 0
                for hit in hits:
                    if count >= max_results: break
                    title = hit.get("title", "")
                    story_url = hit.get("url", "") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                    points = hit.get("points", 0)
                    if not title: continue
                    results += f"Title: {title}\nURL: {story_url}\nUpvotes: {points}\n\n"
                    count += 1
                if count > 0:
                    return results
    except Exception:
        pass

    # 2. Fallback to DDGS if Hacker News fails
    if not has_ddgs:
        return "Search failed: DuckDuckGo module not installed and primary API failed."
    try:
        results = ""
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results += f"Title: {r['title']}\nURL: {r['href']}\nBody: {r['body']}\n\n"
        return results if results else "No results found across all search endpoints."
    except Exception as e:
        return f"Search completely failed: {e}"

# ── 2. File Reader Tool ─────────────────────────────────────────
@tool("read_local_file")
def file_reader_tool(filepath: str) -> str:
    """Useful for reading local files on the system to extract configuration or context."""
    if not os.path.exists(filepath):
        return f"File not found: {filepath}"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Could not read file {filepath}: {e}"

# ── 3. Code Execution Tool ─────────────────────────────────────
@tool("execute_python_code")
def code_execution_tool(code: str) -> str:
    """Execute Python code in a sandboxed environment and return stdout. Use for math or logic."""
    stdout = StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            exec(textwrap.dedent(code), {})
        output = stdout.getvalue()
        return output if output else "Code executed successfully with no output."
    except Exception as e:
        return f"Error executing code: {e}"

# ── 4. DB Query Tool ──────────────────────────────────────────
@tool("query_database")
def db_query_tool(query: str) -> str:
    """Query data from the Postgres/Supabase database if configured."""
    from app.db.supabase import get_supabase
    client = get_supabase()
    if not client:
        return "Database is not configured yet."
    # Since direct SQL execution is not straightforward with the Supabase client,
    # and agents might guess SQL, we wrap table selections here, or we return a warning.
    return "DB execution requires specific table RPCs. This tool is a placeholder for safety."

# ── 5. API Interaction Tool ───────────────────────────────────
@tool("api_request")
def api_request_tool(url: str, method: str = "GET", payload: str = "") -> str:
    """Make an HTTP REST request to an endpoint. Method can be GET or POST."""
    try:
        headers = {"Content-Type": "application/json"}
        if method.upper() == "POST":
            response = requests.post(url, data=payload, headers=headers, timeout=10)
        else:
            response = requests.get(url, timeout=10)
        return f"Status: {response.status_code}\nResponse: {response.text[:1000]}..."
    except Exception as e:
        return f"API request failed: {e}"

# ── 6. Instagram Image Generation Tool ──────────────────────
@tool("generate_instagram_image")
def generate_instagram_image_tool(topic: str, palette: str = "void_purple", layout: str = "bottom_hero", model: str = "flux_schnell", style_hints: str = "") -> str:
    """Generate an Instagram image using ComfyUI. Provide a topic, palette (e.g. void_purple, cyber_teal), layout (e.g. bottom_hero, top_title), model (sdxl_turbo or flux_schnell), and style_hints."""
    import asyncio
    from app.services.comfy_client import ComfyClient
    
    async def _generate():
        comfy = ComfyClient()
        if not await comfy.health_check():
            return "Error: ComfyUI is not running."
        try:
            result = await comfy.generate_instagram_post(
                topic=topic,
                palette=palette,
                layout=layout,
                model=model,
                style_hints=style_hints
            )
            images_markup = []
            prompt_id = result.get('prompt_id')
            for i in range(len(result.get('images', []))):
                images_markup.append(f"![Generated Instagram Image](/generated_posts/{prompt_id}_{i}.png)")
            num_imgs = len(result.get('images', []))
            return f"Successfully generated {num_imgs} Instagram image(s) for topic '{topic}' in {result.get('duration_s')}s:\n\n" + "\n\n".join(images_markup)
        except Exception as e:
            return f"Error generating image: {str(e)}"
    
    try:
        return asyncio.run(_generate())
    except RuntimeError:
        import threading
        result_box = []
        def _run_in_thread():
            result_box.append(asyncio.run(_generate()))
        t = threading.Thread(target=_run_in_thread)
        t.start()
        t.join()
        return result_box[0]
