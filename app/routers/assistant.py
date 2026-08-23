"""
/api/assistant — the centralized chat assistant.

Every route declares ``get_current_user`` directly, which is what satisfies the
boot-time guard in ``app/main.py``; none of these belong in ``PUBLIC_ROUTES``.

``/ask`` deliberately does not spend a generation-quota unit. That follows the
precedent set by the other AI endpoints (``/api/plans/suggest-topics``,
``/api/instagram-analytics/strategy``): ``usage.check_and_increment`` meters
*pipeline runs*, and the billing UI surfaces its counter as such, so charging a
chat message against it would misreport what the user has spent. Volume is
throttled with a rate limit instead — which is the same thing ``auth.py`` does.
The one action that does spend quota, ``generate_content``, spends it inside
``dispatch_generation`` where it belongs.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.db.session import get_session
from app.middleware.rate_limit import limiter
from app.models.assistant import (
    AskRequest,
    AskResponse,
    CancelResponse,
    ConfirmResponse,
    ConversationDetail,
    ConversationOut,
    DigestResponse,
)
from app.services.assistant import service as assistant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/ask", response_model=AskResponse)
@limiter.limit("20/minute")
async def ask(
    request: Request,  # required by slowapi's key extraction
    payload: AskRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Answer a question from the user's own planner data.

    Writes nothing to planner tables — only chat rows and, at most, three
    ``proposed`` actions the user may later confirm.
    """
    return await assistant_service.ask(
        session, current_user["id"], payload.question, payload.conversation_id
    )


@router.post("/actions/{action_id}/confirm", response_model=ConfirmResponse)
@limiter.limit("30/minute")
async def confirm_action(
    request: Request,
    action_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Execute one previously proposed action. The only mutating path here."""
    return await assistant_service.confirm(
        session, current_user["id"], action_id, background_tasks
    )


@router.post("/actions/{action_id}/cancel", response_model=CancelResponse)
async def cancel_action(
    action_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await assistant_service.cancel(session, current_user["id"], action_id)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from app.db import queries

    return await queries.list_assistant_conversations(session, current_user["id"])


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await assistant_service.get_conversation_detail(
        session, current_user["id"], conversation_id
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from fastapi import HTTPException

    from app.db import queries

    deleted = await queries.delete_assistant_conversation(
        session, conversation_id, current_user["id"]
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"message": "Conversation deleted"}


@router.get("/digest", response_model=DigestResponse)
async def digest(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Today at a glance. No LLM call — two index reads, renders instantly."""
    return await assistant_service.digest(session, current_user["id"])
