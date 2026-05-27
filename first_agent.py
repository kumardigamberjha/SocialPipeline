import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, LLM

# =========================
# ENV & OPENAI BYPASS
# =========================

# Load env variables (check root first, then app/.env)
load_dotenv()
load_dotenv(dotenv_path="app/.env")

# Force-sever the default OpenAI LLM fallback
os.environ["OPENAI_API_KEY"] = "sk-no-openai-intended"

# OLLAMA CONFIGURATION
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "ollama/mistral:latest")
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

# =========================
# LLM BUILDER (RUNTIME SAFE)
# =========================

def build_llm(provider="ollama"):
    provider = provider.lower().strip()

    if provider == "ollama":
        print(f"[SYSTEM] Using local Ollama: {OLLAMA_MODEL} at {OLLAMA_API_BASE}")
        return LLM(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_API_BASE,
            api_key="ollama", # dummy key to satisfy LiteLLM/OpenAI validation issues
            temperature=0.0,
            timeout=120,
        )

    if provider == "nvidia":
        NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
        if not NVIDIA_API_KEY:
            raise RuntimeError("Missing NVIDIA_API_KEY")
        print("[SYSTEM] Using NVIDIA")
        return LLM(
            model="qwen/qwen3.5-122b-a10b",
            api_key=NVIDIA_API_KEY,
            base_url="https://integrate.api.nvidia.com/v1",
            temperature=0.6,
            top_p=0.9,
            max_tokens=2048,
            timeout=60,
        )

    if provider == "groq":
        GROQ_API_KEY = os.getenv("GROQ_API_KEY")
        if not GROQ_API_KEY:
            raise RuntimeError("Missing GROQ_API_KEY")
        print("[SYSTEM] Using GROQ")
        return LLM(
            model="llama-3.3-70b-versatile",
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            temperature=0.7,
            max_tokens=2048,
            timeout=60,
        )

    raise ValueError(f"Unknown provider: {provider}")

# Default LLM to Ollama
llm = build_llm("ollama")



# =========================
# USER INPUT
# =========================

USER_TOPIC = "Build AI Agents using CrewAI"

USER_PROMPT = f"""
Topic: {USER_TOPIC}

Create high quality developer content.
Focus on AI, Python, automation, and real-world use.
"""


# =========================
# AGENTS (STRONG SYSTEM PROMPTS)
# =========================

trend_agent = Agent(
    role="Senior Tech Trend Analyst",
    goal="Find high viral developer topics",
    backstory="""
You are a senior AI content strategist.
You know YouTube, LinkedIn, Twitter algorithms.
You always choose topics that can go viral.
Return precise answers.
""",
    llm=llm,
    verbose=True,
)

script_agent = Agent(
    role="YouTube Script Writer",
    goal="Write engaging scripts",
    backstory="""
You are a professional script writer.

Rules:
- Hook in first line
- Keep engaging
- Add CTA
- Use storytelling
""",
    llm=llm,
)

seo_agent = Agent(
    role="SEO Specialist",
    goal="Generate SEO",
    backstory="""
Expert in YouTube SEO.
Generate title, description, tags.
Focus on ranking keywords.
""",
    llm=llm,
)

thumbnail_agent = Agent(
    role="Thumbnail Designer",
    goal="Create clickable thumbnail ideas",
    backstory="""
Expert YouTube designer.
Make high CTR thumbnails.
Use curiosity and emotion.
""",
    llm=llm,
)

shorts_agent = Agent(
    role="Shorts Writer",
    goal="Write viral shorts",
    backstory="""
Short-form video expert.
Hook fast.
Keep under 60 sec.
""",
    llm=llm,
)

linkedin_agent = Agent(
    role="LinkedIn Creator",
    goal="Write viral LinkedIn post",
    backstory="""
LinkedIn growth expert.
Write professional + engaging.
Use storytelling.
""",
    llm=llm,
)

twitter_agent = Agent(
    role="Twitter Thread Writer",
    goal="Write thread",
    backstory="Twitter growth expert",
    llm=llm,
)

blog_agent = Agent(
    role="Technical Blogger",
    goal="Write blog",
    backstory="Writes developer blogs",
    llm=llm,
)

course_agent = Agent(
    role="Course Architect",
    goal="Create course",
    backstory="Designs programming courses",
    llm=llm,
)

idea_agent = Agent(
    role="Creative Strategist",
    goal="Generate viral ideas",
    backstory="Expert in viral content",
    llm=llm,
)


# =========================
# TASKS (GOOD USER PROMPTS)
# =========================

task1 = Task(
    description=f"""
{USER_PROMPT}

Find 5 viral topics.
""",
    expected_output="A list of 5 trending viral developer topics.",
    agent=trend_agent,
)

task2 = Task(
    description=f"""
{USER_PROMPT}

Write YouTube script.
""",
    expected_output="A full YouTube script with an engaging hook and clear CTA.",
    agent=script_agent,
)

task3 = Task(
    description=f"""
{USER_PROMPT}

Generate SEO.
""",
    expected_output="YouTube SEO elements including a title, structured description, and relevant tags.",
    agent=seo_agent,
)

task4 = Task(
    description=f"""
{USER_PROMPT}

Thumbnail idea.
""",
    expected_output="Creative and clickable thumbnail design ideas aimed at high CTR.",
    agent=thumbnail_agent,
)

task5 = Task(
    description=f"""
{USER_PROMPT}

Shorts script.
""",
    expected_output="A fast-paced script for a short-form video under 60 seconds.",
    agent=shorts_agent,
)

task6 = Task(
    description=f"""
{USER_PROMPT}

LinkedIn post.
""",
    expected_output="A professional yet engaging LinkedIn post using storytelling techniques.",
    agent=linkedin_agent,
)

task7 = Task(
    description=f"""
{USER_PROMPT}

Twitter thread.
""",
    expected_output="A series of informative and engaging tweets forming a thread.",
    agent=twitter_agent,
)

task8 = Task(
    description=f"""
{USER_PROMPT}

Blog article.
""",
    expected_output="A comprehensive technical blog article based on the topic.",
    agent=blog_agent,
)

task9 = Task(
    description=f"""
{USER_PROMPT}

Course outline.
""",
    expected_output="A structured programming course outline with modules and lessons.",
    agent=course_agent,
)

task10 = Task(
    description=f"""
{USER_PROMPT}

Generate 10 ideas.
""",
    expected_output="A list of 10 creative and viral content ideas related to the topic.",
    agent=idea_agent,
)


# =========================
# CREW
# =========================

crew = Crew(
    agents=[
        trend_agent,
        script_agent,
        seo_agent,
        thumbnail_agent,
        shorts_agent,
        linkedin_agent,
        twitter_agent,
        blog_agent,
        course_agent,
        idea_agent,
    ],
    tasks=[
        task1,
        task2,
        task3,
        task4,
        task5,
        task6,
        task7,
        task8,
        task9,
        task10,
    ],
    process="sequential",
    verbose=True,
    memory=False, # Disable memory to prevent any default OpenAI embedding models from being called
    llm=llm,      # Explicitly set Crew-level LLM to bypass OpenAI fallback
)


# =========================
# RUN SYSTEM
# =========================

try:

    print(f"\n[SYSTEM] RUNNING OLLAMA ({OLLAMA_MODEL})\n")

    result = crew.kickoff()

except Exception as e:

    print(f"\n[SYSTEM] OLLAMA PIPELINE RUN FAILED: {e}\n")
    raise e


print("\nFINAL RESULT\n")
print(result)