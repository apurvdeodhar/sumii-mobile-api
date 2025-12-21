"""Status and Health Check Endpoints

Provides health checks and progress tracking for mobile app integration.
Similar to Kubernetes liveness/readiness probes.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.conversation import Conversation
from app.models.user import User
from app.users import current_active_user

router = APIRouter(prefix="/api/v1/status", tags=["status"])


@router.get("")
async def health_check():
    """API health check endpoint

    Similar to /healthz in Kubernetes - returns service status.

    Returns:
        dict: Service health status with version and timestamp

    Use cases:
        - Mobile app checks if backend is reachable
        - Load balancer health checks
        - Monitoring systems (Datadog, CloudWatch)
    """
    return {
        "status": "healthy",
        "service": "sumii-mobile-api",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": "development",  # TODO: Make configurable via env var
    }


@router.get("/agents")
async def agent_status():
    """Agent initialization status

    Similar to checking if all microservices in your cluster are ready.
    Returns status of all 4 Mistral AI agents.

    Returns:
        dict: Agent initialization status for each agent

    Use cases:
        - Mobile app shows loading screen: "Initializing AI agents... 3/4 ready"
        - Debug tool: Check which agents failed to initialize
        - Monitoring: Alert if agents aren't all ready after X minutes

    Example response:
        {
            "total_agents": 4,
            "ready_agents": 4,
            "all_ready": true,
            "agents": {
                "router": {"status": "ready", "agent_id": "ag_xxx"},
                "intake": {"status": "ready", "agent_id": "ag_yyy"},
                "reasoning": {"status": "ready", "agent_id": "ag_zzz"},
                "summary": {"status": "ready", "agent_id": "ag_www"}
            },
            "timestamp": "2025-10-26T20:00:00Z"
        }

    Note: Agents are created on-demand, not pre-initialized.
    This endpoint shows if agents COULD be created (API key valid).
    """
    from app.config import settings

    # Check if Mistral API key is configured
    mistral_configured = bool(settings.MISTRAL_API_KEY)

    # Build agent status (all agents are created on-demand via factory)
    agent_names = ["router", "intake", "reasoning", "summary"]
    agents_status = {}

    for name in agent_names:
        # Agents are created on-demand, so we just check if factory can create them
        agents_status[name] = {
            "status": "ready" if mistral_configured else "not_configured",
            "agent_id": "Created on-demand",  # Agents are created when needed
        }

    ready_count = sum(1 for agent in agents_status.values() if agent["status"] == "ready")
    total_count = len(agents_status)

    return {
        "total_agents": total_count,
        "ready_agents": ready_count,
        "all_ready": ready_count == total_count,
        "agents": agents_status,
        "mistral_api_configured": mistral_configured,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/conversations/{conversation_id}")
async def conversation_progress(
    conversation_id: str, current_user: User = Depends(current_active_user), db: AsyncSession = Depends(get_db)
):
    """Conversation progress tracking

    Similar to checking CI/CD pipeline stages - shows conversation workflow progress.

    Args:
        conversation_id: UUID of conversation to check

    Returns:
        dict: Conversation workflow progress (which stages completed)

    Use cases:
        - Mobile app shows progress: "Facts collected ✓, Analysis pending..."
        - User can see where conversation is stuck
        - Debug: Why isn't summary generating?

    Example response:
        {
            "conversation_id": "uuid-here",
            "status": "active",
            "current_agent": "reasoning",
            "workflow_progress": {
                "facts_collection": {
                    "status": "completed",
                    "completeness": {
                        "who": true,
                        "what": true,
                        "when": true,
                        "where": true,
                        "why": true
                    }
                },
                "legal_analysis": {
                    "status": "in_progress"
                },
                "summary_generation": {
                    "status": "pending"
                }
            },
            "next_step": "Reasoning Agent analyzing and connecting facts",
            "timestamp": "2025-10-26T20:00:00Z"
        }
    """
    # Query conversation
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Verify ownership
    if conversation.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this conversation")

    # Check 5W facts completeness
    facts_completeness = {
        "who": bool(conversation.who and conversation.who.get("collected")),
        "what": bool(conversation.what and conversation.what.get("collected")),
        "when": bool(conversation.when and conversation.when.get("collected")),
        "where": bool(conversation.where and conversation.where.get("collected")),
        "why": bool(conversation.why and conversation.why.get("collected")),
    }

    all_facts_collected = all(facts_completeness.values())

    # Determine workflow progress
    workflow_progress = {
        "facts_collection": {
            "status": "completed" if all_facts_collected else "in_progress",
            "completeness": facts_completeness,
        },
        "legal_analysis": {
            "status": "completed"
            if conversation.analysis_done
            else ("in_progress" if all_facts_collected else "pending")
        },
        "summary_generation": {"status": "completed" if conversation.summary_generated else "pending"},
    }

    # Determine next step message
    if conversation.summary_generated:
        next_step = "Conversation complete - summary available"
    elif conversation.analysis_done:
        next_step = "Generating legal summary document"
    elif all_facts_collected:
        next_step = "Reasoning Agent analyzing and connecting facts"
    else:
        missing_facts = [fact for fact, collected in facts_completeness.items() if not collected]
        next_step = f"Intake Agent collecting facts: {', '.join(missing_facts)}"

    return {
        "conversation_id": str(conversation.id),
        "status": conversation.status.value,
        "current_agent": conversation.current_agent,
        "workflow_progress": workflow_progress,
        "next_step": next_step,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
