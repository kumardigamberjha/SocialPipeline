"""
Pydantic models representing Supabase database tables for type safety and fast serialization.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

# ── 1. Users ──
class UserCreate(BaseModel):
    id: str # Supabase auth.uid
    email: str
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

class User(UserCreate):
    pass

# ── 2. Projects ──
class ProjectCreate(BaseModel):
    user_id: str
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

class Project(ProjectCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

# ── 3. Agent Runs ──
class AgentRunCreate(BaseModel):
    project_id: Optional[str] = None
    user_id: str
    topic: str
    provider_used: str
    status: str = "running" # running, completed, failed
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

class AgentRun(AgentRunCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    final_result: Optional[str] = None

# ── 4. Task Steps ──
class TaskStepCreate(BaseModel):
    run_id: str
    agent_name: str
    task_name: str
    status: str = "pending" # pending, in_progress, done, error
    output: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

class TaskStep(TaskStepCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    completed_at: Optional[datetime] = None

# ── 5. Messages (Memory/Chat History) ──
class MessageCreate(BaseModel):
    run_id: str
    user_id: str
    role: str # user, assistant, system
    content: str
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

class Message(MessageCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

# ── 6. API Keys (Per-user configs) ──
class ApiKeyCreate(BaseModel):
    user_id: str
    provider: str # openai, anthropic, groq, nvidia
    api_key_encrypted: str
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

class ApiKey(ApiKeyCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

# ── 7. Usage Logs ──
class UsageLogCreate(BaseModel):
    user_id: str
    run_id: Optional[str] = None
    provider: str
    model: str
    tokens_prompt: int = 0
    tokens_completion: int = 0
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

class UsageLog(UsageLogCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
