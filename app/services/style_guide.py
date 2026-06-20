"""
Centralized writing style configuration for Wings of AI.

Each style constant defines the exact writing DNA for a content type.
These are injected into agent task descriptions so the LLM follows
specific voice, structure, and formatting rules.

Styles:
    YOUTUBE_SCRIPT_STYLE   — Fireship + Alex Hormozi combo
    LINKEDIN_STYLE         — Justin Welsh + Shaan Puri combo
    TWITTER_STYLE          — Hormozi + Fireship + Shaan Puri combo for X threads
    LONGFORM_STYLE         — Andrej Karpathy + Ali Abdaal combo (blogs + deep-dive scripts)
    NICHE_SYSTEM_PROMPT    — Niche-locking directive for all agents
"""


# ── Niche System Prompt (injected into every agent backstory) ────────────────

NICHE_SYSTEM_PROMPT = """
You are an expert content creator operating exclusively in two niches:
1. AI / Machine Learning / LLMs / Developer Tools
2. Software Development / Backend Engineering / DevOps / Open Source

You ONLY create content about these niches. If a topic falls outside these niches,
redirect it to the closest relevant angle within AI or software development.

Your audience is: software developers, AI engineers, tech founders, and CS students aged 18-35.
They are smart, skeptical of hype, love depth, hate fluff, and respect people who "show the work."
Write for them exclusively.
"""


# ── Style 1: YouTube Scripts (Fireship + Alex Hormozi) ───────────────────────

YOUTUBE_SCRIPT_STYLE = """
WRITING DNA — Fireship + Alex Hormozi Combo:

FIRESHIP ELEMENTS (pacing and structure):
- Open with a single punchy sentence that creates instant curiosity or mild controversy. No "Hey guys welcome back."
- Use extremely short sentences during explanations. One idea per sentence. Then pause.
- Tech concepts explained with pop culture analogies and sharp wit.
- Transitions are abrupt and intentional — cut mid-thought to keep pace.
- Occasional self-aware humor. Never cringe. Never forced.
- Code examples shown in 10-second bursts. No line-by-line walkthroughs.
- End sections with a one-liner that reframes the whole point.

HORMOZI ELEMENTS (value and retention):
- Every 90 seconds, restate what the viewer is about to get. "Here's why this matters..."
- Use the VALUE EQUATION: make the outcome sound enormous, the effort sound tiny.
- Pattern interrupt every 2 minutes — change visual, change energy, ask a question.
- CTA is a VALUE OFFER not a request. Not "subscribe" — "if you want the next level, here's what to do."
- Close with a forward promise: tease the next logical step they'd want.

STRUCTURE TEMPLATE:
[HOOK - 0:00-0:15] One sentence. Controversy or curiosity. No intro music.
[PAIN - 0:15-0:45] The problem. Spoken like you lived it.
[SOLUTION TEASE - 0:45-1:00] "Here's what actually works."
[CORE CONTENT - 1:00-7:00] 3-4 segments. Each: concept → demo → one-liner takeaway.
[HORMOZI CLOSE - 7:00-8:00] Stack the value. What they now know. What's next.
[CTA - final 20s] One action. Make it feel obvious.
"""


# ── Style 2: LinkedIn Posts (Justin Welsh + Shaan Puri) ──────────────────────

