"""
Task factory functions.

Each function creates a single CrewAI Task bound to its agent.
`create_all_tasks()` builds the full task list in pipeline order.

Style guides from app.services.style_guide are injected into content-specific
tasks so each agent follows the exact writing DNA for its platform.
"""

from crewai import Agent, Task

from app.services.style_guide import (
    YOUTUBE_SCRIPT_STYLE,
    LINKEDIN_STYLE,
    TWITTER_STYLE,
    LONGFORM_STYLE,
)


def _build_prompt(topic: str) -> str:
    """Build the shared user prompt injected into every task."""
    return (
        f"Topic: {topic}\n\n"
        "Create high-quality developer content.\n"
        "Focus on AI, Python, automation, and real-world use.\n\n"
        "CRITICAL INSTRUCTION: You are operating in a sequential pipeline. You will see previous outputs in your context.\n"
        "IGNORE any previous outputs. DO NOT copy, summarize, or repeat them (especially the YouTube script).\n"
        "You MUST generate entirely NEW content tailored strictly to your specific role and task description."
    )


# ── Individual task factories ────────────────────────────────────────────────


def create_trend_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nFind 5 viral topics related to this theme.",
        expected_output="A list of 5 trending, viral developer topics with brief justifications.",
        agent=agent,
        context=[],
    )


def create_script_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=(
            f"Write a complete YouTube script about: {prompt}\n\n"
            f"{YOUTUBE_SCRIPT_STYLE}\n\n"
            "ADDITIONAL REQUIREMENTS:\n"
            "- Script length: 7-9 minutes when read aloud (~1,400-1,800 words)\n"
            "- Include [VISUAL CUE: description] tags for B-roll and screen recordings\n"
            "- Include [B-ROLL: description] tags for supplementary footage\n"
            "- Mark energy levels: [ENERGY: HIGH] for hype sections, [ENERGY: CALM] for explanations\n"
            "- Every code demo must have a [SCREEN RECORDING] tag before it\n"
            "- The hook must be deliverable in under 10 seconds\n"
            "- Include at least 2 pattern interrupts (questions, visual changes, energy shifts)"
        ),
        expected_output=(
            "A complete YouTube script (1,400-1,800 words) following the Fireship + Hormozi style. "
            "Must include: a <10s hook, 3-4 core segments with [VISUAL CUE] and [B-ROLL] tags, "
            "energy markers, pattern interrupts, and a value-stack CTA close."
        ),
        agent=agent,
        context=[],
    )


def create_seo_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nGenerate YouTube SEO elements.",
        expected_output="YouTube SEO elements: an optimized title, structured description, and 10+ relevant tags.",
        agent=agent,
        context=[],
    )


def create_thumbnail_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nCreate a thumbnail concept.",
        expected_output="Creative and clickable thumbnail design ideas aimed at high CTR.",
        agent=agent,
        context=[],
    )


def create_shorts_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nWrite a YouTube Shorts script.",
        expected_output="A fast-paced script for a short-form video under 60 seconds.",
        agent=agent,
        context=[],
    )


def create_linkedin_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=(
            f"Write a LinkedIn post about: {prompt}\n\n"
            f"{LINKEDIN_STYLE}\n\n"
            "ADDITIONAL REQUIREMENTS:\n"
            "- Total post length: 150-220 words (LinkedIn sweet spot for engagement)\n"
            "- First line must work as a standalone hook — assume 90% of readers see ONLY this line\n"
            "- Include a personal story or anecdote (2-3 lines max)\n"
            "- End with an open-ended question that invites comments\n"
            "- Max 3 hashtags, all lowercase, at the very end\n"
            "- Zero bullet points — use line breaks only\n"
            "- Every line max 9 words"
        ),
        expected_output=(
            "A LinkedIn post (150-220 words) following the Justin Welsh + Shaan Puri style. "
            "Must include: a standalone hook line, 1-3-1 structure, personal story, "
            "open-ended closing question, max 3 lowercase hashtags."
        ),
        agent=agent,
        context=[],
    )


