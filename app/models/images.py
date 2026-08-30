"""HTTP shapes for the Image Studio — a raw prompt straight to Gemini.

The planner's image route wraps every prompt in ``build_instagram_prompt``
(palette + layout + a fixed quality suffix), because there the image is a post
background for a plan item. This surface deliberately does not: the whole point
is that what the user types is what gets rendered.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.services.gemini_image_client import _ASPECT_RATIO_ENUM, _IMAGE_SIZE_ENUM

# Closed vocabularies, taken from the client's own enum maps so the two cannot
# drift. Anything outside them is a 422 rather than a 400 from Google.
AspectRatio = Literal[tuple(_ASPECT_RATIO_ENUM)]  # type: ignore[valid-type]
ImageSize = Literal[tuple(_IMAGE_SIZE_ENUM)]      # type: ignore[valid-type]

# Gemini's own ceiling for a seed is a uint32.
MAX_SEED = 2**31 - 1


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)

    # Gemini exposes no negative-prompt field, so the client states exclusions as
    # an instruction inside the positive prompt. Kept separate in the API so the
    # UI (and the stored row) can show what was asked for.
    negative_prompt: Optional[str] = Field(default=None, max_length=2000)

    aspect_ratio: AspectRatio = "1:1"
    image_size: ImageSize = "1K"

    # An alias, never a raw model id: this field is user-supplied, and an open
    # string would let a caller bill us against any model on the account. Same
    # reasoning as GenerateImageRequest in models/planner.py.
    model: Optional[Literal["gemini_flash", "gemini_flash_lite", "gemini_pro"]] = None

    seed: Optional[int] = Field(default=None, ge=0, le=MAX_SEED)

    @field_validator("prompt", "negative_prompt")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip() or None

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, v: Optional[str]) -> str:
        if not v:
            raise ValueError("Prompt cannot be empty.")
        return v


class GeneratedImageOut(BaseModel):
    """One gallery row. The bytes are fetched separately from ``/file``."""

    id: str
    prompt: str
    negative_prompt: Optional[str] = None
    model: str
    aspect_ratio: str
    image_size: str
    seed: Optional[int] = None
    duration_s: Optional[float] = None
    created_at: Optional[str] = None


class ImageGenerateResponse(GeneratedImageOut):
    """The render that just happened, with the image inline.

    ``image_b64`` saves the page a second round trip for the one image the user
    is waiting on; the gallery below it loads through ``/file`` instead, so a
    long history never has to be base64'd into one response.
    """

    image_b64: str


class GeneratedImageList(BaseModel):
    total: int
    images: list[GeneratedImageOut] = []
