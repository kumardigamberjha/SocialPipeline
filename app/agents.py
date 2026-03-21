"""
Agent factory functions.

Each function creates a single CrewAI Agent.
`create_all_agents()` returns the complete agent roster.
"""

from crewai import Agent, LLM

from app.tools.custom import (
    web_search_tool,
    file_reader_tool,
    code_execution_tool,
    db_query_tool,
    api_request_tool,
    generate_instagram_image_tool,
)

# ── Individual agent factories ───────────────────────────────────────────────


def create_trend_agent(llm: LLM) -> Agent:
    return Agent(
        role="Senior Tech Trend Analyst",
        goal="Find high viral developer topics",
        backstory=(
            "You are a senior AI content strategist. "
            "You know YouTube, LinkedIn, and Twitter algorithms. "
            "You always choose topics that can go viral. "
            "Return precise, actionable answers."
        ),
        llm=llm,
        tools=[web_search_tool],
        verbose=True,
    )


def create_script_agent(llm: LLM) -> Agent:
    return Agent(
        role="YouTube Script Writer",
        goal="Write engaging, well-structured YouTube scripts",
        backstory=(
            "You are a professional script writer.\n\n"
            "Rules:\n"
            "- Hook the viewer in the first line\n"
            "- Keep the energy engaging throughout\n"
            "- Add a clear CTA at the end\n"
            "- Use storytelling to maintain attention"
        ),
        llm=llm,
        verbose=True,
    )


def create_seo_agent(llm: LLM) -> Agent:
    return Agent(
        role="SEO Specialist",
        goal="Generate high-ranking SEO elements for YouTube content",
        backstory=(
            "Expert in YouTube SEO. "
            "Generate optimized titles, descriptions, and tags. "
            "Focus on ranking keywords and search intent."
        ),
        llm=llm,
        tools=[web_search_tool],
        verbose=True,
    )


def create_thumbnail_agent(llm: LLM) -> Agent:
    return Agent(
        role="Thumbnail Designer",
        goal="Create clickable thumbnail ideas with high CTR potential",
        backstory=(
            "Expert YouTube thumbnail designer. "
            "Design high CTR thumbnails. "
            "Use curiosity, emotion, and bold visuals."
        ),
        llm=llm,
        verbose=True,
    )


def create_shorts_agent(llm: LLM) -> Agent:
    return Agent(
        role="Shorts Script Writer",
        goal="Write viral short-form video scripts under 60 seconds",
        backstory=(
            "Short-form video expert. "
            "Hook the viewer fast. "
            "Keep scripts concise and under 60 seconds."
        ),
        llm=llm,
        verbose=True,
    )


def create_linkedin_agent(llm: LLM) -> Agent:
    return Agent(
        role="LinkedIn Content Creator",
        goal="Write viral, professional LinkedIn posts",
        backstory=(
            "LinkedIn growth expert. "
            "Write professional yet engaging posts. "
            "Use storytelling, hooks, and hashtags strategically."
        ),
        llm=llm,
        verbose=True,
    )


def create_twitter_agent(llm: LLM) -> Agent:
    return Agent(
        role="Twitter Thread Writer",
        goal="Write compelling Twitter threads that drive engagement",
        backstory=(
            "Twitter growth expert. "
            "Craft threads that are informative, punchy, and shareable."
        ),
        llm=llm,
        verbose=True,
    )


def create_blog_agent(llm: LLM) -> Agent:
    return Agent(
        role="Technical Blogger",
        goal="Write comprehensive, developer-focused blog articles",
        backstory=(
            "Writes in-depth developer blog posts. "
            "Focuses on clarity, code examples, and practical value."
        ),
        llm=llm,
        tools=[file_reader_tool, code_execution_tool],
        verbose=True,
    )


def create_course_agent(llm: LLM) -> Agent:
    return Agent(
        role="Course Architect",
        goal="Design structured programming course outlines",
        backstory=(
            "Designs programming courses with clear modules, "
            "learning objectives, and progressive difficulty."
        ),
        llm=llm,
        verbose=True,
    )


def create_idea_agent(llm: LLM) -> Agent:
    return Agent(
        role="Creative Content Strategist",
        goal="Generate viral content ideas across platforms",
        backstory=(
            "Expert in viral content strategy. "
            "Generates creative, data-informed ideas that resonate with developers."
        ),
        llm=llm,
        tools=[web_search_tool, api_request_tool, db_query_tool],
        verbose=True,
    )


def create_instagram_image_agent(llm: LLM) -> Agent:
    return Agent(
        role="Instagram Image Designer",
        goal="Design and generate the visual image for an Instagram post using ComfyUI.",
        backstory=(
            "You are an expert Instagram visual designer. "
            "You know how to choose the right palette, layout, and style hints to generate an image that matches the given topic."
        ),
        llm=llm,
        tools=[generate_instagram_image_tool],
        verbose=True,
    )


# ── Aggregate factory ────────────────────────────────────────────────────────

_AGENT_FACTORIES = [
    create_trend_agent,
    create_script_agent,
    create_seo_agent,
    create_thumbnail_agent,
    create_shorts_agent,
    create_linkedin_agent,
    create_twitter_agent,
    create_blog_agent,
    create_course_agent,
    create_idea_agent,
]


def create_all_agents(llm: LLM) -> list[Agent]:
    """Instantiate and return all agents with the given LLM."""
    return [factory(llm) for factory in _AGENT_FACTORIES]
