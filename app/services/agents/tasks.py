"""
Task factory functions.

Each function creates a single CrewAI Task bound to its agent.
`create_all_tasks()` builds the full task list in pipeline order.
"""

from crewai import Agent, Task


def _build_prompt(topic: str) -> str:
    """Build the shared user prompt injected into every task."""
    return (
        f"Topic: {topic}\n\n"
        "Create high-quality developer content.\n"
        "Focus on AI, Python, automation, and real-world use."
    )


# ── Individual task factories ────────────────────────────────────────────────


def create_trend_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nFind 5 viral topics related to this theme.",
        expected_output="A list of 5 trending, viral developer topics with brief justifications.",
        agent=agent,
    )


def create_script_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nWrite a full YouTube script.",
        expected_output="A complete YouTube script with an engaging hook, structured body, and clear CTA.",
        agent=agent,
    )


def create_seo_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nGenerate YouTube SEO elements.",
        expected_output="YouTube SEO elements: an optimized title, structured description, and 10+ relevant tags.",
        agent=agent,
    )


def create_thumbnail_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nCreate a thumbnail concept.",
        expected_output="Creative and clickable thumbnail design ideas aimed at high CTR.",
        agent=agent,
    )


def create_shorts_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nWrite a YouTube Shorts script.",
        expected_output="A fast-paced script for a short-form video under 60 seconds.",
        agent=agent,
    )


def create_linkedin_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nWrite a LinkedIn post.",
        expected_output="A professional yet engaging LinkedIn post using storytelling and relevant hashtags.",
        agent=agent,
    )


def create_twitter_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nWrite a Twitter thread.",
        expected_output="A series of informative and engaging tweets forming a cohesive thread.",
        agent=agent,
    )


def create_blog_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nWrite a technical blog article.",
        expected_output="A comprehensive technical blog article with examples and actionable takeaways.",
        agent=agent,
    )


def create_course_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nCreate a course outline.",
        expected_output="A structured programming course outline with modules, lessons, and learning objectives.",
        agent=agent,
    )


def create_idea_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nGenerate 10 creative content ideas.",
        expected_output="A list of 10 creative and viral content ideas related to the topic.",
        agent=agent,
    )


# ── Aggregate factory ────────────────────────────────────────────────────────

_TASK_FACTORIES = [
    create_trend_task,
    create_script_task,
    create_seo_task,
    create_thumbnail_task,
    create_shorts_task,
    create_linkedin_task,
    create_twitter_task,
    create_blog_task,
    create_course_task,
    create_idea_task,
]


def create_all_tasks(agents: list[Agent], topic: str) -> list[Task]:
    """
    Build all tasks in pipeline order.

    Args:
        agents: List of agents (must match the order in _TASK_FACTORIES).
        topic:  The content topic provided by the user.

    Returns:
        Ordered list of Task objects.
    """
    prompt = _build_prompt(topic)
    return [
        factory(agent, prompt)
        for factory, agent in zip(_TASK_FACTORIES, agents, strict=True)
    ]
