"""Conversation Orchestration Logic

This module implements dynamic agent routing based on conversation state.
Instead of a linear pipeline (Router → Intake → Reasoning → Summary),
the orchestrator decides which agent to use based on:
- Facts completeness (5W framework)
- Reasoning completion status
- Summary generation status

This enables:
- Dynamic routing (skip agents if facts already complete)
- Resuming interrupted conversations
- Flexible conversation flow

Agent flow (domain-aware):
Router → Domain Agent (or fallback Intake) → Reasoning → WrapUp → Summary
"""

from app.models.conversation import Conversation

# Domain agent names used by the 3 Phase 1 domain agents
DOMAIN_AGENT_NAMES = {"mietrecht", "arbeitsrecht", "vertragsrecht"}


class ConversationOrchestrator:
    """Determines which agent should handle the current message based on conversation state"""

    async def determine_next_agent(self, conversation: Conversation) -> str:
        """Decide which agent to use based on conversation state

        Decision Logic:
        1. Summary already generated → Router (handle new questions)
        2. Reasoning done, no summary → Summary (generate final document)
        3. Facts complete, no reasoning → Reasoning (contradiction detection)
        4. Facts incomplete → Intake (collect more facts)

        Args:
            conversation: Conversation ORM model with state metadata

        Returns:
            Agent name: "router", "intake", "reasoning", or "summary"
        """
        # Check conversation state flags
        summary_done = conversation.summary_generated
        reasoning_done = conversation.reasoning_done
        facts_complete = self._check_facts_completeness(conversation)

        # Decision tree
        if summary_done:
            # Conversation complete - Router handles new questions
            return "router"

        elif reasoning_done and not summary_done:
            # Reasoning complete - Generate summary
            return "summary"

        elif facts_complete and not reasoning_done:
            # All facts collected - Reasoning for contradiction detection
            return "reasoning"

        else:
            # Need more facts - Continue intake
            return "intake"

    def _check_facts_completeness(self, conversation: Conversation) -> bool:
        """Check if all 5W facts have been collected

        5W Framework:
        - WHO: Parties involved (claimant, defendant, witnesses)
        - WHAT: Issue description, legal area, specific problem
        - WHEN: Timeline of events, dates, duration
        - WHERE: Location, jurisdiction (German federal state)
        - WHY: Motivation, desired outcome

        Args:
            conversation: Conversation ORM model

        Returns:
            True if all 5W facts collected, False otherwise
        """
        required_facts = ["who", "what", "when", "where", "why"]

        for fact_name in required_facts:
            # Get JSONB field value (e.g., conversation.who)
            fact_value = getattr(conversation, fact_name, None)

            # Check if fact exists and has "collected" flag set to True
            if not fact_value or not fact_value.get("collected"):
                return False

        return True

    async def update_conversation_state(
        self, conversation: Conversation, agent_name: str, facts: dict | None = None
    ) -> None:
        """Update conversation metadata after agent response

        This method updates conversation state based on which agent just completed:
        - Intake/Domain Agent: Updates 5W facts in JSONB fields
        - Reasoning Agent: Sets reasoning_done = True
        - Summary Agent: Sets summary_generated = True

        Args:
            conversation: Conversation ORM model to update
            agent_name: Name of agent that just responded
            facts: Optional facts dict from Intake/Domain Agent (5W framework data)

        Returns:
            None (modifies conversation in-place)

        Note:
            Caller must commit database session after this method
        """
        # Domain agents and generic Intake both extract 5W facts
        is_intake_type = agent_name == "intake" or agent_name in DOMAIN_AGENT_NAMES
        if is_intake_type and facts:
            for fact_name, fact_data in facts.items():
                if fact_name in ["who", "what", "when", "where", "why"]:
                    setattr(conversation, fact_name, {"collected": True, **fact_data})

        elif agent_name == "reasoning":
            conversation.reasoning_done = True

        elif agent_name == "summary":
            conversation.summary_generated = True


# Dependency injection function
def get_orchestrator() -> ConversationOrchestrator:
    """FastAPI dependency for ConversationOrchestrator

    Returns:
        ConversationOrchestrator instance

    Usage:
        @router.websocket("/ws/chat/{conversation_id}")
        async def websocket_chat(
            orchestrator: ConversationOrchestrator = Depends(get_orchestrator)
        ):
            agent_name = await orchestrator.determine_next_agent(conversation)
    """
    return ConversationOrchestrator()
