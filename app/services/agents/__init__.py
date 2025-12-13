"""Mistral AI Agents for Legal Intake Workflow

This package provides specialized AI agents for Sumii's legal intake process:
- Router Agent: Orchestrates workflow
- Intake Agent: Collects facts (5W framework)
- Reasoning Agent: Applies German Civil Law (BGB)
- Summary Agent: Generates professional documents

Architecture: Mistral Agents API (cloud-hosted)
Benefits: Fast implementation, built-in orchestration, production-ready

Agent Flow:
User → Router → Intake → Reasoning → Summary → PDF Download
"""

from app.services.agents.intake import create_intake_agent
from app.services.agents.reasoning import create_reasoning_agent
from app.services.agents.router import create_router_agent
from app.services.agents.summary import create_summary_agent

__all__ = [
    "create_router_agent",
    "create_intake_agent",
    "create_reasoning_agent",
    "create_summary_agent",
    "MistralAgentsService",
]


class MistralAgentsService:
    """Service for managing all Mistral AI Agents

    This service provides a convenient interface to create and manage
    all 4 specialized agents for the legal intake workflow.
    """

    def __init__(self):
        """Initialize service with empty agent registry"""
        self.agents: dict[str, str] = {}

    async def initialize_all_agents(self) -> dict[str, str]:
        """Create all 4 agents and store their IDs

        With Conversations API, handoffs are configured via agent instructions,
        not via UPDATE calls. Mistral's Conversations API handles handoff orchestration
        automatically when using handoff_execution="server".

        Returns:
            dict[str, str]: Mapping of agent names to agent IDs
        """
        # Create all agents (handoffs configured in their instructions)
        intake_id = create_intake_agent()
        reasoning_id = create_reasoning_agent()
        summary_id = create_summary_agent()
        router_id = create_router_agent()

        # Store all agent IDs
        self.agents = {
            "router": router_id,
            "intake": intake_id,
            "reasoning": reasoning_id,
            "summary": summary_id,
        }

        return self.agents

    def get_agent_id(self, agent_name: str) -> str | None:
        """Get agent ID by name

        Args:
            agent_name: Name of agent ("router", "intake", "reasoning", "summary")

        Returns:
            str | None: Agent ID if exists, None otherwise
        """
        return self.agents.get(agent_name)


# Global service instance
_mistral_agents_service: MistralAgentsService | None = None


def get_mistral_agents_service() -> MistralAgentsService:
    """Get or create global Mistral Agents service instance

    Returns:
        MistralAgentsService: Singleton service instance
    """
    global _mistral_agents_service
    if _mistral_agents_service is None:
        _mistral_agents_service = MistralAgentsService()
    return _mistral_agents_service