def create_twitter_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=(
            f"Write a Twitter/X thread about: {prompt}\n\n"
            f"{TWITTER_STYLE}\n\n"
            "ADDITIONAL REQUIREMENTS:\n"
            "- Exactly 10 tweets, numbered (1/10) through (10/10)\n"
            "- Tweet 1 must be standalone shareable — it IS the ad for the thread\n"
            "- Include at least 2 `inline code` snippets across the thread for dev credibility\n"
            "- Each tweet max 240 characters\n"
            "- Tweet 9 must be a personal story or contrarian hot take\n"
            "- Tweet 10 is the CTA: soft sell, retweet request\n"
            "- The thread must have a clear narrative arc (problem → insight → action)\n"
            "- Hashtags only on the last tweet (max 2)"
        ),
        expected_output=(
            "A Twitter/X thread of exactly 10 tweets following the Hormozi + Fireship + Shaan Puri style. "
            "Must include: numbered tweets (1/10)-(10/10), standalone hook tweet, "
            "inline code snippets, personal story in tweet 9, soft CTA in tweet 10."
        ),
        agent=agent,
        context=[],
    )


def create_blog_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=(
            f"Write a technical blog article about: {prompt}\n\n"
            f"{LONGFORM_STYLE}\n\n"
            "ADDITIONAL REQUIREMENTS:\n"
            "- Minimum 1,800 words\n"
            "- Include at least 3 code examples (Python preferred) with commentary\n"
            "- Use proper Markdown headers (##, ###) for structure\n"
            "- Include a 'Prerequisites' section near the top\n"
            "- End with a 'What to Build Next' section with 3 concrete project ideas\n"
            "- Every abstract concept must have a real-world analogy\n"
            "- Use 'we' not 'you' throughout\n"
            "- Never say 'simply' or 'just'"
        ),
        expected_output=(
            "A technical blog article (1,800+ words) following the Karpathy + Ali Abdaal style. "
            "Must include: Markdown headers, Prerequisites section, 3+ code examples with commentary, "
            "real-world analogies, 'What to Build Next' closing section."
        ),
        agent=agent,
        context=[],
    )


def create_course_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nCreate a course outline.",
        expected_output="A structured programming course outline with modules, lessons, and learning objectives.",
        agent=agent,
        context=[],
    )


def create_idea_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nGenerate 10 creative content ideas.",
        expected_output="A list of 10 creative and viral content ideas related to the topic.",
        agent=agent,
        context=[],
    )


def create_instagram_image_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nChoose the best artistic parameters (palette, layout, style_hints) and generate an Instagram image using your tool.",
        expected_output="Confirmation of the generated Instagram image along with the chosen palette, layout, and styles.",
        agent=agent,
        context=[],
    )


# ── Aggregate factory ────────────────────────────────────────────────────────

_TASK_FACTORIES = [
    ("Trend Analysis", create_trend_task),
    ("Script Writing", create_script_task),
    ("SEO Optimization", create_seo_task),
    ("Thumbnail Design", create_thumbnail_task),
    ("Shorts Scripting", create_shorts_task),
    ("LinkedIn Content", create_linkedin_task),
    ("Twitter Thread", create_twitter_task),
    ("Blog Article", create_blog_task),
    ("Course Outline", create_course_task),
    ("Idea Generation", create_idea_task),
]


def create_all_tasks(agents: list[Agent], topic: str, task_callback=None) -> list[Task]:
    """
    Build all tasks in pipeline order.

    Args:
        agents: List of agents (must match the order in _TASK_FACTORIES).
        topic:  The content topic provided by the user.
        task_callback: Optional callable passed to each task to report completion.

    Returns:
        Ordered list of Task objects.
    """
    prompt = _build_prompt(topic)
    tasks = []

    for (task_name, factory), agent in zip(_TASK_FACTORIES, agents, strict=True):
        task = factory(agent, prompt)

        # Wrap the original callback if provided
        if task_callback:
            def make_cb(name=task_name):
                def cb(task_output):
                    # task_output is a TaskOutput object in CrewAI
                    task_callback(name, task_output.raw)
                return cb

            task.callback = make_cb()

        tasks.append(task)

    return tasks
