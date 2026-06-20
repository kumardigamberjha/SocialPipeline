"""
Pydantic JSON contracts for the 5-agent blog pipeline.

These are the *only* shapes accepted between agents. Every LLM output is parsed
and validated against one of these models before it is allowed to flow to the
next stage (see app.services.blog_pipeline.utils.call_llm_with_retry).

List fields default to empty and most flags default to a safe value so that a
sloppy 7B completion that omits an auxiliary field still validates instead of
forcing a needless retry. The load-bearing content fields (heading, body, etc.)
stay required.
"""

from pydantic import BaseModel, Field


class SectionOutline(BaseModel):
    heading: str
    intent: str                                              # what this section must accomplish for the reader
    key_points: list[str] = Field(default_factory=list)      # 3-6 bullet points the writer must cover
    source_snippets: list[str] = Field(default_factory=list) # real excerpts from fetched pages (max 5 per section)
    word_target: int = 500                                   # target word count for this section


class GroundingPack(BaseModel):
    title: str
    target_keyword: str
    outline: list[SectionOutline] = Field(default_factory=list)
    serp_gaps: list[str] = Field(default_factory=list)       # what competitors missed — the SEO edge


class SectionDraft(BaseModel):
    heading: str
    body_markdown: str
    claims_used: list[str] = Field(default_factory=list)     # which source_snippets were drawn from


class StyleViolation(BaseModel):
    rule: str = ""
    location: str = ""                                       # quote of the offending text
    fix_applied: str = ""                                    # what the editor changed it to


class EditedSection(BaseModel):
    heading: str
    revised_body: str
    violations_fixed: list[StyleViolation] = Field(default_factory=list)
    still_problematic: bool = False                          # True = flag for human review after 2 cycles


class SectionQAResult(BaseModel):
    heading: str
    body: str
    word_count: int = 0                                      # Python-counted, never model-counted
    keyword_present: bool = False
    thin_flag: bool = False                                  # True if word_count < word_target * 0.8
    h3_count: int = 0
    rewrite_needed: bool = False


class AssembledDraft(BaseModel):
    title: str
    target_keyword: str
    sections: list[SectionQAResult] = Field(default_factory=list)
    total_word_count: int = 0                                # Python sum of all section word counts
    thin_sections: list[str] = Field(default_factory=list)   # headings of sections that need rewrite
    keyword_density: float = 0.0                             # (keyword_occurrences / total_words) * 100


class ApprovalResult(BaseModel):
    approved: bool = False
    reasons: list[str] = Field(default_factory=list)         # specific reasons if not approved
    checklist: dict[str, bool] = Field(default_factory=dict) # each checklist item → pass/fail
