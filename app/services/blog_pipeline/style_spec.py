"""
Shared style specification injected into BOTH the writer and the editor.
This makes style *checkable* instead of vibes-based.
"""

STYLE_SPEC = """
STYLE SPECIFICATION — Hormozi + Shaan Puri + Fireship Blend

HOOK RULE (Shaan Puri):
- Open EVERY section with ONE of: a concrete story, a specific number, or a contrarian line.
- NEVER open with: "In today's world", "In this section", "Let's explore", "It is important".
- The first sentence of every section must create a question or tension in the reader's mind.
- Good: "Three months ago, our RAG system was returning wrong answers 34% of the time."
- Bad: "In today's rapidly evolving AI landscape, RAG has become increasingly important."

FRAMEWORK RULE (Hormozi):
- Be blunt. Value-dense. Name your frameworks explicitly.
- No hedging language: never "might", "could potentially", "in some cases", "it depends".
- State things as facts or show the evidence. Waffling kills authority.
- Every section must deliver one concrete, actionable insight the reader can use today.
- Good: "The fix is dead simple: chunk your documents at 512 tokens, not 1024. Here's why."
- Bad: "There are various approaches one might consider when thinking about chunk size."

DENSITY RULE (Fireship):
- Short sentences. Technically precise. Maximum information per word.
- One dry aside per section maximum. Format: (yes, this actually happens in production.)
- Zero filler transitions. These words are BANNED as sentence openers:
  Moreover, Furthermore, Additionally, In conclusion, To summarize,
  It is worth noting, It should be mentioned, As previously stated.
- Sentence length MUST vary. After 2 short sentences, use one longer complex sentence. Then short again.
- Good rhythm: "The embedding model matters. Most people pick ada-002 and move on. That's the mistake — ada-002 is optimized for semantic similarity, not retrieval precision, and the gap shows up immediately in production evals."
- Bad rhythm: "The embedding model is important. You should choose carefully. There are many options. Each has pros and cons."

BANNED WORDS (automatic style violation if present):
delve, leverage (as a verb), realm, tapestry, moreover, furthermore,
navigate (used figuratively), seamlessly, robust (unless quoting a benchmark),
revolutionary, game-changing, cutting-edge, best practices (show it, don't label it),
utilize (use "use"), implement (use "build" or "write"), deep dive (use "breakdown")

CODE RULE:
- Every technical claim gets a code example. No exceptions.
- Code blocks must be complete and runnable. No "# ... rest of the code".
- Inline code for: function names, variable names, file names, commands.
- Comment every non-obvious line inside code blocks.
"""

STYLE_CHECKLIST = {
    "hook_not_generic": "First sentence is a story, number, or contrarian line — NOT a 'in today's world' opener",
    "no_hedging": "No 'might', 'could potentially', 'in some cases' — statements are direct",
    "no_filler_transitions": "No Moreover/Furthermore/Additionally/In conclusion as sentence openers",
    "no_banned_words": "None of the banned words appear: delve, leverage(v), realm, tapestry, navigate(fig), seamlessly",
    "sentence_rhythm": "Sentence lengths vary — not all short, not all long",
    "one_actionable_insight": "Section delivers at least one concrete thing the reader can do today",
    "claims_grounded": "Every factual claim is drawn from source_snippets — no invented statistics",
    "code_present_if_technical": "Technical claims have code examples",
}
