"""Mistral AI Agents for Legal Intake Workflow

This package provides specialized AI agents for Sumii's legal intake process:
- Router Agent: Classifies domain + intent, routes to correct agent
- Domain Agents: Mietrecht, Vertragsrecht, Arbeitsrecht (Phase 1)
- Intake Agent: Generic fallback for low-confidence classification
- Fact Completion Agent: Generic fallback detailed fact-gathering
- Reasoning Logic Agent: Contradiction detection
- Wrap-Up Agent: Confirms facts before summary generation
- Summary Agent: Generates professional documents for lawyers

Architecture: Mistral Agents API (cloud-hosted)
Benefits: Fast implementation, built-in orchestration, production-ready

IMPORTANT: Sumii does NOT provide legal analysis or advice.
Legal analysis is done by lawyers. Sumii only collects facts.

Agent Flow (domain-aware):
User → Router ──classify──→ Domain Agent ──→ Reasoning Logic → Wrap-Up → Summary
                  │                                    ↓
                  │ (low confidence)      (contradiction) → Domain Agent / Fact Completion
                  └──→ Intake → Fact Completion ──→ Reasoning Logic → ...
"""

import logging
import re

from mistralai import Mistral

from app.services.agents.domains.domain_factory import create_all_domain_agents
from app.services.agents.fact_completion import create_fact_completion_agent
from app.services.agents.intake import create_intake_agent
from app.services.agents.reasoning_logic import create_reasoning_logic_agent
from app.services.agents.router import create_router_agent
from app.services.agents.summary import create_summary_agent
from app.services.agents.wrapup import create_wrapup_agent

# Regex for the invisible sync marker appended to instructions during version sync.
# This marker forces a version bump on lagging agents without changing behavior.
_SYNC_MARKER_RE = re.compile(r"\n<!-- v-sync:\d+ -->")

# Phase 1 domain agents — keys match YAML config filenames
PHASE_1_DOMAINS = ["vertragsrecht", "mietrecht", "arbeitsrecht"]


def _configure_handoffs(
    client: Mistral,
    agent_id: str,
    handoff_ids: list[str],
    logger: logging.Logger,
) -> None:
    """Configure agent handoffs, skipping the update if already correct.

    Handoff updates via ``update(handoffs=...)`` DO increment agent versions
    on Mistral's side (confirmed empirically with SDK v1.12).  Unconditional
    updates on every restart cause version drift (+1 per restart on all agents
    except Summary, which has no outgoing handoffs).

    To avoid this, we fetch the agent's current handoffs and compare with the
    desired list.  The ``handoffs`` field is a ``list[str]`` of agent IDs.
    """
    try:
        agent = client.beta.agents.get(agent_id=agent_id)
        existing = sorted(agent.handoffs or [])
        desired = sorted(handoff_ids)
        if existing == desired:
            return
        client.beta.agents.update(agent_id=agent_id, handoffs=handoff_ids)
    except Exception as e:
        logger.warning(f"Failed to configure handoffs for {agent_id}: {e}")


