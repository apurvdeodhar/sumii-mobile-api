"""Mistral AI Agents for Legal Intake Workflow

This package provides specialized AI agents for Sumii's legal intake process:
- Router Agent: Orchestrates workflow
- Intake Agent: Collects facts (5W framework)
- Fact Completion Agent: Gathers additional details
- Reasoning Logic Agent: Contradiction detection
- Wrap-Up Agent: Confirms facts before summary generation
- Summary Agent: Generates professional documents for lawyers

Architecture: Mistral Agents API (cloud-hosted)
Benefits: Fast implementation, built-in orchestration, production-ready

IMPORTANT: Sumii does NOT provide legal analysis or advice.
Legal analysis is done by lawyers. Sumii only collects facts.

Agent Flow:
User → Router → Intake → Fact Completion → Reasoning Logic → Wrap-Up → Summary
                                                 ↓
                               (contradiction) → Fact Completion
"""

import hashlib
import logging

from mistralai import Mistral

from app.services.agents.fact_completion import create_fact_completion_agent
from app.services.agents.intake import create_intake_agent
from app.services.agents.reasoning_logic import create_reasoning_logic_agent
from app.services.agents.router import create_router_agent
from app.services.agents.summary import create_summary_agent
from app.services.agents.wrapup import create_wrapup_agent


def _compute_handoff_hash(handoff_ids: list[str]) -> str:
    """Compute hash of handoff IDs to detect changes."""
    content = "|".join(sorted(handoff_ids))
    return hashlib.md5(content.encode()).hexdigest()[:16]


def _update_handoffs_if_changed(
    client: Mistral,
    agent_id: str,
    handoff_ids: list[str],
    logger: logging.Logger,
) -> bool:
    """
    Update agent handoffs ONLY if they have changed.

    Uses agent metadata to store a hash of the handoff configuration.
    This prevents unnecessary updates that increment agent versions.

    Returns:
        bool: True if update was performed, False if skipped
    """
    # Get current agent to check metadata
    try:
        agent = client.beta.agents.get(agent_id=agent_id)
    except Exception as e:
        logger.warning(f"Failed to get agent {agent_id}: {e}")
        # Fall back to updating
        client.beta.agents.update(agent_id=agent_id, handoffs=handoff_ids)
        return True

    # Compute new handoff hash
    new_hash = _compute_handoff_hash(handoff_ids)

    # Check existing metadata for handoff hash
    existing_metadata = getattr(agent, "metadata", {}) or {}
    existing_handoff_hash = existing_metadata.get("handoff_hash", "")

    if existing_handoff_hash == new_hash:
        # No changes, skip update to preserve version
        logger.debug(f"Agent {agent_id} handoffs unchanged (hash={new_hash[:8]}...), skipping update")
        return False

    # Update needed - include handoff hash in metadata
    new_metadata = {**existing_metadata, "handoff_hash": new_hash}
    logger.debug(f"Agent {agent_id} handoffs changed, updating (hash={new_hash[:8]}...)")
    client.beta.agents.update(
        agent_id=agent_id,
        handoffs=handoff_ids,
        metadata=new_metadata,
    )
    return True


def _ensure_version_bumped(
    client: Mistral,
    agent_id: str,
    logger: logging.Logger,
) -> bool:
    """Ensure an agent without handoffs has its version bumped to match others.

    The Conversations API requires all agents in a handoff chain to be at the
    same version. Agents with handoffs get bumped automatically via update(),
    but final agents (no outgoing handoffs) stay at v0. This uses a no-op
    description update to bump the version.

    The agent's metadata tracks whether it was already bumped to avoid
    unnecessary version increments on subsequent startups.

    Returns:
        bool: True if version was bumped, False if already bumped
    """
    try:
        agent = client.beta.agents.get(agent_id=agent_id)
    except Exception as e:
        logger.warning(f"Failed to get agent {agent_id}: {e}")
        return False

    existing_metadata = getattr(agent, "metadata", {}) or {}
    if existing_metadata.get("version_bumped"):
        return False

    # No-op description update to bump version, and mark as bumped in metadata
    client.beta.agents.update(
        agent_id=agent_id,
        description=agent.description or "",
    )
    logger.debug(f"Agent {agent_id} version bumped to match handoff chain")
    return True


__all__ = [
    "create_router_agent",
    "create_intake_agent",
    "create_fact_completion_agent",
    "create_reasoning_logic_agent",
    "create_wrapup_agent",
    "create_summary_agent",
    "MistralAgentsService",
]


