"""AI Analysis Engine for Short-Form & Instagram Reels Prospect Audits.

Leverages Gemini 3.8 / 3.6 Flash and our tier fallback cascade to generate:
1. Executive Short-Form Opportunity Summary
2. 5 Viral Reel / Short Conversion Blueprints (Timestamps, 3s Hooks, Visual Direction)
3. 5 Hook Teardowns & Viral Rewrites
4. 30-Day Short-Form Content Sprint
5. Turnkey Cold Outreach Pitch Copy
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import Field

from app.config import get_settings
from app.models.shortform_prospects import (
    HookTeardown,
    ReelConversionBlueprint,
    ShortFormOutreachCopy,
    ShortFormSprintDay,
)
from app.services.blog_pipeline.utils import CoercingBaseModel, call_llm_with_retry
from app.services.youtube_ai_analysis import audit_scope

logger = logging.getLogger(__name__)

ANALYSIS_TEMPERATURE = 0.4


class ShortFormAnalysisOutput(CoercingBaseModel):
    executive_summary: str = ""
    blueprints: List[ReelConversionBlueprint] = Field(default_factory=list)
    hook_teardowns: List[HookTeardown] = Field(default_factory=list)
    sprint_calendar: List[ShortFormSprintDay] = Field(default_factory=list)
    outreach_copy: ShortFormOutreachCopy


SHORTFORM_PROMPT_TEMPLATE = """ROLE: You are an elite Short-Form Content Director & Virality Strategist (specializing in Instagram Reels, YouTube Shorts, and TikTok).
You are analyzing a creator or brand's public profile and video portfolio to generate a high-ticket "Short-Form Content Repurposing & Growth Audit".

TARGET PROFILE:
- Platform: {platform}
- Channel / Account Name: {title}
- Handle: {handle}
- Audience: {followers_or_subs:,} followers/subscribers
- Total Catalog: {total_videos_or_posts} videos/posts
- Short-Form Gap Analysis: {shorts_count} Shorts vs {longform_count} Long-form videos ({shorts_ratio_pct:.1f}% short-form ratio).
- Estimated Missed Top-of-Funnel Reach: ~{estimated_missed_views:,} views.

RECENT PORTFOLIO CONTEXT:
{portfolio_context}

YOUR MANDATE:
Generate an institutional-grade Short-Form Audit report adhering strictly to these virality principles:
1. Long-Form to Short-Form Arbitrage: Identify high-performing topics and extract the top 5 viral Reel clip blueprints. Every blueprint MUST specify an exact 3-second spoken hook that interrupts scrolling, a visual B-roll direction, and pacing notes.
2. Hook Teardowns: Take 5 real or representative angles from their content and perform an aggressive audit: explain why the opening causes retention drop-off, and write TWO high-converting viral rewrites utilizing proven retention frameworks (Curiosity Gap, Negation, Contrarian, Time-Arbitrage).
3. 30-Day Short-Form Sprint: Generate a comprehensive publishing schedule across 4 weeks with a balanced mix of 3 core pillars:
   - Authority & Proof (40%)
   - Problem-Agitation & Mistakes (35%)
   - Viral Relatability & Rapid Hacks (25%)
4. Turnkey Cold Outreach Copy: Write a hyper-personalized, non-salesy cold email, Instagram DM, and follow-up bump referencing their exact video topics and short-form gap.

OUTPUT FORMAT:
Return ONLY valid JSON matching this structure exactly without prose or markdown fences:
{{
  "executive_summary": "3-4 concise, data-driven sentences diagnosing their current short-form gap and the exact commercial opportunity of scaling Reels/Shorts.",
  "blueprints": [
    {{
      "source_title": "Title of video or core topic",
      "source_url": null,
      "clip_timestamp_start": "02:15",
      "clip_timestamp_end": "03:05",
      "duration_seconds": 50,
      "viral_hook_3s": "High-impact opening sentence spoken in the first 3 seconds",
      "visual_hook_prompt": "Visual direction for the first frame and dynamic B-roll elements",
      "pacing_and_sound": "Pacing speed (e.g. cuts every 2.2s, trending tech lofi or punchy beat)",
      "caption": "Punchy caption with call to save and 4-5 targeted hashtags",
      "estimated_viral_score": 94
    }}
  ],
  "hook_teardowns": [
    {{
      "original_angle": "The original slow or passive topic title",
      "weakness_diagnosis": "Why this loses 60% of viewers in the first 3 seconds",
      "viral_rewrite_1": "High-urgency rewrite variant A",
      "viral_rewrite_2": "Contrarian / curiosity rewrite variant B",
      "framework_used": "e.g. The Contrarian Reality Framework"
    }}
  ],
  "sprint_calendar": [
    {{
      "day_number": 1,
      "week_number": 1,
      "pillar": "Authority & Proof",
      "topic": "Concrete short-form working topic",
      "hook": "Spoken hook sentence",
      "format_style": "Talking Head + Fast Screen B-Roll",
      "target_cta": "Comment 'SYSTEM' for the full code"
    }}
  ],
  "outreach_copy": {{
    "cold_email_subject": "quick short-form audit for {handle}",
    "cold_email_body": "3-paragraph personalized pitch referencing their videos and offering the 5 free clip blueprints",
    "dm_pitch": "Under 60 words, casual, high-converting direct message",
    "followup_bump": "2-line friendly bump message"
  }}
}}
"""


def _build_analysis_llm():
    from app.llm import build_fallback_cascade
    settings = get_settings()
    primary_llm, fallback_chain = build_fallback_cascade(
        settings,
        temperature=ANALYSIS_TEMPERATURE,
        is_audit=True,
    )
    model = getattr(primary_llm, "model", None) or settings.audit_model or "gemini/gemini-3.8-flash"
    return primary_llm, fallback_chain, model


async def generate_shortform_audit(
    platform: str,
    title: str,
    handle: str,
    followers_or_subs: int,
    total_videos_or_posts: int,
    shorts_count: int,
    longform_count: int,
    shorts_ratio_pct: float,
    estimated_missed_views: int,
    portfolio_context: str,
) -> tuple[ShortFormAnalysisOutput, str]:
    """Runs the AI short-form audit pipeline under audit_scope."""
    with audit_scope():
        llm, fallback_chain, model = _build_analysis_llm()
        used: dict = {}

        prompt = SHORTFORM_PROMPT_TEMPLATE.format(
            platform=platform,
            title=title,
            handle=handle,
            followers_or_subs=followers_or_subs,
            total_videos_or_posts=total_videos_or_posts,
            shorts_count=shorts_count,
            longform_count=longform_count,
            shorts_ratio_pct=shorts_ratio_pct,
            estimated_missed_views=estimated_missed_views,
            portfolio_context=portfolio_context,
        )

        result: ShortFormAnalysisOutput = await call_llm_with_retry(
            llm,
            prompt,
            ShortFormAnalysisOutput,
            temperature=ANALYSIS_TEMPERATURE,
            max_retries=3,
            agent_name="ShortFormProspectAuditor",
            fallback_chain=fallback_chain,
            used=used,
        )

        effective_model = used.get("model") or model
        return result, effective_model