def _sync_agent_versions(
    client: Mistral,
    agents: dict[str, str],
    logger: logging.Logger,
) -> bool:
    """Check version consistency across agents and force-sync if needed.

    The Mistral Conversations API requires all agents in a handoff chain to be
    at the same version.  When only some agent prompts change on deploy, those
    agents get version-bumped while others stay at their old version, causing
    error 3000 ("Response failed during handoff orchestration").

    This function detects version drift and fixes it by appending an invisible
    HTML comment (``<!-- v-sync:N -->``) to the instructions of lagging agents.
    This forces a version bump WITHOUT changing agent IDs, preserving all
    active conversations and server-side history.

    The sync marker does NOT affect the hash-based change detection in
    ``AgentFactory.create_agent()`` because the hash is stored in the agent's
    description prefix and computed from the code-provided instructions (which
    never include the marker).

    Returns:
        True if all versions are consistent (either already or after sync).
    """
    # 1. Collect current versions
    agent_data: dict[str, dict] = {}
    for name, agent_id in agents.items():
        try:
            agent = client.beta.agents.get(agent_id=agent_id)
            agent_data[name] = {
                "id": agent_id,
                "version": getattr(agent, "version", 0),
                "instructions": agent.instructions or "",
                "model": getattr(agent, "model", "?"),
            }
        except Exception as e:
            logger.warning(f"  [VERIFY] {name}: failed to query - {e}")
            return False

    versions = {n: d["version"] for n, d in agent_data.items()}
    unique = set(versions.values())

    # Log each agent's state
    for name, data in agent_data.items():
        logger.info(f"  [VERIFY] {name}: model={data['model']}, version=v{data['version']}, id={data['id']}")

    if len(unique) <= 1:
        v = unique.pop() if unique else "?"
        logger.info(f"[AGENTS] All agents at v{v}, versions consistent")
        return True

    # 2. Drift detected -- sync lagging agents
    max_version = max(versions.values())
    logger.warning(f"[AGENTS] Version drift detected: {versions}. Syncing to v{max_version}...")

    for name, data in agent_data.items():
        gap = max_version - data["version"]
        if gap <= 0:
            continue
        # Each update() increments version by 1, so we need `gap` updates
        clean_instructions = _SYNC_MARKER_RE.sub("", data["instructions"])
        try:
            for bump in range(gap):
                marker = f"\n<!-- v-sync:{data['version'] + bump + 1} -->"
                client.beta.agents.update(
                    agent_id=data["id"],
                    instructions=clean_instructions + marker,
                )
            logger.info(f"  [SYNC] {name}: v{data['version']} -> v{max_version} ({gap} bumps)")
        except Exception as e:
            logger.error(f"  [SYNC] Failed to sync {name}: {e}")
            return False

    # 3. Re-verify
    final_versions = {}
    for name, agent_id in agents.items():
        try:
            agent = client.beta.agents.get(agent_id=agent_id)
            final_versions[name] = getattr(agent, "version", 0)
        except Exception as e:
            logger.warning(f"  [VERIFY] {name}: failed to re-verify - {e}")
            return False

    final_unique = set(final_versions.values())
    if len(final_unique) <= 1:
        v = final_unique.pop()
        logger.info(f"[AGENTS] Version sync complete. All agents at v{v}")
        return True

    logger.error(f"[AGENTS] Version drift persists after sync: {final_versions}")
    return False


