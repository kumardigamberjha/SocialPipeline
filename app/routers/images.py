"""
/api/images — the Image Studio: a prompt in, a picture out.

The same Gemini client the planner uses, minus the Instagram prompt engine. The
planner renders a *post background* for a plan item, so it wraps every prompt in
palette + layout + a quality suffix (``build_instagram_prompt``). Here the user's
words are the prompt, because that is the entire feature.

Two things are load-bearing:

**Renders are not static files.** ``settings.image_output_dir`` is deliberately
never mounted — see ``planner.get_item_image``: under docker-compose the
dashboard cannot read the API's disk anyway, and a mount would make every
tenant's images public to anyone who guessed a filename. A row in
``generated_images`` proves ownership, then the bytes are streamed.

**A render costs an API call**, so this is rate limited, following the same
reasoning as ``assistant.ask``: ``usage.check_and_increment`` meters *pipeline
runs* and the billing UI reports it as such, so charging an image against it
would misreport what the user spent. Volume is throttled instead.
"""

import base64
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.db import queries
from app.db.session import get_session
from app.middleware.rate_limit import limiter
from app.models.images import (
    GeneratedImageList,
    GeneratedImageOut,
    ImageGenerateRequest,
    ImageGenerateResponse,
)
from app.services.gemini_image_client import (
    OUTPUT_DIR as IMAGE_DIR,
    GeminiImageClient,
    resolve_model,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/images", tags=["images"])

_client = GeminiImageClient()

MAX_PAGE = 100


def _image_path(filename: str):
    """Resolve a stored name inside IMAGE_DIR, refusing anything outside it.

    Same guard as ``planner._image_path``. The name is read back from our own
    table, but it reached that table through a request handler, so it stays
    untrusted: without this a crafted filename turns the GET below into an
    arbitrary-file read.
    """
    candidate = (IMAGE_DIR / filename).resolve()
    if candidate.parent != IMAGE_DIR.resolve() or not candidate.is_file():
        return None
    return candidate


def _compose_prompt(prompt: str, negative_prompt: str | None) -> str:
    """Fold exclusions into the positive prompt.

    Gemini's generateContent takes no negative-prompt field, so the only way to
    express "not this" is to say so in the prompt — which is what
    ``build_instagram_prompt`` does with its own NEGATIVE_PROMPT constant.
    """
    if not negative_prompt:
        return prompt
    return f"{prompt}\n\nDo not render any of the following: {negative_prompt}."


@router.post("/generate", response_model=ImageGenerateResponse)
@limiter.limit("10/minute")
async def generate_image(
    request: Request,  # required by slowapi's key extraction
    payload: ImageGenerateRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await _client.health_check():
        raise HTTPException(
            status_code=503,
            detail="Gemini image generation is unavailable. Check GEMINI_API_KEY and GEMINI_IMAGE_MODEL.",
        )

    model_id = resolve_model(payload.model)
    full_prompt = _compose_prompt(payload.prompt, payload.negative_prompt)

    t0 = time.time()
    try:
        images = await _client.generate(
            full_prompt,
            model=model_id,
            aspect_ratio=payload.aspect_ratio,
            image_size=payload.image_size,
            seed=payload.seed,
        )
    except Exception as exc:
        # The client raises with Google's own reason (quota, safety block, bad
        # model); pass it through rather than a bare 502.
        logger.error("Image studio generation failed for %s: %s", current_user["id"], exc)
        raise HTTPException(status_code=502, detail=f"Image generation failed: {exc}")

    if not images:
        raise HTTPException(status_code=502, detail="Gemini returned no image.")

    duration_s = round(time.time() - t0, 2)
    raw = images[0]

    # File first, row second. The reverse order can leave a row pointing at
    # nothing, which 404s in the gallery forever; this order can at worst leave
    # an unreferenced file, which is merely untidy. The name is independent of
    # the row id so neither write has to wait on the other.
    filename = f"studio_{uuid.uuid4().hex}.png"
    (IMAGE_DIR / filename).write_bytes(raw)

    row = await queries.create_generated_image(
        session,
        current_user["id"],
        prompt=payload.prompt,
        negative_prompt=payload.negative_prompt,
        model=model_id,
        aspect_ratio=payload.aspect_ratio,
        image_size=payload.image_size,
        seed=payload.seed,
        filename=filename,
        duration_s=duration_s,
    )

    return ImageGenerateResponse(
        **_out(row).model_dump(),
        image_b64=base64.b64encode(raw).decode(),
    )


def _out(row: dict) -> GeneratedImageOut:
    return GeneratedImageOut(
        id=row["id"],
        prompt=row["prompt"],
        negative_prompt=row.get("negative_prompt"),
        model=row["model"],
        aspect_ratio=row["aspect_ratio"],
        image_size=row["image_size"],
        seed=row.get("seed"),
        duration_s=row.get("duration_s"),
        created_at=row.get("created_at"),
    )


@router.get("", response_model=GeneratedImageList)
async def list_images(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The user's gallery, newest first. Metadata only — bytes come from /file."""
    limit = max(1, min(limit, MAX_PAGE))
    offset = max(0, offset)
    rows = await queries.get_generated_images(
        session, current_user["id"], limit=limit, offset=offset
    )
    total = await queries.count_generated_images(session, current_user["id"])
    return GeneratedImageList(total=total, images=[_out(r) for r in rows])


@router.get("/{image_id}/file")
async def get_image_file(
    image_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Stream one render. The owner-scoped read is the authorization."""
    row = await queries.get_generated_image(session, image_id, current_user["id"])
    if not row:
        # 404 for both "no such image" and "not yours", deliberately
        # indistinguishable — probing an id should not confirm it exists.
        raise HTTPException(status_code=404, detail="Image not found")

    path = _image_path(row["filename"])
    if path is None:
        raise HTTPException(status_code=404, detail="Image file is missing from disk")
    return FileResponse(path, media_type="image/png")


@router.delete("/{image_id}")
async def delete_image(
    image_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await queries.get_generated_image(session, image_id, current_user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")

    await queries.delete_generated_image(session, image_id, current_user["id"])

    # Best-effort: an orphaned file is untidy, a failed delete is not worth a 500
    # once the row (and so the only way to reach it) is already gone.
    path = _image_path(row["filename"])
    if path is not None:
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Could not remove image file %s: %s", row["filename"], exc)

    return {"deleted": image_id}
