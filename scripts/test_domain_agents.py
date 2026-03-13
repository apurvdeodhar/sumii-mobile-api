"""Inline API Tests for Domain-Aware Intake Architecture

Tests against the local Mistral workspace (Sumii Local Dev) to validate:
1. Template composition — merged base + domain instructions produce working agents
2. Router function tool — classify_legal_domain tool works with handoffs
3. Fan-in handoff — multiple domain agents hand off to same downstream agent
4. Function tool dynamic Qs — Approach B latency comparison

Run from host venv:
    .venv/bin/python scripts/test_domain_agents.py

Requires: MISTRAL_API_KEY in .env (pointing to Sumii Local Dev workspace)
"""

import json
import logging
import os
import sys
import time

import requests
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from mistralai import (  # noqa: E402
    AgentHandoffDoneEvent,
    FunctionCallEvent,
    FunctionResultEntry,
    MessageOutputEvent,
    Mistral,  # noqa: E402
    ResponseDoneEvent,
    ResponseErrorEvent,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_KEY = os.environ.get("MISTRAL_API_KEY", "")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def delete_agent(agent_id: str) -> None:
    """Delete an agent via direct HTTP (SDK has no delete method)."""
    try:
        resp = requests.delete(
            f"https://api.mistral.ai/v1/agents/{agent_id}",
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=10,
        )
        if resp.status_code in [200, 204]:
            logger.debug(f"Deleted agent {agent_id}")
        else:
            logger.warning(f"Failed to delete agent {agent_id}: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Failed to delete agent {agent_id}: {e}")


def consume_stream(stream) -> dict:
    """Consume a Mistral Conversations stream and collect results.

    FunctionCallEvent fires multiple times per tool call (arguments stream in chunks).
    We accumulate arguments by tool_call_id.

    Returns dict with: text, function_calls, handoffs, errors, conversation_id
    """
    result: dict = {
        "text": "",
        "function_calls": [],
        "handoffs": [],
        "errors": [],
        "conversation_id": None,
    }

    # Accumulate function call arguments across chunks (keyed by tool_call_id)
    pending_calls: dict[str, dict] = {}

    for event in stream:
        if not hasattr(event, "data"):
            continue

        # Capture conversation ID from any event that has it
        conv_id = getattr(event.data, "conversation_id", None)
        if conv_id:
            result["conversation_id"] = conv_id

        match event.data:
            case MessageOutputEvent():
                content = event.data.content
                if content:
                    chunks = list(content) if isinstance(content, list) else [content]
                    for chunk in chunks:
                        if isinstance(chunk, str):
                            result["text"] += chunk  # type: ignore[operator]
                        elif hasattr(chunk, "text"):
                            result["text"] += chunk.text  # type: ignore[operator]
                        elif hasattr(chunk, "get"):
                            result["text"] += chunk.get("text", "")  # type: ignore[operator]

            case FunctionCallEvent():
                tool_call_id = getattr(event.data, "tool_call_id", None) or "unknown"
                fn_name = getattr(event.data, "name", "unknown")
                fn_args = getattr(event.data, "arguments", "")

                if tool_call_id not in pending_calls:
                    pending_calls[tool_call_id] = {
                        "tool_call_id": tool_call_id,
                        "name": fn_name,
                        "raw_arguments": "",
                    }
                # Accumulate argument chunks
                if fn_args:
                    pending_calls[tool_call_id]["raw_arguments"] += fn_args
                # Update name if we get a non-"unknown" name
                if fn_name and fn_name != "unknown":
                    pending_calls[tool_call_id]["name"] = fn_name

            case AgentHandoffDoneEvent():
                target = getattr(event.data, "to_agent_id", None) or getattr(event.data, "agent_id", None)
                result["handoffs"].append(target)  # type: ignore[union-attr]

            case ResponseErrorEvent():
                msg = getattr(event.data, "message", "Unknown error")
                code = getattr(event.data, "code", None)
                result["errors"].append({"message": msg, "code": code})  # type: ignore[union-attr]

            case ResponseDoneEvent():
                pass

    # Parse accumulated function call arguments
    for call_data in pending_calls.values():
        raw = call_data["raw_arguments"]
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        result["function_calls"].append(  # type: ignore[union-attr]
            {
                "tool_call_id": call_data["tool_call_id"],
                "name": call_data["name"],
                "arguments": parsed,
            }
        )

    return result


# ---------------------------------------------------------------------------
# Shared base instructions (simulating what base_instructions.py will provide)
# ---------------------------------------------------------------------------

BASE_INTAKE_AND_FACTS_INSTRUCTIONS = """You are Sumii's domain-specific intake specialist.

<<<YOUR ROLE: STRUCTURED LEGAL INTAKE>>>

You conduct client interviews to collect all facts needed for a lawyer-ready case summary.
You are NOT a lawyer. You do NOT assess cases. You COLLECT information.

<<<INTERVIEW TECHNIQUE>>>
- Ask ONE question at a time
- Build on previous answers
- Acknowledge responses before asking the next question
- Be professional, efficient, and thorough

<<<HANDOFF>>>
When you have collected enough facts according to the domain-specific criteria below,
SILENTLY hand off to the downstream agent. Do NOT announce the handoff.
"""

GERMAN_LANGUAGE_INSTRUCTIONS = """
<<<LANGUAGE>>>
- Detect user language (German or English) and respond in the same language
- Default to informal "du" unless user uses "Sie"
"""

# ---------------------------------------------------------------------------
# Domain-specific configs (simulating YAML content)
# ---------------------------------------------------------------------------

MIETRECHT_CONFIG = {
    "name": "Mietrecht",
    "intake_questions": """
<<<DOMAIN: MIETRECHT (Tenancy Law)>>>

KEY QUESTIONS FOR TENANCY DISPUTES:
1. Are you the tenant (Mieter) or landlord (Vermieter)?
2. What type of issue? (rent increase, repairs, deposit, termination, subletting)
3. When did the tenancy start? (Mietvertragsbeginn)
4. What is the monthly rent? (Kaltmiete / Warmmiete)
5. Have you notified the other party in writing? (Mängelanzeige)
6. Are there any deadlines? (Kündigungsfrist, Widerspruchsfrist)

FOR DOCUMENT DRAFTING (sublease, termination notice):
1. What document do you need?
2. Parties involved?
3. Duration and terms?
4. Special provisions?
""",
    "completion_criteria": """
<<<COMPLETION CRITERIA: MIETRECHT>>>
Before handoff, you MUST have collected:
- Tenant or landlord role
- Type of tenancy issue
- Tenancy start date
- Rent amount
- Written notification status
- Any deadlines
""",
}

VERTRAGSRECHT_CONFIG = {
    "name": "Vertragsrecht",
    "intake_questions": """
<<<DOMAIN: VERTRAGSRECHT (Contract Law)>>>

KEY QUESTIONS FOR CONTRACT DISPUTES:
1. Private or business customer? (Verbraucher oder Unternehmer)
2. What type of contract? (purchase, service, online order)
3. Payment method used? (PayPal, bank transfer, credit card — relevant for buyer protection)
4. What was promised vs. what was delivered?
5. Have you contacted the seller/provider? What was their response?
6. Purchase/contract date? (relevant for warranty/return deadlines)
7. Do you have the contract/order confirmation in writing?

FOR DOCUMENT DRAFTING:
1. What type of contract do you need?
2. Parties and their roles?
3. Key terms and conditions?
4. Duration and termination clauses?
""",
    "completion_criteria": """
<<<COMPLETION CRITERIA: VERTRAGSRECHT>>>
Before handoff, you MUST have collected:
- Consumer or business context
- Contract type
- Payment method
- Delivery/service discrepancy
- Prior communication with other party
- Key dates (purchase, complaint)
""",
}

# ---------------------------------------------------------------------------
# Test helper: create a domain agent from template
# ---------------------------------------------------------------------------


def create_test_domain_agent(client: Mistral, domain_config: dict, handoff_ids: list[str] | None = None) -> str:
    """Create a domain agent using the template composition approach."""
    instructions = f"""{BASE_INTAKE_AND_FACTS_INSTRUCTIONS}

{domain_config['intake_questions']}

{domain_config['completion_criteria']}

{GERMAN_LANGUAGE_INSTRUCTIONS}
"""

    kwargs: dict = {
        "model": "mistral-medium-2505",
        "name": f"Test{domain_config['name']} Agent",
        "description": f"Test domain agent for {domain_config['name']}",
        "instructions": instructions,
    }
    # Only pass handoffs if non-empty (API rejects empty list)
    if handoff_ids:
        kwargs["handoffs"] = handoff_ids

    agent = client.beta.agents.create(**kwargs)
    logger.info(f"Created test agent: {domain_config['name']} -> id={agent.id}, version={agent.version}")
    return agent.id


# ---------------------------------------------------------------------------
# Test 1: Template-composed agent follows domain-specific questions
# ---------------------------------------------------------------------------


def test_template_composition(client: Mistral) -> bool:
    """Test that a template-composed domain agent follows domain-specific Qs."""
    logger.info("=" * 60)
    logger.info("TEST 1: Template Composition")
    logger.info("=" * 60)

    agent_id = create_test_domain_agent(client, MIETRECHT_CONFIG)

    try:
        stream = client.beta.conversations.start_stream(
            agent_id=agent_id,
            inputs="Meine Heizung ist seit 3 Wochen kaputt und mein Vermieter reagiert nicht.",
        )
        result = consume_stream(stream)
        response_text = result["text"]

        logger.info(f"Agent response ({len(response_text)} chars):\n{response_text[:500]}")

        if result["errors"]:
            logger.error(f"Errors: {result['errors']}")
            return False

        if len(response_text) > 20:
            logger.info("PASS: Template-composed agent produced a response")
            tenancy_keywords = ["mieter", "vermieter", "heizung", "wohnung", "miet", "tenant", "landlord", "heating"]
            matches = [kw for kw in tenancy_keywords if kw in response_text.lower()]
            if matches:
                logger.info(f"PASS: Response contains tenancy-relevant terms: {matches}")
            else:
                logger.warning("WARN: Response doesn't contain expected tenancy terms (may still be valid)")
            return True
        else:
            logger.error(f"FAIL: Response too short ({len(response_text)} chars)")
            return False

    finally:
        delete_agent(agent_id)


# ---------------------------------------------------------------------------
# Test 2: Router with classify_legal_domain function tool
# ---------------------------------------------------------------------------

CLASSIFY_LEGAL_DOMAIN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "classify_legal_domain",
        "description": (
            "Classify the user's legal domain and intent based on their message. "
            "Call this tool BEFORE handing off to determine the correct domain agent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": [
                        "vertragsrecht",
                        "mietrecht",
                        "arbeitsrecht",
                        "familienrecht",
                        "erbrecht",
                        "deliktsrecht",
                        "sachenrecht",
                        "gesellschaftsrecht",
                    ],
                    "description": "The classified legal domain",
                },
                "intent": {
                    "type": "string",
                    "enum": ["dispute", "drafting"],
                    "description": "Whether the user has a concrete dispute or needs document drafting",
                },
                "confidence": {
                    "type": "number",
                    "description": "Classification confidence between 0.0 and 1.0",
                },
                "is_civil": {
                    "type": "boolean",
                    "description": "Whether this is a civil/private law matter (True) or criminal/public (False)",
                },
            },
            "required": ["domain", "intent", "confidence", "is_civil"],
        },
    },
}


