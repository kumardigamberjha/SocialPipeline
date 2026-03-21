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


def create_instagram_image_task(agent: Agent, prompt: str) -> Task:
    return Task(
        description=f"{prompt}\n\nChoose the best artistic parameters (palette, layout, style_hints) and generate an Instagram image using your tool.",
        expected_output="Confirmation of the generated Instagram image along with the chosen palette, layout, and styles.",
        agent=agent,
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
