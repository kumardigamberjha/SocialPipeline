"""FastAPI Router for Short-Form & Instagram Reels Prospect Audits."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth_deps import get_current_user
from app.models.shortform_prospects import (
    ProspectStatus,
    ShortFormAuditReport,
    ShortFormGenerateRequest,
    ShortFormLookupRequest,
    ShortFormProfile,
)
from app.services import shortform_prospect_service as service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shortform-prospects", tags=["Short-Form Prospects"])


class StatusUpdateRequest(BaseModel):
    status: ProspectStatus


@router.post("/lookup")
async def lookup_creator(
    req: ShortFormLookupRequest,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Resolves a creator profile on YouTube or Instagram and evaluates short-form gap metrics."""
    try:
        profile, videos = await service.resolve_candidate(req.platform, req.query)
        gap_metrics = service.compute_gap_metrics(videos, profile)
        return {
            "profile": profile.model_dump(),
            "gap_metrics": gap_metrics.model_dump(),
            "sample_videos_count": len(videos),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Shortform creator lookup failed")
        raise HTTPException(status_code=500, detail=f"Failed to resolve creator: {e}")


@router.post("/generate")
async def generate_shortform_audit(
    req: ShortFormGenerateRequest,
    user: dict = Depends(get_current_user),
) -> ShortFormAuditReport:
    """Generates the full Short-Form & Reels virality audit and 30-day sprint deliverable."""
    try:
        profile, videos = await service.resolve_candidate(req.platform, req.identifier)
        report = await service.generate_shortform_report(profile, videos)
        return report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Shortform audit generation failed")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")


@router.get("/list")
async def list_reports(
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Lists all generated short-form prospect reports."""
    reports = service.list_saved_reports()
    return {"items": [r.model_dump() for r in reports]}


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    user: dict = Depends(get_current_user),
) -> ShortFormAuditReport:
    """Retrieves a generated report by ID."""
    report = service.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    return report


@router.patch("/{report_id}/status")
async def update_status(
    report_id: str,
    req: StatusUpdateRequest,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Updates the cold outreach status of a report."""
    report = service.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    report.outreach_status = req.status
    return {"status": report.outreach_status, "report_id": report_id}