def _create_and_configure_agents(
    client: Mistral,
    logger: logging.Logger,
) -> dict[str, str]:
    """Create all agents and configure the handoff chain.

    This is the inner workhorse called by ``initialize_all_agents()``.
    It handles agent creation (via upsert) and handoff wiring but does NOT
    verify version consistency -- that is done separately by
    ``_sync_agent_versions()``.

    Returns:
        Mapping of agent role name to Mistral agent ID.
    """
    # --- Core agents (unchanged) ---
    logger.debug("[AGENTS] Creating Intake Agent...")
    intake_id = create_intake_agent()

    logger.debug("[AGENTS] Creating Fact Completion Agent...")
    fact_completion_id = create_fact_completion_agent()

    logger.debug("[AGENTS] Creating Reasoning Logic Agent...")
    reasoning_logic_id = create_reasoning_logic_agent()

    logger.debug("[AGENTS] Creating Wrap-Up Agent...")
    wrapup_id = create_wrapup_agent()

    logger.debug("[AGENTS] Creating Summary Agent...")
    summary_id = create_summary_agent()

    # --- Domain agents (Phase 1) ---
    logger.debug("[AGENTS] Creating domain agents (Phase 1)...")
    domain_agents = create_all_domain_agents(PHASE_1_DOMAINS)

    logger.debug("[AGENTS] Creating Router Agent...")
    router_id = create_router_agent()

    # --- Configure handoff chain ---
    logger.debug("[AGENTS] Configuring handoff chain...")

    # Router → domain agents + generic intake (fallback)
    router_handoff_targets = list(domain_agents.values()) + [intake_id]
    _configure_handoffs(client, router_id, router_handoff_targets, logger)
    domain_names = list(domain_agents.keys())
    logger.debug(f"  Router -> [{', '.join(domain_names)}, Intake]")

    # Each domain agent → Reasoning Logic (fan-in)
    for domain_key, domain_id in domain_agents.items():
        _configure_handoffs(client, domain_id, [reasoning_logic_id], logger)
        logger.debug(f"  {domain_key} -> Reasoning Logic")

    # Generic fallback path (kept for low-confidence classification)
    _configure_handoffs(client, intake_id, [fact_completion_id], logger)
    logger.debug("  Intake -> Fact Completion")

    _configure_handoffs(client, fact_completion_id, [reasoning_logic_id], logger)
    logger.debug("  Fact Completion -> Reasoning Logic")

    # Downstream (shared across all paths)
    _configure_handoffs(client, reasoning_logic_id, [wrapup_id, fact_completion_id], logger)
    logger.debug("  Reasoning Logic -> [Wrap-Up, Fact Completion]")

    _configure_handoffs(client, wrapup_id, [summary_id, fact_completion_id], logger)
    logger.debug("  Wrap-Up -> [Summary, Fact Completion]")

    # Summary is final -- no outgoing handoffs, no configuration needed.
    logger.debug("  Summary (final, no outgoing handoffs)")

    # Build agent registry
    agents = {
        "router": router_id,
        "intake": intake_id,
        "fact_completion": fact_completion_id,
        "reasoning_logic": reasoning_logic_id,
        "wrapup": wrapup_id,
        "summary": summary_id,
    }
    # Add domain agents with their domain key as the registry name
    for domain_key, domain_id in domain_agents.items():
        agents[domain_key] = domain_id

    return agents


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
    all agents for the legal intake workflow (core + domain agents).
    """

    def __init__(self):
        """Initialize service with empty agent registry"""
        self.agents: dict[str, str] = {}
        self._logger = logging.getLogger(__name__)

    async def initialize_all_agents(self) -> dict[str, str]:
        """Create all agents, configure handoffs, and ensure version consistency.

        The agent workflow is:
        Router → Domain Agent → Reasoning Logic → Wrap-Up → Summary
                   │ (fallback)                        ↓
                   └→ Intake → Fact Completion → (contradiction) → Fact Completion

        After creation and handoff wiring, agent versions are verified.  If any
        agents are at different versions (caused by partial prompt updates on
        deploy), lagging agents are force-bumped via an invisible instruction
        marker to restore consistency.  This prevents error 3000 during handoffs
        while preserving all active conversations (agent IDs stay the same).

        Returns:
            dict[str, str]: Mapping of agent names to agent IDs
        """
        total = 6 + len(PHASE_1_DOMAINS)  # core + domain agents
        self._logger.info(f"[AGENTS] Initializing {total} Mistral agents...")

        from app.services.mistral_client import get_mistral_client

        client = get_mistral_client()

        # Step 1: Create agents and configure handoffs
        self.agents = _create_and_configure_agents(client, self._logger)

        self._logger.info(f"[AGENTS] All {len(self.agents)} agents initialized successfully!")

        # Step 2: Verify version consistency and auto-sync if needed
        _sync_agent_versions(client, self.agents, self._logger)

        return self.agents

    def get_agent_id(self, agent_name: str) -> str | None:
        """Get agent ID by name

        Args:
            agent_name: Name of agent ("router", "intake", "fact_completion",
                        "reasoning_logic", "wrapup", "summary",
                        "vertragsrecht", "mietrecht", "arbeitsrecht")

        Returns:
            str | None: Agent ID if exists, None otherwise
        """
        return self.agents.get(agent_name)

    @property
    def is_initialized(self) -> bool:
        """Check if all agents are initialized (core + domain)"""
        expected = 6 + len(PHASE_1_DOMAINS)
        return len(self.agents) >= expected

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