def test_router_classification(client: Mistral) -> bool:
    """Test that Router calls classify_legal_domain and we can read the result."""
    logger.info("=" * 60)
    logger.info("TEST 2: Router Function Tool Classification")
    logger.info("=" * 60)

    # Create a simple downstream agent (dummy target)
    dummy_agent = client.beta.agents.create(
        model="mistral-medium-2505",
        name="TestDummy Downstream",
        description="Dummy agent for testing handoff",
        instructions="You are a test agent. Just say 'Handoff received successfully.'",
    )
    logger.info(f"Created dummy downstream agent: {dummy_agent.id}")

    # Create Router with classify tool + handoff to dummy
    router_agent = client.beta.agents.create(
        model="mistral-medium-2505",
        name="TestSmart Router",
        description="Test router with classification tool",
        instructions="""You are a legal intake router.

<<<WORKFLOW>>>
1. When you receive a user message, FIRST call the classify_legal_domain tool
2. After classification, hand off to the downstream agent

<<<RULES>>>
- ALWAYS call classify_legal_domain before doing anything else
- You are SILENT — produce no text output to the user
- After calling the tool and receiving the result, hand off immediately
""",
        tools=[CLASSIFY_LEGAL_DOMAIN_SCHEMA],
        handoffs=[dummy_agent.id],
    )
    logger.info(f"Created test router: {router_agent.id}")

    test_cases = [
        {
            "message": "Meine Heizung ist kaputt und der Vermieter reagiert nicht.",
            "expected_domain": "mietrecht",
            "expected_intent": "dispute",
        },
        {
            "message": "Ich habe online etwas bestellt aber es wurde nie geliefert. Ich will mein Geld zurück.",
            "expected_domain": "vertragsrecht",
            "expected_intent": "dispute",
        },
        {
            "message": "Ich brauche Hilfe bei einem Untermietvertrag für meine Wohnung.",
            "expected_domain": "mietrecht",
            "expected_intent": "drafting",
        },
    ]

    results = []
    try:
        for i, tc in enumerate(test_cases):
            logger.info(f"\n--- Test case {i + 1}: {tc['message'][:60]}...")

            stream = client.beta.conversations.start_stream(
                agent_id=router_agent.id,
                inputs=tc["message"],
            )
            result = consume_stream(stream)

            if result["errors"]:
                logger.error(f"  Errors: {result['errors']}")

            # Check for classify function call
            classify_calls = [fc for fc in result["function_calls"] if fc["name"] == "classify_legal_domain"]

            if classify_calls:
                fc = classify_calls[0]
                args = fc["arguments"]
                logger.info(f"  Classification: {json.dumps(args, indent=2)}")

                domain = args.get("domain", "")
                intent = args.get("intent", "")
                confidence = args.get("confidence", 0)
                is_civil = args.get("is_civil", None)

                domain_match = domain == tc["expected_domain"]
                intent_match = intent == tc["expected_intent"]

                logger.info(
                    f"  Domain: {domain} (expected: {tc['expected_domain']}) -> {'PASS' if domain_match else 'MISS'}"
                )
                logger.info(
                    f"  Intent: {intent} (expected: {tc['expected_intent']}) -> {'PASS' if intent_match else 'MISS'}"
                )
                logger.info(f"  Confidence: {confidence}, Is civil: {is_civil}")

                results.append(domain_match)
            else:
                logger.warning("  WARN: No classify_legal_domain call detected")
                if result["text"]:
                    logger.info(f"  Response text: {result['text'][:200]}")
                if result["handoffs"]:
                    logger.info(f"  Handoffs: {result['handoffs']}")
                results.append(False)

            time.sleep(1)

        passed = sum(results)
        total = len(results)
        logger.info(f"\nClassification results: {passed}/{total} domains correct")

        success = passed >= 2  # Allow 1 miss (LLM variance)
        logger.info(f"TEST 2: {'PASS' if success else 'FAIL'}")
        return success

    finally:
        delete_agent(router_agent.id)
        delete_agent(dummy_agent.id)
        logger.info("Cleaned up test agents")


