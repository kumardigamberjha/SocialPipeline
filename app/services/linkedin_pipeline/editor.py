"""
Agent 3 — Editor.

Critiques AND fixes the post against the style checklist in a single call. Called
at most twice (the orchestrator enforces the 2-cycle hard cap). Fixes violations
in place only — it never adds new ideas or restructures the post.

Temperature: 0.3
"""

import json
import logging

from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm
from app.services.linkedin_pipeline.schemas import EditedPost
from app.services.linkedin_pipeline.style_spec import (
    LINKEDIN_STYLE_CHECKLIST,
    LINKEDIN_STYLE_SPEC,
)

logger = logging.getLogger(__name__)

EDITOR_TEMPERATURE = 0.3

EDITOR_PROMPT = """
INSTRUCTION: You are an elite AI Editor grading a draft post. The draft below has FAILED the QA pipeline. 
Rewrite and fix the draft in-place so it perfectly resolves the specific violations listed below while maintaining the original meaning. 
You must perfectly match this exact Persona, Structure, and Word Count (600-800 words). Return the complete rewritten post.

# THE VIOLATIONS (TARGET THESE EXACT ERRORS):
{failed_rules}

# ROLE & PERSONA
You are an elite ghostwriter for a Senior AI Software Engineer. Your writing style is pragmatic, highly technical, and slightly contrarian (a mix of Shaan Puri and Alex Hormozi). You write for other engineers, founders, and technical builders. 

INPUT:
- post_text: {post_text}
- rewrite_cycle: {rewrite_cycle} (current cycle number, max is 2)
"""

_SCHEMA_HINT = json.dumps(
    {
        "revised_post": "string (the FULL corrected post text, all lines)",
        "hook_line": "string (the first line of revised_post)",
        "violations_fixed": [
            {"rule": "checklist key", "offending_text": "the quote you fixed", "fix_applied": "what you changed it to"}
        ],
        "still_weak": False,
    },
    indent=2,
)


class LinkedInEditorAgent:
    def __init__(self, llm_provider: str):
        self.llm_provider = llm_provider
        self.llm = make_llm(llm_provider, EDITOR_TEMPERATURE, max_tokens=4096)

    async def edit(self, post_text: str, qa_results: dict, cycle: int) -> EditedPost:
        failed_rules = []
        for key, passed in qa_results.items():
            if key.startswith("passes_") and not passed:
                failed_rules.append(key)
        
        error_context = "Failed Rules:\n" + "\n".join(f"- {r}" for r in failed_rules)
        if qa_results.get("long_lines"):
            error_context += "\n\nLong lines found:\n" + "\n".join(f"- {l}" for l in qa_results["long_lines"])
        if qa_results.get("banned_words_found"):
            error_context += "\n\nBanned words found:\n" + ", ".join(qa_results["banned_words_found"])

        prompt = EDITOR_PROMPT.format(
            post_text=post_text,
            failed_rules=error_context,
            rewrite_cycle=cycle,
            style_spec=LINKEDIN_STYLE_SPEC,
            schema=_SCHEMA_HINT,
        )

        edited: EditedPost = await call_llm_with_retry(
            self.llm,
            prompt,
            EditedPost,
            temperature=EDITOR_TEMPERATURE,
            max_retries=3,
            agent_name="Editor",
        )
        # Never lose the post — fall back to the input text if the model blanked it.
        if not edited.revised_post.strip():
            edited.revised_post = post_text
        if not edited.hook_line:
            for line in edited.revised_post.split("\n"):
                if line.strip():
                    edited.hook_line = line.strip()
                    break
        return edited
