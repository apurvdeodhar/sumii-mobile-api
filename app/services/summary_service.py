"""Summary Service - Generate legal summaries using Summary Agent

This service handles calling the Mistral Summary Agent and extracting
the markdown content from the agent's function call response.
"""

import json
import logging

from mistralai import Mistral
from mistralai.extra.run.context import RunContext

from app.config import settings
from app.models import Conversation, Message, MessageRole
from app.services.agents import MistralAgentsService

logger = logging.getLogger(__name__)


class SummaryService:
    """Service for generating legal summaries"""

    def __init__(self, agents_service: MistralAgentsService):
        """Initialize summary service

        Args:
            agents_service: Mistral agents service instance
        """
        self.agents_service = agents_service
        self.client = Mistral(api_key=settings.MISTRAL_API_KEY)

    async def generate_summary(self, conversation: Conversation, db_session) -> tuple[str, dict]:
        """Generate summary markdown using Summary Agent

        This method:
        1. Calls the Summary Agent with conversation context
        2. Extracts markdown from the agent's function call
        3. Returns markdown content and metadata

        Args:
            conversation: Conversation model with messages
            db_session: Database session (for saving messages)

        Returns:
            Tuple of (markdown_content, metadata_dict)
            - markdown_content: Full markdown summary text
            - metadata: Dict with legal_area, case_strength, urgency

        Raises:
            Exception: If summary generation fails
        """
        try:
            # Get Summary Agent ID
            summary_agent_id = self.agents_service.get_agent_id("summary")
            if not summary_agent_id:
                raise Exception("Summary agent not initialized")

            # Build conversation context from messages
            conversation_context = self._build_conversation_context(conversation)

            # Call Summary Agent with RunContext
            async with RunContext(agent_id=summary_agent_id) as run_ctx:
                # Use run (non-streaming) to get complete response
                response = await self.client.beta.conversations.run_async(
                    run_ctx=run_ctx,
                    inputs=conversation_context,
                )

                # Extract markdown from function call
                markdown_content, metadata = self._extract_summary_from_response(response)

                # Save agent message to database
                if markdown_content:
                    agent_message = Message(
                        conversation_id=conversation.id,
                        role=MessageRole.ASSISTANT,
                        content=f"Zusammenfassung generiert: {len(markdown_content)} Zeichen",
                        agent_name="summary",
                    )
                    db_session.add(agent_message)
                    await db_session.commit()

                return markdown_content, metadata

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}", exc_info=True)
            raise Exception(f"Summary generation failed: {str(e)}") from e

    def _build_conversation_context(self, conversation: Conversation) -> str:
        """Build conversation context string from messages

        Args:
            conversation: Conversation model with messages

        Returns:
            str: Formatted conversation context
        """
        context_parts = [
            f"Konversation: {conversation.title or 'Rechtliche Beratung'}",
            f"Rechtsgebiet: {conversation.legal_area.value if conversation.legal_area else 'Nicht spezifiziert'}",
            "",
            "Konversationsverlauf:",
        ]

        # Add all messages
        for message in conversation.messages:
            role_label = "Benutzer" if message.role == MessageRole.USER else "Assistent"
            context_parts.append(f"{role_label}: {message.content}")

        # Add 5W facts if available
        if conversation.who or conversation.what or conversation.when or conversation.where or conversation.why:
            context_parts.append("")
            context_parts.append("Gesammelte Fakten (5W):")
            if conversation.who:
                context_parts.append(f"Wer: {json.dumps(conversation.who, ensure_ascii=False)}")
            if conversation.what:
                context_parts.append(f"Was: {json.dumps(conversation.what, ensure_ascii=False)}")
            if conversation.when:
                context_parts.append(f"Wann: {json.dumps(conversation.when, ensure_ascii=False)}")
            if conversation.where:
                context_parts.append(f"Wo: {json.dumps(conversation.where, ensure_ascii=False)}")
            if conversation.why:
                context_parts.append(f"Warum: {json.dumps(conversation.why, ensure_ascii=False)}")

        context_parts.append("")
        context_parts.append(
            "Bitte generiere eine vollständige rechtliche Zusammenfassung im Markdown-Format "
            "basierend auf dem obigen Konversationsverlauf und den gesammelten Fakten. "
            "Verwende die Funktion generate_summary mit dem vollständigen Markdown-Text und den Metadaten."
        )

        return "\n".join(context_parts)

    def _extract_summary_from_response(self, response) -> tuple[str, dict]:
        """Extract markdown and metadata from Mistral agent response

        Args:
            response: Mistral RunResult object from run_async

        Returns:
            Tuple of (markdown_content, metadata_dict)

        Raises:
            Exception: If markdown not found in response
        """
        markdown_content = None
        metadata = {}

        # Check output_entries for function calls
        if hasattr(response, "output_entries"):
            for entry in response.output_entries:
                # Check if this is a function call entry
                if hasattr(entry, "type") and entry.type == "function.call":
                    if hasattr(entry, "name") and entry.name == "generate_summary":
                        # Parse function arguments
                        if hasattr(entry, "arguments"):
                            args = entry.arguments
                            if isinstance(args, str):
                                args = json.loads(args)
                            markdown_content = args.get("markdown_content", "")
                            metadata = args.get("metadata", {})

        # If no function call found, try to get text output
        if not markdown_content and hasattr(response, "output_as_text"):
            markdown_content = response.output_as_text

        # If still no markdown, try to extract from response text
        if not markdown_content:
            response_text = str(response)
            # Try to find markdown in response
            if "```markdown" in response_text:
                # Extract markdown from code block
                start = response_text.find("```markdown") + 11
                end = response_text.find("```", start)
                if end > start:
                    markdown_content = response_text[start:end].strip()
            elif response_text:
                # Use full response as markdown
                markdown_content = response_text

        if not markdown_content:
            raise Exception("Could not extract markdown content from agent response")

        # Ensure metadata has required fields
        if not metadata:
            metadata = {
                "legal_area": "Mietrecht",  # Default, should come from conversation
                "case_strength": "medium",  # Default
                "urgency": "weeks",  # Default
            }

        return markdown_content, metadata


# Dependency injection function
def get_summary_service(agents_service: MistralAgentsService) -> SummaryService:
    """FastAPI dependency for SummaryService

    Args:
        agents_service: Mistral agents service

    Returns:
        SummaryService instance
    """
    return SummaryService(agents_service)
