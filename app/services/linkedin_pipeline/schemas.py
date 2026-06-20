"""
Pydantic JSON contracts for the lean 4-agent LinkedIn pipeline.

These are the *only* shapes accepted between agents. Every LLM output is parsed
and validated against one of these models before it flows to the next stage
(see app.services.blog_pipeline.utils.call_llm_with_retry).

Load-bearing content fields (topic, selected_hook, body, revised_post, ...) stay
required so a useless completion is rejected and retried. Auxiliary fields
(violations, flags, checklist) default to a safe value so a sloppy 7B completion
that merely omits an extra field still validates instead of forcing a retry.

The enum/length validators below are intentional contracts: a wrong angle_type or
the wrong number of hooks IS a failed generation and should be retried.
"""

from pydantic import BaseModel, Field, field_validator

ANGLE_TYPES = {"story", "contrarian", "how-to", "lesson-learned"}
CTA_TYPES = {"question", "soft-ask", "observation"}


class AnglePack(BaseModel):
    topic: str
    angle_type: str                                       # story / contrarian / how-to / lesson-learned
    hook_options: list[str] = Field(default_factory=list)  # exactly 3 hooks, each under 15 words
    selected_hook: str                                    # strongest hook chosen from hook_options
    cta_type: str                                         # question / soft-ask / observation

    @field_validator("angle_type")
    @classmethod
    def validate_angle(cls, v: str) -> str:
        if v not in ANGLE_TYPES:
            raise ValueError(f"angle_type must be one of {sorted(ANGLE_TYPES)}")
        return v

    @field_validator("cta_type")
    @classmethod
    def validate_cta(cls, v: str) -> str:
        if v not in CTA_TYPES:
            raise ValueError(f"cta_type must be one of {sorted(CTA_TYPES)}")
        return v

    @field_validator("hook_options")
    @classmethod
    def validate_hooks(cls, v: list[str]) -> list[str]:
        if len(v) != 3:
            raise ValueError("hook_options must contain exactly 3 hooks")
        return v


class PostDraft(BaseModel):
    hook: str                                             # first 1-2 lines — must match selected_hook
    body: str                                             # main content — short lines, white space
    cta: str                                              # single CTA — question or soft ask
    hashtags: list[str] = Field(default_factory=list)     # 3-5 hashtags, lowercase, no # prefix
    full_post: str = ""                                   # hook + body + cta + hashtags rendered (synthesized if blank)

    @field_validator("hashtags")
    @classmethod
    def validate_hashtags(cls, v: list[str]) -> list[str]:
        if not (3 <= len(v) <= 5):
            raise ValueError("hashtags must have 3 to 5 items")
        return [tag.lower().lstrip("#") for tag in v]


class StyleViolation(BaseModel):
    rule: str = ""                                        # which checklist item failed
    offending_text: str = ""                              # exact quote of the problem
    fix_applied: str = ""                                 # what was changed


class EditedPost(BaseModel):
    revised_post: str                                     # complete revised post text
    hook_line: str = ""                                   # extracted first line of revised_post
    violations_fixed: list[StyleViolation] = Field(default_factory=list)
    still_weak: bool = False                              # True if violations remain after 2 cycles


class ApprovalResult(BaseModel):
    approved: bool = False
    reasons: list[str] = Field(default_factory=list)      # specific reasons if not approved — empty if approved
    checklist: dict[str, bool] = Field(default_factory=dict)  # each checklist item name → True/False
