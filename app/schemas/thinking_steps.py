"""ThinkingSteps Pydantic Schemas

TypeSync will convert these to TypeScript types.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ThinkingStep(BaseModel):
    """Individual agent step within a ThinkingSteps"""

    agent_id: str  # router, intake, fact_completion, reasoning, wrapup, summary
    title: str  # Human-readable description
    status: str  # pending, active, complete
    timestamp: datetime
    preview_text: str | None = None  # Last ~120 chars of agent output for UI preview


class ThinkingStepsResponse(BaseModel):
    """ThinkingSteps response for API and sync"""

    id: UUID
    conversation_id: UUID
    message_id: UUID | None  # User message that triggered this thinking steps
    current_agent: str | None
    completed_agents: list[str]
    steps: list[ThinkingStep]
    is_generating_summary: bool
    is_live: bool
    created_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True
