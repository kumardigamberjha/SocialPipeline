LINKEDIN_STYLE_SPEC = """
LINKEDIN STYLE SPECIFICATION — Hormozi + Shaan Puri + Fireship Blend

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOOK RULE (Shaan Puri — pehli 2 lines sab kuch hain)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Line 1 MUST be ONE of: a concrete number, a micro-story opening, or a contrarian claim. Maximum 15 words.
- Line 2 MUST deepen the tension or promise created by line 1.
- These two lines appear BEFORE "...see more".
- NEVER open with: "In today's world", "I'm excited", "Thrilled to announce", "Humbled by", "It's important to".

GOOD: "I got fired on a Tuesday. Best thing that ever happened to my career."
BAD: "In today's rapidly evolving AI landscape, it's crucial to stay updated."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BODY RULE (Hormozi — blunt, value-dense, NO LISTICLES)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- ONE clear framework or insight per post. Not three. ONE.
- STATE FACTS. No "I think", "maybe", "it could be argued".
- MIDDLE PART CONSTRAINT (THE ANTI-WALL-OF-TEXT RULE): 
  - If you use a list, maximum 3 bullet points. 
  - Each bullet point MUST be under 20 words.
  - Never write a paragraph longer than 3 sentences. 
- Every line must earn its place. Cut the fat.
- White space between every 1-2 lines. Double line breaks (\\n\\n) are mandatory.

GOOD rhythm:
  "The problem isn't the model.
  It's the chunking strategy.

  Most chunk at 1024 tokens.
  Should be 256-512 for precision.

  Fixed that one thing.
  Latency dropped 40%."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RHYTHM RULE (Fireship — density + variation)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Short sentences dominate.
- Technically precise. Use exact numbers ("3x faster").
- ZERO filler transitions. BANNED: Moreover, Furthermore, Additionally, In conclusion, To summarize.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CTA RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Exactly ONE Call to Action at the end (a question or soft ask).
- NEVER: "Like and share", "Drop a comment AND repost".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HASHTAG RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 3 to 5 lowercase hashtags. On their own line. At the very end.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BANNED WORDS (Automatic Hard Fail)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
delve, leverage (as verb), realm, tapestry, synergy, seamlessly, humbled to announce, thrilled to share, excited to share, game-changer, revolutionary, cutting-edge, best practices, utilize, implement, navigate, robust, in today's, let's dive in.
"""

LINKEDIN_REGEX_CHECKLIST = {
    "hook_under_15_words":     "First line word count <= 20",
    "no_filler_transitions":   "No Moreover/Furthermore/Additionally/In conclusion as line openers",
    "no_banned_words":         "Zero occurrences of banned dictionary words",
    "hashtag_count_ok":        "Regex count of '#' is between 3 and 5",
    "word_count_ok":           "Total post length is between 500 and 800 words",
    "white_space_present":     "Post uses '\\n\\n' between ideas",
    "no_wall_of_text":         "No single text block (between \\n\\n) exceeds 40 words",
    "listicle_constraint":     "If bullet points are used, no individual bullet point exceeds 20 words"
}

LINKEDIN_SEMANTIC_CHECKLIST = {
    "hook_not_generic":        "Does the first line use a concrete number, micro-story, or contrarian claim instead of a generic opener?",
    "no_hedging":              "Is the text entirely free of hedging words like 'I think', 'maybe', 'could potentially'?",
    "one_insight_only":        "Does the post focus on a single, deep framework rather than listing multiple distinct topics?",
    "middle_part_concise":     "Does the body of the post maintain rapid pacing without devolving into long, descriptive paragraphs or heavy listicles?",
    "single_cta":              "Is there exactly one clear call to action at the bottom?"
}

LINKEDIN_STYLE_CHECKLIST = {
    "hook_not_generic":        "First line is a number, micro-story, or contrarian claim — NOT a generic opener",
    "hook_under_15_words":     "First line is 15 words or fewer",
    "no_hedging":              "No 'I think', 'maybe', 'could potentially', 'in some cases'",
    "no_filler_transitions":   "No Moreover/Furthermore/Additionally/In conclusion as line openers",
    "no_banned_words":         "None of these appear: delve, leverage(v), realm, synergy, humbled to announce, thrilled to share, seamlessly",
    "single_cta":              "Exactly one CTA at the end — not multiple asks",
    "line_length_ok":          "Lines are punchy and readable (not walls of text)",
    "hashtag_count_ok":        "Between 3 and 5 hashtags",
    "word_count_ok":           "Total post is between 400 and 800 words",
    "white_space_present":     "Post uses line breaks between ideas — not wall-of-text paragraphs",
    "one_insight_only":        "Post delivers exactly one framework, lesson, or insight — not a list of three",
}
