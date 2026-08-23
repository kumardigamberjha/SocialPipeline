"""HTTP shapes for the assistant.

Plain ``BaseModel`` — these validate requests from the dashboard and document
responses. The LLM contract lives in ``app/services/assistant/schemas.py`` and
subclasses ``CoercingBaseModel`` instead, because model output needs repair and
user input needs rejection.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[str] = None


class ResolvedRange(BaseModel):
    """Echoed back so a mis-parsed date phrase is visible, not silent."""

    intent: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    platforms: list[str] = []


class ActionOut(BaseModel):
    id: str
    message_id: Optional[str] = None
    verb: str
    label: str
    item_id: str
    content_id: Optional[str] = None
    item_topic: str = ""
    item_platform: str = ""
    params: dict = {}
    status: str
    expires_at: Optional[str] = None


class SourceRef(BaseModel):
    kind: Literal["plan_item", "review", "backlog", "report", "analytics"]
    id: str
    label: str
    platform: Optional[str] = None


class AskResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer_markdown: str
    resolved: ResolvedRange
    actions: list[ActionOut] = []
    sources: list[SourceRef] = []
    meta: dict = {}


class ConfirmResponse(BaseModel):
    action: ActionOut
    item: Optional[dict] = None
    content: Optional[dict] = None
    dispatched: list[Any] = []


class CancelResponse(BaseModel):
    action: ActionOut


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int = 0


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: Optional[str] = None
    meta: dict = {}


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut] = []
    actions: list[ActionOut] = []


class DigestResponse(BaseModel):
    today: str
    week_from: str
    week_to: str
    items_today: list[dict] = []
    items_this_week: int = 0
    pending_review: int = 0
    backlog_uncovered: int = 0
    overdue: int = 0