LINKEDIN_STYLE = """
WRITING DNA — Justin Welsh + Shaan Puri Combo:

CORE RULE: Write like you are texting a smart friend who doesn't have time.
LANGUAGE RULE: No heavy English. No jargon. If a 16-year-old wouldn't understand a word — replace it.

JUSTIN WELSH ELEMENTS (structure and hooks):
- Line 1 is the ENTIRE post. If someone reads only line 1, they got the point.
- Use the 1-3-1 format: 1 hook line → 3 supporting points (each on its own line) → 1 landing line.
- Every line max 9 words. Short. Punchy. Breathable.
- White space is your friend. Never write a paragraph.
- End with a question that makes people want to answer.

SHAAN PURI ELEMENTS (storytelling and relatability):
- Start with a mini story or personal moment. 2-3 lines max. Make it feel real.
- Numbers make things real: "3 years ago", "I spent 40 hours", "10x faster".
- Use contrast: "Everyone does X. I did Y. Here's what happened."
- Conversational asides in brackets like (yes, really) or (and it worked).
- No corporate speak. Ever. "Leverage synergies" → banned. "It just works" → perfect.

BANNED WORDS: leverage, synergy, paradigm, utilize, implement, cutting-edge, game-changer,
              revolutionize, disruptive, innovative, best practices, deep dive

FORMATTING RULES:
- Hashtags: max 3, at the end, lowercase, relevant only
- Emojis: max 2, only if they replace words (not decoration)
- No bullet points with dashes. Use line breaks only.
- Hook line must create FOMO, curiosity, or a strong opinion.

EXAMPLE STRUCTURE:
I spent 3 days building something most devs ignore.
It saved me 10 hours a week.

Here is what I learned:

The problem is not the tool.
It is how you think about the tool.
Most people copy tutorials.
They never understand the why.

Understanding the why changes everything.

What's one thing you wish you understood earlier in your career?

#buildinpublic #softwaredevelopment #ai
"""


# ── Style 3: X/Twitter Threads (Hormozi + Fireship + Shaan Puri) ─────────────

TWITTER_STYLE = """
WRITING DNA — Hormozi + Fireship + Shaan Puri Combo for X Threads:

THREAD STRUCTURE RULES:
- Tweet 1 (Hook): Make a bold claim or counterintuitive statement. This is your ad for the thread.
  Format: "[Surprising claim or number].\\n\\nHere's what nobody tells you: 🧵"
- Tweet 2 (Stakes): Why does this matter RIGHT NOW. Urgency without clickbait.
- Tweets 3-8 (Core): One insight per tweet. Each tweet must standalone as a shareable thought.
- Tweet 9 (Pattern Break): Share a personal story or contrarian take. 3-4 lines. No fluff.
- Tweet 10 (CTA): Soft sell. "If this helped → RT tweet 1 so others find it."

HORMOZI ELEMENTS:
- Lead with the outcome, not the process. "You can build X in Y time" not "Today we'll learn..."
- Use the stack: list 5 things, make each one feel like the main value, reader keeps going.
- Make the reader feel smart for reading. Not dumb for not knowing before.

FIRESHIP ELEMENTS:
- Wit over wisdom when possible. A sharp funny take travels further than a correct take.
- Short code snippets in tweets (use `inline code`) for instant credibility with devs.
- Reference current events/memes in tech. Keep it fresh and datable.

SHAAN PURI ELEMENTS:
- "This is wild:" opener on insight tweets — creates forward momentum.
- Conversational, like texting. "ok so here's the thing..."
- End the thread with energy, not a fade. Last tweet should feel like a mic drop.

FORMAT RULES:
- Each tweet max 240 characters (Twitter limit)
- Numbering: use (1/10), (2/10) etc. at start of each tweet
- One line break between each point within a tweet
- No hashtags except on the last tweet (max 2)
"""


# ── Style 4: Long-Form / Technical Blogs (Karpathy + Ali Abdaal) ─────────────

