"""Pydantic schemas for the lean YouTube script pipeline."""

from pydantic import BaseModel, Field


class ScriptDraft(BaseModel):
    title: str = Field(description="Working video title")
    script: str = Field(description="Full markdown script with [VISUAL CUE]/[B-ROLL]/[ENERGY] tags")


class SeoPack(BaseModel):
    seo_title: str = Field(description="Click-optimized YouTube title, under 70 chars")
    seo_description: str = Field(description="YouTube description with keywords and timestamps placeholder")
    seo_tags: list[str] = Field(default_factory=list, description="10+ relevant tags")
