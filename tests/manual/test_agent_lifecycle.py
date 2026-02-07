#!/usr/bin/env python3
"""Agent Lifecycle Test - Comprehensive Logging

This script traces the complete agent lifecycle with detailed logging:
1. Agent creation and handoff configuration
2. Conversation start → Router handoff
3. Each subsequent handoff event
4. Tool calls and their results
5. Message responses

Run with: python -m tests.manual.test_agent_lifecycle
Requires: MISTRAL_API_KEY in .env
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from mistralai import (
    AgentHandoffDoneEvent,
    FunctionCallEvent,
    MessageOutputEvent,
    ResponseDoneEvent,
    ResponseErrorEvent,
    ToolExecutionStartedEvent,
)

from app.services.mistral_client import get_mistral_client

# Load environment
load_dotenv()

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def log_section(title: str) -> None:
    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{BOLD}{'=' * 80}{RESET}\n")


def log_event(event_type: str, detail: str, color: str = CYAN) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"{color}[{timestamp}] [{event_type}]{RESET} {detail}")


def log_handoff(from_agent: str, to_agent: str) -> None:
    print(f"{YELLOW}{'━' * 60}{RESET}")
    print(f"{YELLOW}🔄 HANDOFF: {from_agent} → {to_agent}{RESET}")
    print(f"{YELLOW}{'━' * 60}{RESET}")


def log_success(msg: str) -> None:
    print(f"{GREEN}✅ {msg}{RESET}")


def log_error(msg: str) -> None:
    print(f"{RED}❌ {msg}{RESET}")


def test_agent_creation() -> dict[str, str]:
    """Test creating all agents and verify handoff configuration."""
    log_section("STEP 1: AGENT CREATION & HANDOFF CONFIGURATION")

    from app.services.agents import (
        create_fact_completion_agent,
        create_intake_agent,
        create_reasoning_logic_agent,
        create_router_agent,
        create_summary_agent,
        create_wrapup_agent,
    )

    agents = {}

    # Create each agent with logging
    agent_creators = [
        ("router", create_router_agent),
        ("intake", create_intake_agent),
        ("fact_completion", create_fact_completion_agent),
        ("reasoning_logic", create_reasoning_logic_agent),
        ("wrapup", create_wrapup_agent),
        ("summary", create_summary_agent),
    ]

    for name, creator in agent_creators:
        log_event("CREATING", f"{name.upper()} agent...")
        try:
            agent_id = creator()
            agents[name] = agent_id
            log_success(f"{name}: {agent_id}")
        except Exception as e:
            log_error(f"{name}: {e}")
            raise

    # Configure handoffs
    log_section("HANDOFF CONFIGURATION")

    client = get_mistral_client()

    handoff_config = [
        ("router", [agents["intake"]]),
        ("intake", [agents["fact_completion"]]),
        ("fact_completion", [agents["reasoning_logic"]]),
        ("reasoning_logic", [agents["wrapup"], agents["fact_completion"]]),
        ("wrapup", [agents["summary"], agents["fact_completion"]]),
    ]

    for agent_name, handoff_targets in handoff_config:
        target_names = [k for k, v in agents.items() if v in handoff_targets]
        log_event("HANDOFF", f"{agent_name} → {target_names}")
        client.beta.agents.update(agent_id=agents[agent_name], handoffs=handoff_targets)
        log_success("Configured")

    return agents


def test_conversation_flow(agents: dict[str, str], test_messages: list[str]) -> None:
    """Test a conversation flow and log all events."""
    log_section("STEP 2: CONVERSATION FLOW")

    client = get_mistral_client()

    conversation_id = None
    current_agent = "router"
    message_count = 0

    for user_message in test_messages:
        message_count += 1
        log_section(f"MESSAGE {message_count}: {user_message[:50]}...")

        log_event("USER", user_message)

        # Start or append to conversation
        if conversation_id is None:
            log_event("API", f"start_stream() with router_id={agents['router']}")
            response = client.beta.conversations.start_stream(
                agent_id=agents["router"],
                inputs=user_message,
            )
        else:
            log_event("API", f"append_stream() with conv_id={conversation_id}")
            response = client.beta.conversations.append_stream(
                conversation_id=conversation_id,
                inputs=user_message,
            )

        # Process events
        full_response = ""
        function_call_data = {"name": "", "arguments": "", "tool_call_id": None}

        with response as event_stream:
            # Get conversation ID from first event
            first_event = next(iter(event_stream))
            if hasattr(first_event.data, "conversation_id"):
                new_conv_id = first_event.data.conversation_id
                if conversation_id != new_conv_id:
                    conversation_id = new_conv_id
                    log_event("CONV_ID", conversation_id, GREEN)

            # Process first event
            _process_event(first_event, current_agent, full_response, function_call_data)

            # Process remaining events
            for event in event_stream:
                result = _process_event(event, current_agent, full_response, function_call_data)
                if result == "handoff":
                    current_agent = getattr(event.data, "next_agent_name", current_agent)

        # Handle function call if any
        if function_call_data["tool_call_id"]:
            log_event(
                "TOOL_EXEC",
                f"Executing {function_call_data['name']} " f"with args: {function_call_data['arguments'][:100]}...",
            )
            # For now, just log - actual execution would require more setup

        log_event("CURRENT_AGENT", current_agent, YELLOW)

    log_section("CONVERSATION COMPLETE")
    log_success(f"Processed {message_count} messages")
    log_success(f"Final agent: {current_agent}")


def _process_event(event, current_agent: str, full_response: str, function_call_data: dict) -> str | None:
    """Process a single Mistral event and log it."""
    match event.data:
        case MessageOutputEvent():
            content = event.data.content
            if isinstance(content, list):
                content = "".join(str(c.text if hasattr(c, "text") else c) for c in content)
            if content:
                # Truncate for logging
                display = content[:80] + "..." if len(content) > 80 else content
                log_event("MSG", display.replace("\n", " "))
            return None

        case AgentHandoffDoneEvent():
            next_agent = event.data.next_agent_name
            log_handoff(current_agent, next_agent)
            return "handoff"

        case ToolExecutionStartedEvent():
            log_event("TOOL_START", f"{event.data.name}", CYAN)
            return None

        case FunctionCallEvent():
            function_call_data["tool_call_id"] = event.data.tool_call_id
            function_call_data["name"] = event.data.name
            function_call_data["arguments"] += event.data.arguments or ""
            return None

        case ResponseErrorEvent():
            log_error(f"Response error: {event.data.message}")
            return "error"

        case ResponseDoneEvent():
            log_event("DONE", "Stream complete", GREEN)
            return "done"

        case _:
            log_event("OTHER", f"{type(event.data).__name__}")
            return None


def main():
    """Main entry point."""
    log_section("AGENT LIFECYCLE TEST")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Mistral API Key: {'SET' if os.environ.get('MISTRAL_API_KEY') else 'MISSING'}")

    # Test messages simulating a rental heating issue
    test_messages = [
        "Hallo, meine Heizung ist seit 2 Wochen kaputt und mein Vermieter reagiert nicht.",
        "Ich wohne in Berlin-Kreuzberg, die Miete beträgt 850 Euro kalt.",
        "Ich habe am 5. Januar eine E-Mail geschickt und am 10. Januar nochmal angerufen.",
        "Ja, ich habe einen schriftlichen Mietvertrag. Ich möchte die Miete mindern.",
    ]

    try:
        # Step 1: Create agents
        agents = test_agent_creation()

        # Step 2: Test conversation flow
        test_conversation_flow(agents, test_messages)

        log_section("TEST COMPLETE")
        log_success("All steps completed successfully!")

    except Exception as e:
        log_error(f"Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