class MistralAgentsService:
    """Service for managing all Mistral AI Agents

    This service provides a convenient interface to create and manage
    all 6 specialized agents for the legal intake workflow.
    """

    def __init__(self):
        """Initialize service with empty agent registry"""
        self.agents: dict[str, str] = {}
        self._logger = logging.getLogger(__name__)

    async def initialize_all_agents(self) -> dict[str, str]:
        """Create all 6 agents and configure handoffs via Mistral API

        The agent workflow is:
        Router → Intake → Fact Completion → Reasoning Logic → Wrap-Up → Summary
                                                    ↓
                                  (contradiction) → Fact Completion

        Handoffs are configured via client.beta.agents.update() to enable
        proper agent orchestration with Mistral's Conversations API.

        Returns:
            dict[str, str]: Mapping of agent names to agent IDs
        """
        self._logger.info("🚀 [AGENTS] Initializing all 6 Mistral agents...")

        # Create Mistral client with optimized timeout settings
        from app.services.mistral_client import get_mistral_client

        client = get_mistral_client()

        # Create all agents with progress logging
        self._logger.debug("[AGENTS] Creating Intake Agent...")
        intake_id = create_intake_agent()

        self._logger.debug("[AGENTS] Creating Fact Completion Agent...")
        fact_completion_id = create_fact_completion_agent()

        self._logger.debug("[AGENTS] Creating Reasoning Logic Agent (Magistral model)...")
        reasoning_logic_id = create_reasoning_logic_agent()

        self._logger.debug("[AGENTS] Creating Wrap-Up Agent...")
        wrapup_id = create_wrapup_agent()

        self._logger.debug("[AGENTS] Creating Summary Agent...")
        summary_id = create_summary_agent()

        self._logger.debug("[AGENTS] Creating Router Agent...")
        router_id = create_router_agent()

        # Configure handoffs via Mistral API (only if changed)
        self._logger.debug("[AGENTS] Configuring handoff chain (if changed)...")

        # Router can hand off to Intake
        if _update_handoffs_if_changed(client, router_id, [intake_id], self._logger):
            self._logger.debug("  Router → Intake ✓ (updated)")
        else:
            self._logger.debug("  Router → Intake ✓ (unchanged)")

        # Intake can hand off to Fact Completion
        if _update_handoffs_if_changed(client, intake_id, [fact_completion_id], self._logger):
            self._logger.debug("  Intake → Fact Completion ✓ (updated)")
        else:
            self._logger.debug("  Intake → Fact Completion ✓ (unchanged)")

        # Fact Completion can hand off to Reasoning Logic
        if _update_handoffs_if_changed(client, fact_completion_id, [reasoning_logic_id], self._logger):
            self._logger.debug("  Fact Completion → Reasoning Logic ✓ (updated)")
        else:
            self._logger.debug("  Fact Completion → Reasoning Logic ✓ (unchanged)")

        # Reasoning Logic can hand off to Wrap-Up (if no issues) or back to Fact Completion (if contradiction)
        if _update_handoffs_if_changed(client, reasoning_logic_id, [wrapup_id, fact_completion_id], self._logger):
            self._logger.debug("  Reasoning Logic → [Wrap-Up, Fact Completion] ✓ (updated)")
        else:
            self._logger.debug("  Reasoning Logic → [Wrap-Up, Fact Completion] ✓ (unchanged)")

        # Wrap-Up can hand off to Summary (on confirmation) or back to Fact Completion (on correction)
        if _update_handoffs_if_changed(client, wrapup_id, [summary_id, fact_completion_id], self._logger):
            self._logger.debug("  Wrap-Up → [Summary, Fact Completion] ✓ (updated)")
        else:
            self._logger.debug("  Wrap-Up → [Summary, Fact Completion] ✓ (unchanged)")

        # Summary is final — no outgoing handoffs, but needs version bump to match others.
        # Without this, Summary stays at v0 while others are v1 → 404 on append_stream().
        if _ensure_version_bumped(client, summary_id, self._logger):
            self._logger.debug("  Summary (final, version bumped) ✓")
        else:
            self._logger.debug("  Summary (final) ✓ (already bumped)")

        # Store all agent IDs
        self.agents = {
            "router": router_id,
            "intake": intake_id,
            "fact_completion": fact_completion_id,
            "reasoning_logic": reasoning_logic_id,
            "wrapup": wrapup_id,
            "summary": summary_id,
        }

        self._logger.info("✅ [AGENTS] All 6 agents initialized successfully!")
        self._logger.debug(f"[AGENTS] Agent IDs: {self.agents}")

        # Verify agent models by querying Mistral API
        for name, agent_id in self.agents.items():
            try:
                agent = client.beta.agents.get(agent_id=agent_id)
                self._logger.info(f"  [VERIFY] {name}: model={agent.model}, id={agent_id}")
            except Exception as e:
                self._logger.warning(f"  [VERIFY] {name}: failed to verify - {e}")

        return self.agents

    def get_agent_id(self, agent_name: str) -> str | None:
        """Get agent ID by name

        Args:
            agent_name: Name of agent ("router", "intake", "fact_completion",
                        "reasoning_logic", "wrapup", "summary")

        Returns:
            str | None: Agent ID if exists, None otherwise
        """
        return self.agents.get(agent_name)

    @property
    def is_initialized(self) -> bool:
        """Check if all agents are initialized"""
        return len(self.agents) == 6  # Now 6 agents

    def status(self) -> dict:
        """Get agent initialization status for health checks

        Returns:
            dict: Status information including initialized flag and agent count
        """
        return {
            "initialized": self.is_initialized,
            "agent_count": len(self.agents),
            "agents": list(self.agents.keys()) if self.agents else [],
        }


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
