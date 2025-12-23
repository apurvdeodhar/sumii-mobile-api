"""Mistral AI Agents for Legal Intake Workflow

This package provides specialized AI agents for Sumii's legal intake process:
- Router Agent: Orchestrates workflow
- Intake Agent: Collects facts (5W framework)
- Fact Completion Agent: Gathers additional details
- Summary Agent: Generates professional documents for lawyers

Architecture: Mistral Agents API (cloud-hosted)
Benefits: Fast implementation, built-in orchestration, production-ready

IMPORTANT: Sumii does NOT provide legal analysis or advice.
Legal analysis is done by lawyers. Sumii only collects facts.

Agent Flow:
User → Router → Intake → Fact Completion → Summary → PDF Download
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
        """Create all 4 agents and configure handoffs via Mistral API

        The agent workflow is:
        Router → Intake → Reasoning → Summary

        Handoffs are configured via client.beta.agents.update() to enable
        proper agent orchestration with Mistral's Conversations API.

        Returns:
            dict[str, str]: Mapping of agent names to agent IDs
        """
        from mistralai import Mistral

        from app.config import settings

        # Create Mistral client
        client = Mistral(api_key=settings.MISTRAL_API_KEY)

        # Create all agents
        intake_id = create_intake_agent()
        reasoning_id = create_reasoning_agent()
        summary_id = create_summary_agent()
        router_id = create_router_agent()

        # Configure handoffs via Mistral API
        # Router can hand off to Intake
        client.beta.agents.update(agent_id=router_id, handoffs=[intake_id])

        # Intake can hand off to Reasoning
        client.beta.agents.update(agent_id=intake_id, handoffs=[reasoning_id])

        # Reasoning can hand off to Summary
        client.beta.agents.update(agent_id=reasoning_id, handoffs=[summary_id])

        # Summary is final - no handoffs needed

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
