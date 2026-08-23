"""
Personal Intelligence — user-defined rules the LLM must obey, and tracked
goals whose progress is read from synced YouTube analytics.

Both are rendered into a single text block (app.services.personal_intelligence)
that every content-generation surface injects into its prompts. This router is
pure CRUD plus goal progress; the injection wiring lives in the services that
consume ``get_directives`` / ``get_directives_sync``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.db import queries
from app.db.session import get_session
from app.models.personal_intelligence import GoalCreate, GoalUpdate, RuleCreate, RuleUpdate
from app.services import goal_service
from app.services.personal_intelligence import (
    RULES_CHAR_BUDGET,
    build_intelligence_block,
    bump_intelligence_epoch,
    render_directives,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/personal-intelligence", tags=["Personal Intelligence"])

MAX_ACTIVE_RULES = 50


# ── Rules ────────────────────────────────────────────────────────────────────


@router.get("/rules")
async def list_rules(
    scope: str | None = None,
    include_inactive: bool = False,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await queries.list_user_rules(
        session, current_user["id"], scope=scope, active_only=not include_inactive
    )


@router.post("/rules")
async def create_rule(
    request: RuleCreate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    active = await queries.list_user_rules(session, current_user["id"], active_only=True)
    if len(active) >= MAX_ACTIVE_RULES:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum of {MAX_ACTIVE_RULES} active rules reached. Deactivate one first.",
        )
    row = await queries.create_user_rule(
        session,
        current_user["id"],
        scope=request.scope,
        category=request.category,
        rule_text=request.rule_text,
        priority=request.priority,
        is_active=request.is_active,
    )
    await bump_intelligence_epoch(current_user["id"])
    return row


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    request: RuleUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await queries.get_user_rule(session, rule_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Rule not found")
    await queries.update_user_rule(
        session,
        rule_id,
        current_user["id"],
        scope=request.scope,
        category=request.category,
        rule_text=request.rule_text,
        priority=request.priority,
        is_active=request.is_active,
    )
    await bump_intelligence_epoch(current_user["id"])
    return await queries.get_user_rule(session, rule_id, current_user["id"])


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await queries.delete_user_rule(session, rule_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Rule not found")
    await bump_intelligence_epoch(current_user["id"])
    return {"message": "Rule deleted"}


# ── Goals ────────────────────────────────────────────────────────────────────


@router.get("/goals")
async def list_goals(
    status: str | None = "active",
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    goals = await queries.list_user_goals(session, current_user["id"], status=status)
    return [goal_service.compute_progress(g) for g in goals]


@router.post("/goals")
async def create_goal(
    request: GoalCreate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    baseline, _ = await goal_service.read_metric(session, current_user["id"], request.metric)
    row = await queries.create_user_goal(
        session,
        current_user["id"],
        title=request.title,
        metric=request.metric,
        target_value=request.target_value,
        deadline=request.deadline,
        platform=request.platform,
        description=request.description,
        baseline_value=baseline or 0.0,
    )
    await bump_intelligence_epoch(current_user["id"])
    return goal_service.compute_progress(row)


@router.patch("/goals/{goal_id}")
async def update_goal(
    goal_id: str,
    request: GoalUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await queries.get_user_goal(session, goal_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Goal not found")
    await queries.update_user_goal(
        session,
        goal_id,
        current_user["id"],
        title=request.title,
        description=request.description if request.description is not None else queries.UNSET,
        target_value=request.target_value,
        deadline=request.deadline,
        status=request.status,
    )
    await bump_intelligence_epoch(current_user["id"])
    goal = await queries.get_user_goal(session, goal_id, current_user["id"])
    return goal_service.compute_progress(goal)


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await queries.delete_user_goal(session, goal_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Goal not found")
    await bump_intelligence_epoch(current_user["id"])
    return {"message": "Goal deleted"}


@router.post("/goals/{goal_id}/refresh")
async def refresh_goal(
    goal_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    goal = await queries.get_user_goal(session, goal_id, current_user["id"])
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    current, _ = await goal_service.read_metric(session, current_user["id"], goal["metric"])
    progress = goal_service.compute_progress(goal, current_value=current)
    await queries.update_user_goal(session, goal_id, current_user["id"], progress=progress["progress"])
    return progress


# ── Preview ──────────────────────────────────────────────────────────────────


@router.get("/preview")
async def preview_directives(
    scope: str = "global",
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The exact text block that will be injected into prompts for ``scope``."""
    rules = await queries.list_user_rules(session, current_user["id"], scope=scope, active_only=True)
    goals = await queries.list_user_goals(session, current_user["id"], status="active")
    goals = [goal_service.compute_progress(g) for g in goals]
    block = render_directives(rules, goals)
    return {
        "directives": block,
        "char_count": len(block),
        "rule_count": len(rules),
        "goal_count": len(goals),
        "rules_char_budget": RULES_CHAR_BUDGET,
    }
