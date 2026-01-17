"""ThinkingBlock Pydantic Schemas

TypeSync will convert these to TypeScript types.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ThinkingBlockResponse(BaseModel):
    """ThinkingBlock response for API and sync"""

    id: UUID
    conversation_id: UUID
    current_agent: str | None
    completed_agents: list[str]
    is_generating_summary: bool
    is_live: bool
    created_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True