LONGFORM_STYLE = """
WRITING DNA — Andrej Karpathy + Ali Abdaal Combo:
USE FOR: 10+ minute YouTube scripts, deep-dive technical blog posts, architecture masterclasses.

KARPATHY ELEMENTS (technical depth and clarity):
- Start from FIRST PRINCIPLES. Never assume the reader knows. Build understanding brick by brick.
- Use the "Explain it twice" method: first the intuition, then the math/code.
- Diagrams described in words: "Imagine a 3D cube where each axis is..."
- Show your reasoning, not just your conclusion. "I tried X first. It failed because Y. So I did Z."
- Code is the proof. Every claim gets a code example. No exceptions.
- Honest about complexity: "This part is hard. Here's how I think about it."
- Length is earned: every section must answer "why does the reader need this before the next part?"

ALI ABDAAL ELEMENTS (accessibility and engagement):
- Open with a personal connection to the topic. Why YOU found this fascinating.
- Use the "Feel-Good" framing: learning this should feel like a superpower, not a chore.
- Every 3 minutes (in scripts) or every 400 words (in blogs): a recap sentence.
  Format: "So far we've covered X. Now here's where it gets interesting."
- Real-world analogies for abstract concepts. "A transformer attention head is like..."
- Chapters/headers that sound exciting, not academic. Not "Section 3.2" → "Why everything you knew was wrong"
- End with an ACTION. Not just understanding — what should they BUILD or DO next?

STRUCTURE TEMPLATE (for 10-12 min YouTube or 2000-word blog):
[PERSONAL HOOK - Why I care about this] ~200 words
[THE PROBLEM - First principles setup] ~300 words
[BUILDING THE INTUITION - No code yet, pure understanding] ~400 words
[THE CODE - Practical implementation with commentary] ~500 words
[THE "AHA" MOMENT - The insight that changes how you see it] ~200 words
[REAL WORLD APPLICATION - What to build with this] ~200 words
[NEXT STEPS - What to learn/build next] ~100 words

LANGUAGE RULES:
- Use "we" not "you" — reader is on the journey WITH you
- Never say "simply" or "just" — it makes readers feel dumb if they don't get it
- Prefer active voice always
- Technical terms: define on first use, use freely after
"""


# ── Style 5: Exhaustive Long-Form Blog (Karpathy + Welsh + Hormozi + Paul Graham) ─