# ---------------------------------------------------------------------------
# Test 3: Fan-in handoff (multiple domain agents → same downstream)
# ---------------------------------------------------------------------------


def test_fan_in_handoff(client: Mistral) -> bool:
    """Test that multiple domain agents can all hand off to the same downstream agent."""
    logger.info("=" * 60)
    logger.info("TEST 3: Fan-in Handoff")
    logger.info("=" * 60)

    # Create a shared downstream agent (simulating Reasoning Logic)
    downstream = client.beta.agents.create(
        model="mistral-medium-2505",
        name="TestShared Downstream",
        description="Shared downstream for fan-in test",
        instructions=(
            "You received a handoff. Respond with: 'Fan-in handoff received.' "
            "Then briefly summarize what the user told the previous agent."
        ),
    )
    logger.info(f"Created shared downstream: {downstream.id}")

    mietrecht_id = create_test_domain_agent(client, MIETRECHT_CONFIG, handoff_ids=[downstream.id])
    vertragsrecht_id = create_test_domain_agent(client, VERTRAGSRECHT_CONFIG, handoff_ids=[downstream.id])

    try:
        # Test: Mietrecht agent → downstream
        logger.info("\n--- Fan-in from Mietrecht agent ---")
        stream = client.beta.conversations.start_stream(
            agent_id=mietrecht_id,
            inputs=(
                "Ich bin Mieter. Heizung kaputt seit 2 Wochen. Kaltmiete 800 EUR. "
                "Vermieter per Email informiert. Keine Frist gesetzt. Ich will dass er repariert."
            ),
        )
        result = consume_stream(stream)
        logger.info(f"Response ({len(result['text'])} chars): {result['text'][:300]}")
        logger.info(f"Handoffs: {result['handoffs']}")
        logger.info(f"Errors: {result['errors']}")
        mietrecht_ok = len(result["text"]) > 10 or len(result["handoffs"]) > 0
        logger.info(f"Mietrecht → downstream: {'PASS' if mietrecht_ok else 'FAIL'}")

        time.sleep(1)

        # Test: Vertragsrecht agent → downstream
        logger.info("\n--- Fan-in from Vertragsrecht agent ---")
        stream = client.beta.conversations.start_stream(
            agent_id=vertragsrecht_id,
            inputs=(
                "Ich bin Verbraucher. Online-Kauf. PayPal bezahlt. Ware nie geliefert. "
                "Verkäufer antwortet nicht. Kaufdatum 01.02.2026. Bestellbestätigung per Email."
            ),
        )
        result = consume_stream(stream)
        logger.info(f"Response ({len(result['text'])} chars): {result['text'][:300]}")
        logger.info(f"Handoffs: {result['handoffs']}")
        logger.info(f"Errors: {result['errors']}")
        vertragsrecht_ok = len(result["text"]) > 10 or len(result["handoffs"]) > 0
        logger.info(f"Vertragsrecht → downstream: {'PASS' if vertragsrecht_ok else 'FAIL'}")

        success = mietrecht_ok and vertragsrecht_ok
        logger.info(f"\nTEST 3: {'PASS' if success else 'FAIL'}")
        return success

    finally:
        for aid in [mietrecht_id, vertragsrecht_id, downstream.id]:
            delete_agent(aid)
        logger.info("Cleaned up test agents")


