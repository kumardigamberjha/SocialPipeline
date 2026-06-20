"""
Agent 4 — Approver.

The final gate. The verdict is a pure function of the Python QA results and the
editor's still_weak flag — no LLM call needed.
"""

from app.services.linkedin_pipeline.schemas import ApprovalResult

# Maps the final checklist key -> (qa_results key, plain-English failure reason).
_CHECK_MAP = {
    "word_count_ok": ("passes_word_count", "post is outside the 150-300 word range"),
    "hashtag_count_ok": ("passes_hashtag_count", "post does not have 3-5 hashtags"),
    "line_length_ok": ("passes_line_length", "one or more lines exceed 12 words"),
    "hook_not_generic": ("passes_hook", "the hook uses a banned generic opener"),
    "no_banned_words": ("passes_banned_words", "banned words/phrases are present"),
    "single_cta": ("passes_cta", "post does not have exactly one CTA"),
    "no_wall_of_text": ("passes_white_space", "post has a wall-of-text paragraph"),
}


def _deterministic_checklist(qa_results: dict, still_weak: bool) -> dict[str, bool]:
    checklist = {key: bool(qa_results.get(qa_key, False)) for key, (qa_key, _) in _CHECK_MAP.items()}
    checklist["not_flagged_by_editor"] = not still_weak
    return checklist


def _deterministic_result(qa_results: dict, still_weak: bool) -> ApprovalResult:
    checklist = _deterministic_checklist(qa_results, still_weak)
    reasons = [reason for key, (_, reason) in _CHECK_MAP.items() if not checklist[key]]
    if still_weak:
        reasons.append("editor flagged the post as still weak after the 2 rewrite cycles")
    return ApprovalResult(approved=all(checklist.values()), reasons=reasons, checklist=checklist)


class LinkedInApproverAgent:
    def __init__(self, llm_provider: str):
        pass

    async def approve(self, topic: str, qa_results: dict, still_weak: bool) -> ApprovalResult:
        # Verdict is a pure function of the QA numbers — deterministic Python is
        # authoritative, so there is no need for an LLM round-trip here.
        return _deterministic_result(qa_results, still_weak)