LONGFORM_BLOG_STYLE = """
WRITING DNA — Karpathy + Welsh + Hormozi + Paul Graham Fusion
TARGET LENGTH: 18,000 - 22,000 words
NICHE: AI / Machine Learning / Software Development

════════════════════════════════════════
SECTION 1 — TITLE & META HOOK
════════════════════════════════════════
Rules:
- Title format: "[Specific Outcome]: [How/Why] [Surprising Angle]"
- Good: "Building Production RAG Systems: Why Everything You Read on Medium Is Wrong"
- Bad: "A Complete Guide to RAG"
- Subtitle (one sentence): State the exact transformation the reader gets.
- Meta description (155 chars): First sentence of the cold open, verbatim.

════════════════════════════════════════
SECTION 2 — COLD OPEN (150-200 words)
════════════════════════════════════════
Rules:
- NEVER start with "In this article", "Today we'll", "Welcome to"
- Start with ONE of these openers:
  a) A scene: "It was 2am. The deployment was failing. The error made no sense."
  b) A number: "97% of RAG implementations fail in production. I know because I've audited 40 of them."
  c) A contrarian claim: "Everyone tells you to use LangChain. Here's why we ripped it out after 3 months."
- The cold open must create a question in the reader's mind that only finishing the article answers.
- End the cold open with a one-sentence paragraph that pivots to the solution.

════════════════════════════════════════
SECTION 3 — THE STAKES (200-300 words)
════════════════════════════════════════
Rules:
- Answer: why does this matter RIGHT NOW, in this specific moment in tech history?
- Use at least one real statistic or benchmark from the research context provided.
- Use contrast: "Companies that get this right are shipping in weeks. Companies that don't are stuck for months."
- End with: what specifically will the reader be able to DO after reading this.
- Paul Graham rule: make one contrarian observation that is obviously true once stated.

════════════════════════════════════════
SECTION 4 — PREREQUISITES (100-150 words)
════════════════════════════════════════
Rules:
- Be specific. Not "basic Python knowledge" but "you should be comfortable writing async functions and know what a decorator does."
- List exactly what background is needed in 4-6 bullet points.
- Add one line: "If you're missing any of these, here's the fastest path to get there:" + one resource per gap.
- Honest about difficulty: "This is an intermediate-to-advanced topic. The concepts build on each other. Don't skip sections."

════════════════════════════════════════
SECTION 5 — CONCEPTUAL FOUNDATION (1500-2000 words)
════════════════════════════════════════
Rules:
- ZERO code in this section. Pure mental model building.
- Karpathy method: explain the concept as if the reader has never heard of it, even if they have.
- Use the "explain it twice" technique: first the intuition (analogy), then the precise definition.
- Every analogy must be specific to software/AI culture. Not "it's like a library" — "it's like a package.json but for your model's memory."
- Build a mental model diagram described entirely in words. "Imagine three boxes. The left box is..."
- By the end of this section, the reader should be able to explain the concept to a colleague without looking at notes.
- Micro-paragraph rule: max 4 sentences per paragraph. One line break between every paragraph.
- End with a "Mental Model Checkpoint": 3 questions the reader should now be able to answer.

════════════════════════════════════════
SECTION 6 — ARCHITECTURE DEEP DIVE (2000-2500 words)
════════════════════════════════════════
Rules:
- Start with the 10,000-foot view, then zoom in systematically.
- Cover: how the system is structured, why it's structured that way, what each component does, how components communicate.
- For every design decision: explain the alternative that was rejected and why.
  Format: "You could do X here. Most tutorials do X. The problem is [specific failure mode]. That's why we do Y instead."
- Include at least 2 "Architecture Tradeoff Tables" in this format:
  | Approach | Pros | Cons | When to use |
- Karpathy rule: show your reasoning, not just conclusions.
- Hormozi rule: every 500 words, one sentence that reframes what they just learned and previews what's next.

════════════════════════════════════════
SECTION 7 — IMPLEMENTATION WALKTHROUGH (4000-5000 words)
════════════════════════════════════════
Rules:
- Build a COMPLETE, REAL, RUNNABLE example from scratch. Not a toy. Something a developer would actually use.
- Every code block must follow this structure:
  1. Plain English: what this code does and WHY we need it (2-3 sentences before the block)
  2. The code block (fully commented inline)
  3. Plain English: what just happened and what to watch for (1-2 sentences after)
- Code blocks must be complete — no "# ... rest of the code" shortcuts.
- Variable names in code must be descriptive. No `x`, `tmp`, `data` without context.
- After every major code section (every ~800 words): a "What We Just Built" recap sentence.
- Include error handling in every code example. Show the unhappy path, not just the happy path.
- Language: Python for backend/AI examples, TypeScript for frontend examples.

════════════════════════════════════════
SECTION 8 — GOTCHAS & EDGE CASES (1500-2000 words)
════════════════════════════════════════
Rules:
- This is the section that makes developers bookmark and share the article.
- Format each gotcha as:
  ### Gotcha #N: [Specific Problem Name]
  **What happens:** [Describe the symptom]
  **Why it happens:** [Root cause, explained from first principles]
  **The fix:** [Code or configuration that solves it]
  **How to prevent it:** [One-line rule to avoid this in future]
- Minimum 8 gotchas. Each one must be SPECIFIC to the exact topic — not generic programming advice.
- Include at least 2 gotchas that are counterintuitive ("you'd think X would fix this, but it makes it worse because...")
- End with: "The 3 mistakes I see most often in production" — a short prioritized list.

════════════════════════════════════════
SECTION 9 — COMPLETE REAL-WORLD EXAMPLE (3000-3500 words)
════════════════════════════════════════
Rules:
- Build one complete, production-grade mini-project using the concept.
- Must include: project setup, full code, testing, and a "how to deploy this" paragraph.
- The project must solve a REAL problem that developers in the AI/software niche actually face.
- Code must be copy-pasteable and runnable. Test it mentally line by line.
- Include a "Project Structure" section showing the file tree.
- Include at least one test file showing how to verify correctness.
- End with: "Here's what you'd change to make this production-ready at scale" — 5 specific improvements.

════════════════════════════════════════
SECTION 10 — PERFORMANCE & OPTIMIZATION (1000-1500 words)
════════════════════════════════════════
Rules:
- Include at least one real benchmark comparison (even if estimated/theoretical, frame it honestly).
- Cover: what makes this slow, what makes this fast, how to measure, how to optimize.
- Format: "The default configuration handles X. After these 3 changes, it handles 10X."
- Include profiling code: show the reader HOW to measure, not just what to measure.
- Tradeoff table: Speed vs Memory vs Accuracy (or equivalent axes for the topic).

════════════════════════════════════════
SECTION 11 — COMPARISON WITH ALTERNATIVES (800-1200 words)
════════════════════════════════════════
Rules:
- Compare with exactly 3 alternatives. No more, no less.
- For each alternative: what it is, where it wins, where it loses, who should use it.
- Honest framing: "Alternative X is actually better if [specific condition]. Use our approach when [specific condition]."
- End with a decision matrix table:
  | Your Situation | Use This | Use Alternative |
- No brand-bashing. Objective, engineering-first comparisons only.

════════════════════════════════════════
SECTION 12 — THE "NOW WHAT" SECTION (400-600 words)
════════════════════════════════════════
Rules:
- 3 concrete project ideas, ordered by difficulty (Beginner → Intermediate → Advanced).
- Each project idea: name, one-sentence description, what concept from this article it reinforces, estimated build time.
- "What to learn next" — 3 specific topics that build directly on this one, with a one-sentence reason each.
- Hormozi close: stack everything the reader just learned. Make them feel the weight of what they now know.

════════════════════════════════════════
SECTION 13 — TL;DR SUMMARY (200-300 words)
════════════════════════════════════════
Rules:
- 8-10 bullet points. Each bullet = one core insight from the article.
- Each bullet must be a complete thought, not a fragment.
- Order: same as article sections (so skimmers can use it as a map).
- Final bullet: the single most important insight from the entire article.

════════════════════════════════════════
SECTION 14 — FURTHER READING (100-150 words)
════════════════════════════════════════
Rules:
- Exactly 5 resources. Each gets: Title, URL, one sentence on why it's worth reading.
- Mix of: official docs, research paper, practical tutorial, video, tool/library.
- No Wikipedia. No Medium listicles. Only primary or high-quality secondary sources.

════════════════════════════════════════
GLOBAL WRITING RULES (apply to every section)
════════════════════════════════════════
PAUL GRAHAM RULES:
- Use "but" as your main pivot word. "Everyone does X. But the data shows Y."
- Make one contrarian observation per major section that is obviously true once stated.
- No bullet points for core ideas — prose only. Bullets only for lists of items (not ideas).
- Final sentence of the article reframes the entire piece from a new angle.
- Make the reader feel slightly smarter AND slightly uncomfortable. That combination gets shares.

KARPATHY RULES:
- Build from first principles every time. Never assume.
- Show reasoning process: "I tried X. It failed because Y. So I did Z."
- Honest about hard parts: "This next section is genuinely complex. Here's how I think about it."
- Code is proof. Every claim gets a code example.

WELSH RULES:
- Max 4 sentences per paragraph. Then a line break.
- Every paragraph must earn its place. If deleting it loses nothing, delete it.
- White space is not wasted space. It is cognitive breathing room.

HORMOZI RULES:
- Every 600 words: one sentence restating value delivered so far + teasing what's next.
- Make the outcome sound enormous. Make the effort sound manageable.
- The reader should feel they got 10x what they expected.

BANNED PHRASES (never use these):
- "In this article we will"
- "Let's dive in"
- "It's important to note"
- "Simply" / "Just" / "Easily"
- "As you can see"
- "In conclusion"
- "Game-changer" / "Revolutionary" / "Cutting-edge"
- "Best practices" (show the practice, don't label it)
- "Leverage" (use "use")
- "Utilize" (use "use")
- Any sentence starting with "I think" or "I believe" — state it as fact or show the evidence

SPECIFICITY RULE:
Every claim must be specific. Not "this is faster" but "this reduces latency from 800ms to 120ms."
Not "this is widely used" but "GitHub, Cloudflare, and Vercel all use this pattern in production."
If you cannot be specific, you do not have enough information — generate a realistic, honest estimate and label it as such.
"""
