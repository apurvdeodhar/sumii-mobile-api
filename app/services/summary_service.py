"""Summary Service - Generate legal summaries using Summary Agent

This service handles calling the Mistral Summary Agent and extracting
the markdown content from the agent's function call response.
"""

import json
import logging

from sqlalchemy import select

from app.models import Conversation, Message, MessageRole
from app.models.document import Document, OCRStatus
from app.models.user import User
from app.schemas.summary_validation import build_user_profile_context_lines, validate_and_enrich_summary
from app.services.agents import MistralAgentsService
from app.services.mistral_client import get_mistral_client

logger = logging.getLogger(__name__)


class SummaryService:
    """Service for generating legal summaries"""

    def __init__(self, agents_service: MistralAgentsService):
        """Initialize summary service with optimized Mistral client

        Args:
            agents_service: Mistral agents service instance
        """
        self.agents_service = agents_service
        self.client = get_mistral_client()

    async def generate_summary(self, conversation: Conversation, db_session) -> tuple[str, dict, dict]:
        """Generate summary markdown using Summary Agent

        This method:
        1. Calls the Summary Agent with conversation context
        2. Extracts markdown from the agent's function call
        3. Returns markdown content, metadata, and structured data for PDF

        Args:
            conversation: Conversation model with messages
            db_session: Database session (for saving messages)

        Returns:
            Tuple of (markdown_content, metadata_dict, structured_case_data)
            - markdown_content: Full markdown summary text
            - metadata: Dict with legal_area, urgency (no case_strength - lawyers assess that)
            - structured_case_data: Dict with claimant, respondent, factual_narrative for PDF template

        Raises:
            Exception: If summary generation fails
        """
        try:
            # Get Summary Agent ID
            summary_agent_id = self.agents_service.get_agent_id("summary")
            if not summary_agent_id:
                raise Exception("Summary agent not initialized")

            # Validate conversation has messages
            messages_list = list(conversation.messages) if conversation.messages else []
            logger.info(f"Generating summary for conversation {conversation.id}, found {len(messages_list)} messages")

            if len(messages_list) == 0:
                raise ValueError(
                    "Conversation has no messages. Please chat with the legal assistant " "before generating a summary."
                )

            # Fetch user profile for context enrichment
            user_result = await db_session.execute(select(User).where(User.id == conversation.user_id))
            user = user_result.unique().scalar_one_or_none()

            # Fetch documents with completed OCR for context enrichment
            docs_result = await db_session.execute(
                select(Document)
                .where(
                    Document.conversation_id == conversation.id,
                    Document.ocr_status == OCRStatus.COMPLETED,
                )
                .order_by(Document.created_at)
            )
            documents = list(docs_result.scalars().all())

            # Build conversation context from messages + user profile + documents
            conversation_context = self._build_conversation_context(conversation, user=user, documents=documents)
            logger.debug(f"Built conversation context: {len(conversation_context)} chars")

            if not conversation_context or len(conversation_context) < 50:
                raise ValueError(f"Conversation context is too short ({len(conversation_context)} chars)")

            # Call Summary Agent using conversations.start() pattern from cookbook
            # This avoids the RunContext issues with empty inputs
            response = await self.client.beta.conversations.start_async(
                agent_id=summary_agent_id,
                inputs=conversation_context,
            )

            # Extract markdown, metadata, and structured data from function call
            markdown_content, metadata, structured_data = self._extract_summary_from_response(response)

            # Validate and enrich structured data with Pydantic + user profile auto-fill
            validated = validate_and_enrich_summary(
                {
                    "markdown_content": markdown_content,
                    "metadata": metadata,
                    **structured_data,
                },
                user=user,
            )
            markdown_content = validated.markdown_content
            metadata = validated.metadata.model_dump()
            structured_data = {
                "client_profile": validated.client_profile.model_dump(),
                "claimant": validated.claimant.model_dump(),
                "respondent": validated.respondent.model_dump(),
                "factual_narrative": validated.factual_narrative.model_dump(),
                "evidence": validated.evidence.model_dump(),
                "financial_info": validated.financial_info.model_dump(),
            }

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

            return markdown_content, metadata, structured_data

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}", exc_info=True)
            raise Exception(f"Summary generation failed: {str(e)}") from e

    def _build_conversation_context(
        self,
        conversation: Conversation,
        user: User | None = None,
        documents: list[Document] | None = None,
    ) -> str:
        """Build conversation context string from messages, user profile, and documents

        Args:
            conversation: Conversation model with messages
            user: User model with profile data (name, address, insurance)
            documents: List of documents with completed OCR

        Returns:
            str: Formatted conversation context with all available data
        """
        context_parts = [
            f"Konversation: {conversation.title or 'Rechtliche Beratung'}",
            f"Rechtsgebiet: {conversation.legal_area.value if conversation.legal_area else 'Nicht spezifiziert'}",
        ]

        # Add user profile (Mandantenprofil)
        if user:
            profile_lines = build_user_profile_context_lines(user)
            if profile_lines:
                context_parts.append("")
                context_parts.append("## Mandantenprofil (Client Profile)")
                context_parts.extend(profile_lines)

        # Add conversation messages
        context_parts.append("")
        context_parts.append("Konversationsverlauf:")
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

        # Add uploaded documents with OCR text
        if documents:
            context_parts.append("")
            context_parts.append("## Hochgeladene Dokumente (Uploaded Documents)")
            for idx, doc in enumerate(documents, 1):
                context_parts.append(f"### Anlage {idx} — {doc.filename}")
                if doc.file_type:
                    context_parts.append(f"Dateityp: {doc.file_type}")
                if doc.created_at:
                    context_parts.append(f"Hochgeladen: {doc.created_at.strftime('%d.%m.%Y')}")
                if doc.ocr_text:
                    context_parts.append(f"OCR-extrahierter Text:\n{doc.ocr_text}")
                context_parts.append("---")

        context_parts.append("")
        context_parts.append(
            "Bitte generiere eine vollständige rechtliche Zusammenfassung im Markdown-Format "
            "basierend auf dem obigen Konversationsverlauf, dem Mandantenprofil, den gesammelten Fakten "
            "und den hochgeladenen Dokumenten. "
            "Verwende die Funktion generate_summary mit dem vollständigen Markdown-Text und den Metadaten. "
            "WICHTIG: Trage alle verfügbaren Mandantendaten (Name, Adresse, Versicherung) in die Zusammenfassung ein."
        )

        return "\n".join(context_parts)

    def _extract_summary_from_response(self, response) -> tuple[str, dict, dict]:
        """Extract markdown, metadata, and structured data from Mistral agent response

        Handles both:
        - conversations.start_async response (outputs array)
        - run_async response (output_entries)

        Args:
            response: Mistral response object

        Returns:
            Tuple of (markdown_content, metadata_dict, structured_case_data)
            - structured_case_data: dict with claimant, respondent, factual_narrative, evidence for PDF template

        Raises:
            Exception: If markdown not found in response
        """
        markdown_content = None
        metadata = {}
        structured_data = {}  # New: structured data for PDF template

        logger.debug(f"Response type: {type(response)}")
        logger.debug(f"Response attributes: {dir(response)}")

        # Method 1: Check 'outputs' array (conversations.start_async format)
        if hasattr(response, "outputs") and response.outputs:
            logger.debug(f"Found outputs array with {len(response.outputs)} entries")
            for output in response.outputs:
                logger.debug(f"Output type: {type(output)}, attributes: {dir(output)}")

                # Check for function call output
                if hasattr(output, "type"):
                    if output.type == "function.call" or str(output.type) == "function.call":
                        if hasattr(output, "name") and output.name == "generate_summary":
                            if hasattr(output, "arguments"):
                                args = output.arguments
                                if isinstance(args, str):
                                    args = json.loads(args)
                                markdown_content = args.get("markdown_content", "")
                                metadata = args.get("metadata", {})
                                # Extract structured data for PDF template
                                structured_data = {
                                    "client_profile": args.get("client_profile", {}),
                                    "claimant": args.get("claimant", {}),
                                    "respondent": args.get("respondent", {}),
                                    "factual_narrative": args.get("factual_narrative", {}),
                                    "evidence": args.get("evidence", {}),
                                    "financial_info": args.get("financial_info", {}),
                                }
                                logger.info(f"Extracted summary from function call: {len(markdown_content)} chars")

                # Check for message output with content
                if not markdown_content and hasattr(output, "content"):
                    content = output.content
                    if content and len(content) > 50:
                        markdown_content = content
                        logger.info(f"Extracted summary from message content: {len(markdown_content)} chars")

        # Method 2: Check 'output_entries' (run_async format - fallback)
        if not markdown_content and hasattr(response, "output_entries"):
            for entry in response.output_entries:
                if hasattr(entry, "type") and entry.type == "function.call":
                    if hasattr(entry, "name") and entry.name == "generate_summary":
                        if hasattr(entry, "arguments"):
                            args = entry.arguments
                            if isinstance(args, str):
                                args = json.loads(args)
                            markdown_content = args.get("markdown_content", "")
                            metadata = args.get("metadata", {})
                            structured_data = {
                                "client_profile": args.get("client_profile", {}),
                                "claimant": args.get("claimant", {}),
                                "respondent": args.get("respondent", {}),
                                "factual_narrative": args.get("factual_narrative", {}),
                                "evidence": args.get("evidence", {}),
                                "financial_info": args.get("financial_info", {}),
                            }

        # Method 3: Try output_as_text property
        if not markdown_content and hasattr(response, "output_as_text"):
            text = response.output_as_text
            if text and len(text) > 50:
                markdown_content = text
                logger.info(f"Extracted summary from output_as_text: {len(markdown_content)} chars")

        # Method 4: Try to parse response directly
        if not markdown_content:
            response_text = str(response)
            logger.debug(f"Response as string (first 500 chars): {response_text[:500]}")

            # Try to find markdown in code block
            if "```markdown" in response_text:
                start = response_text.find("```markdown") + 11
                end = response_text.find("```", start)
                if end > start:
                    markdown_content = response_text[start:end].strip()

            # Try to find content in the response
            elif "markdown_content" in response_text:
                # Try to extract JSON
                try:
                    import re

                    match = re.search(r'"markdown_content"\s*:\s*"([^"]+)"', response_text)
                    if match:
                        markdown_content = match.group(1)
                except Exception:
                    pass

        if not markdown_content:
            logger.error(f"Could not extract markdown. Full response: {response}")
            raise Exception("Could not extract markdown content from agent response")

        # Ensure metadata has required fields (no case_strength - lawyers assess that)
        if not metadata:
            metadata = {
                "legal_area": "Mietrecht",  # Default
                "urgency": "weeks",  # Default
            }

        # Remove case_strength if present (deprecated)
        metadata.pop("case_strength", None)

        return markdown_content, metadata, structured_data


# Dependency injection function
def get_summary_service(agents_service: MistralAgentsService) -> SummaryService:
    """FastAPI dependency for SummaryService

    Args:
        agents_service: Mistral agents service

    Returns:
        SummaryService instance
    """
    return SummaryService(agents_service)