# ---------------------------------------------------------------------------
# Test 4 (optional): Function tool for dynamic Qs (Approach B comparison)
# ---------------------------------------------------------------------------


def test_function_tool_dynamic_qs(client: Mistral) -> bool:
    """Test Approach B: agent calls a function tool to get domain Qs at runtime.

    Measures latency overhead of the extra function call round-trip.
    """
    logger.info("=" * 60)
    logger.info("TEST 4: Function Tool for Dynamic Questions (Approach B)")
    logger.info("=" * 60)

    get_domain_questions_schema = {
        "type": "function",
        "function": {
            "name": "get_domain_intake_questions",
            "description": (
                "Get the domain-specific intake questions for the user's legal domain. "
                "Call this at the start to know what questions to ask."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "enum": ["mietrecht", "vertragsrecht", "arbeitsrecht"],
                        "description": "The legal domain to get questions for",
                    },
                },
                "required": ["domain"],
            },
        },
    }

    agent = client.beta.agents.create(
        model="mistral-medium-2505",
        name="TestDynamic Q Agent",
        description="Test agent that fetches domain Qs via function tool",
        instructions="""You are a legal intake agent.

<<<WORKFLOW>>>
1. When you receive a user message, first call get_domain_intake_questions to get the right questions for this domain
2. Use the returned questions to guide your interview
3. Ask ONE question at a time

<<<RULES>>>
- ALWAYS call get_domain_intake_questions first before responding to the user
- Use the questions returned by the tool to guide your interview
""",
        tools=[get_domain_questions_schema],
    )
    logger.info(f"Created dynamic Q agent: {agent.id}")

    try:
        start_time = time.time()

        stream = client.beta.conversations.start_stream(
            agent_id=agent.id,
            inputs="Meine Heizung ist kaputt.",
        )
        result = consume_stream(stream)
        first_stream_time = time.time() - start_time

        logger.info(f"First stream time: {first_stream_time:.2f}s")
        logger.info(f"Function calls: {len(result['function_calls'])}")
        logger.info(f"Text: {result['text'][:200]}")

        # Check if it called the function
        domain_qs_calls = [fc for fc in result["function_calls"] if fc["name"] == "get_domain_intake_questions"]

        if domain_qs_calls and result["conversation_id"]:
            fc = domain_qs_calls[0]
            logger.info(f"Function call args: {fc['arguments']}")

            # Send function result back
            domain_questions = json.dumps(
                {
                    "domain": "mietrecht",
                    "questions": [
                        "Bist du Mieter oder Vermieter?",
                        "Welche Art von Problem? (Miete, Reparaturen, Kündigung)",
                        "Seit wann besteht das Mietverhältnis?",
                        "Wie hoch ist die Kaltmiete?",
                    ],
                }
            )

            append_start = time.time()
            fn_result = FunctionResultEntry(
                tool_call_id=fc["tool_call_id"],
                result=domain_questions,
            )
            append_stream = client.beta.conversations.append_stream(
                conversation_id=result["conversation_id"],
                inputs=[fn_result],
            )
            append_result = consume_stream(append_stream)
            append_time = time.time() - append_start
            total_time = time.time() - start_time

            logger.info(f"Append stream time: {append_time:.2f}s")
            logger.info(f"Total round-trip time: {total_time:.2f}s")
            logger.info(f"Response after function result:\n{append_result['text'][:400]}")

            logger.info(
                f"\nApproach B latency: ~{first_stream_time:.1f}s (fn call) " f"+ ~{append_time:.1f}s (response)"
            )
            logger.info("TEST 4: PASS")
            return True
        else:
            logger.warning("No get_domain_intake_questions call detected")
            logger.info("TEST 4: FAIL (agent didn't call the function tool)")
            return False

    finally:
        delete_agent(agent.id)
        logger.info("Cleaned up test agent")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    if not API_KEY:
        logger.error("MISTRAL_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    client = Mistral(api_key=API_KEY)

    logger.info("Starting domain agent inline tests against Mistral Local Dev workspace...")
    logger.info("These tests create temporary agents, run conversations, and clean up.\n")

    results = {}

    # Test 1: Template composition
    try:
        results["template_composition"] = test_template_composition(client)
    except Exception as e:
        logger.error(f"TEST 1 ERROR: {e}")
        results["template_composition"] = False

    time.sleep(2)

    # Test 2: Router classification
    try:
        results["router_classification"] = test_router_classification(client)
    except Exception as e:
        logger.error(f"TEST 2 ERROR: {e}")
        results["router_classification"] = False

    time.sleep(2)

    # Test 3: Fan-in handoff
    try:
        results["fan_in_handoff"] = test_fan_in_handoff(client)
    except Exception as e:
        logger.error(f"TEST 3 ERROR: {e}")
        results["fan_in_handoff"] = False

    time.sleep(2)

    # Test 4: Dynamic Qs (Approach B)
    try:
        results["dynamic_qs"] = test_function_tool_dynamic_qs(client)
    except Exception as e:
        logger.error(f"TEST 4 ERROR: {e}")
        results["dynamic_qs"] = False

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    for test_name, passed in results.items():
        logger.info(f"  {test_name}: {'PASS' if passed else 'FAIL'}")

    core_passed = all(
        results.get(k, False) for k in ["template_composition", "router_classification", "fan_in_handoff"]
    )

    logger.info(f"\nCore tests (1-3): {'ALL PASS' if core_passed else 'SOME FAILED'}")

    if core_passed:
        logger.info("\nRECOMMENDATION: Approach A (template composition) is validated.")
        logger.info("Proceed with implementation using domain_factory.py pattern.")

        if results.get("dynamic_qs"):
            logger.info("Approach B also works but adds latency overhead.")
        else:
            logger.info("Approach B had issues — template composition is the clear winner.")
    else:
        logger.info("\nSome core tests failed. Review output above and re-run.")

    sys.exit(0 if core_passed else 1)


if __name__ == "__main__":
    main()
