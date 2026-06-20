"""
Agent 5 — Approver.

Runs a final, strict approval checklist over the assembled draft. The model
evaluates ONLY the metadata it is given (Python already produced every number).
If the model cannot return valid JSON after retries, a deterministic Python
checklist computes the same verdict so the pipeline never dies at the last step.

Temperature: 0.3
"""

import json
import logging

from app.services.blog_pipeline.schemas import ApprovalResult, AssembledDraft
from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm

logger = logging.getLogger(__name__)

APPROVER_TEMPERATURE = 0.3

_BANNED_OPENERS = (
    "in today's world", "in todays world", "in this section", "let's explore",
    "lets explore", "it is important", "in conclusion", "moreover", "furthermore",
    "additionally", "in the world of", "in this article",
)

APPROVER_PROMPT_TEMPLATE = """
ROLE: You do exactly one thing: run a final approval checklist on an assembled blog draft.

INPUT:
- title: {title}
- target_keyword: {target_keyword}
- total_word_count: {total_word_count}
- keyword_density: {keyword_density}
- thin_sections: {thin_sections}
- section_headings: {section_headings}
- first_sentence_of_each_section: {first_sentences}
- still_problematic_sections: {still_problematic}

RULES:
- Evaluate ONLY the data provided. Do not invent problems not evidenced by the input.
- Be strict on the checklist. A pass is only given when the evidence clearly supports it.
- approved must be true ONLY if ALL checklist items pass.
- The most important rule: if still_problematic_sections is non-empty, approved must be false.

CHECKLIST TO EVALUATE (return each as true/false with a reason if false):
1. word_count_adequate: total_word_count >= 3000
2. keyword_present: target_keyword appears in title
3. keyword_density_ok: keyword_density between 0.5 and 3.0
4. no_thin_sections: thin_sections list is empty
5. has_introduction: first heading contains intro/introduction/overview
6. has_conclusion: last heading contains conclusion/summary/next/wrap
7. hooks_not_generic: none of the first_sentences start with banned openers
8. no_problematic_sections: still_problematic_sections is empty

OUTPUT: Return ONLY valid JSON matching this schema. No prose. No markdown fences.
{schema}
"""

_SCHEMA_HINT = json.dumps(
    {
        "approved": False,
        "reasons": ["string reason for each failed item"],
        "checklist": {
            "word_count_adequate": True,
            "keyword_present": True,
            "keyword_density_ok": True,
            "no_thin_sections": True,
            "has_introduction": True,
            "has_conclusion": True,
            "hooks_not_generic": True,
            "no_problematic_sections": True,
        },
    },
    indent=2,
)


def _first_sentence(body: str) -> str:
    """Return the first sentence of a section body, skipping markdown headings/fences."""
    for line in (body or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "```", "-", "*", ">")):
            continue
        for sep in (". ", "! ", "? "):
            if sep in stripped:
                return stripped.split(sep, 1)[0].strip()
        return stripped
    return ""


class ApproverAgent:
    def __init__(self, llm_provider: str):
        self.llm_provider = llm_provider
        self.llm = make_llm(llm_provider, APPROVER_TEMPERATURE, max_tokens=2048)

    async def approve(
        self, draft: AssembledDraft, flagged_sections: list[str] | None = None
    ) -> ApprovalResult:
        flagged_sections = flagged_sections or []
        headings = [s.heading for s in draft.sections]
        first_sentences = [_first_sentence(s.body) for s in draft.sections]

        prompt = APPROVER_PROMPT_TEMPLATE.format(
            title=draft.title,
            target_keyword=draft.target_keyword,
            total_word_count=draft.total_word_count,
            keyword_density=round(draft.keyword_density, 3),
            thin_sections=json.dumps(draft.thin_sections, ensure_ascii=False),
            section_headings=json.dumps(headings, ensure_ascii=False),
            first_sentences=json.dumps(first_sentences, ensure_ascii=False),
            still_problematic=json.dumps(flagged_sections, ensure_ascii=False),
            schema=_SCHEMA_HINT,
        )

        try:
            result: ApprovalResult = await call_llm_with_retry(
                self.llm, prompt, ApprovalResult,
                temperature=APPROVER_TEMPERATURE, max_retries=3, agent_name="Approver",
            )
        except Exception as exc:
            logger.warning("Approver LLM failed (%s) — using deterministic Python checklist", exc)
            return self._python_approval(draft, first_sentences, flagged_sections)

        # The hard rule is non-negotiable regardless of what the model said.
        if flagged_sections:
            result.approved = False
            if "still_problematic_sections present" not in result.reasons:
                result.reasons.append("still_problematic_sections present")
            result.checklist["no_problematic_sections"] = False
        return result

    @staticmethod
    def _python_approval(
        draft: AssembledDraft, first_sentences: list[str], flagged_sections: list[str]
    ) -> ApprovalResult:
        headings = [s.heading.lower() for s in draft.sections]
        first_h = headings[0] if headings else ""
        last_h = headings[-1] if headings else ""

        def hook_ok(sentence: str) -> bool:
            s = sentence.strip().lower()
            return not any(s.startswith(op) for op in _BANNED_OPENERS)

        checklist = {
            "word_count_adequate": draft.total_word_count >= 3000,
            "keyword_present": draft.target_keyword.lower() in draft.title.lower(),
            "keyword_density_ok": 0.5 <= draft.keyword_density <= 3.0,
            "no_thin_sections": len(draft.thin_sections) == 0,
            "has_introduction": any(k in first_h for k in ("intro", "introduction", "overview")),
            "has_conclusion": any(k in last_h for k in ("conclusion", "summary", "next", "wrap")),
            "hooks_not_generic": all(hook_ok(s) for s in first_sentences) if first_sentences else False,
            "no_problematic_sections": len(flagged_sections) == 0,
        }
        reasons = [f"{k} failed" for k, ok in checklist.items() if not ok]
        return ApprovalResult(approved=all(checklist.values()), reasons=reasons, checklist=checklist)
