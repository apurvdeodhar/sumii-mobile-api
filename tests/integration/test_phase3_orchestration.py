#!/usr/bin/env python3
"""Phase 3: Dynamic Agent Orchestration Test

Tests the ConversationOrchestrator's ability to route to agents based on conversation state.

Test Scenarios:
1. New conversation (no facts) → Routes to Intake Agent
2. Facts collected → Routes to Reasoning Agent
3. Analysis done → Routes to Summary Agent
4. Summary generated → Routes to Router Agent
5. Partial facts → Still routes to Intake Agent

These are integration tests that test multiple components working together.
Requires Docker services (PostgreSQL, backend) and may require API keys.
"""

import asyncio

import pytest
import requests

from app.database import AsyncSessionLocal
from app.models.conversation import Conversation, ConversationStatus
from app.services.orchestrator import ConversationOrchestrator

pytestmark = [pytest.mark.integration, pytest.mark.requires_services]

# Configuration
BASE_URL = "http://localhost:8000"


class Colors:
    """ANSI color codes for terminal output"""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_section(title: str):
    """Print a section header"""
    print(f"\n{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{title}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'=' * 80}{Colors.ENDC}\n")


def print_test(test_num: int, description: str):
    """Print a test description"""
    print(f"{Colors.OKCYAN}[TEST {test_num}] {description}{Colors.ENDC}")


def print_success(message: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}✅ {message}{Colors.ENDC}")


def print_error(message: str):
    """Print error message"""
    print(f"{Colors.FAIL}❌ {message}{Colors.ENDC}")


def print_info(message: str, indent: int = 3):
    """Print info message"""
    print(f"{' ' * indent}{message}")


async def test_orchestrator_routing():
    """Test ConversationOrchestrator routing logic"""
    print_section("PHASE 3: Dynamic Agent Orchestration Testing")

    orchestrator = ConversationOrchestrator()

    # Test 1: New conversation (no facts)
    print_test(1, "New conversation → Should route to Intake Agent")
    conversation = Conversation(
        user_id="00000000-0000-0000-0000-000000000001",
        title="Test Conversation",
        status=ConversationStatus.ACTIVE,
        current_agent="router",
        # All metadata fields are None/False by default
    )
    agent = await orchestrator.determine_next_agent(conversation)
    assert agent == "intake", f"Expected 'intake', got '{agent}'"
    print_success(f"Routed to: {agent}")
    print_info("Reason: No facts collected yet")

    # Test 2: Facts collected, no analysis
    print_test(2, "Facts complete → Should route to Reasoning Agent")
    conversation.who = {"collected": True, "claimant": "User", "defendant": "Landlord"}
    conversation.what = {"collected": True, "issue": "Broken heating", "legal_area": "Mietrecht"}
    conversation.when = {"collected": True, "timeline": [{"date": "2025-01-10", "event": "Heating broke"}]}
    conversation.where = {"collected": True, "location": "Berlin", "jurisdiction": "Berlin"}
    conversation.why = {"collected": True, "desired_outcome": "Rent reduction"}
    conversation.analysis_done = False
    agent = await orchestrator.determine_next_agent(conversation)
    assert agent == "reasoning", f"Expected 'reasoning', got '{agent}'"
    print_success(f"Routed to: {agent}")
    print_info("Reason: All 5W facts collected, analysis not done")

    # Test 3: Analysis done, no summary
    print_test(3, "Analysis complete → Should route to Summary Agent")
    conversation.analysis_done = True
    conversation.summary_generated = False
    agent = await orchestrator.determine_next_agent(conversation)
    assert agent == "summary", f"Expected 'summary', got '{agent}'"
    print_success(f"Routed to: {agent}")
    print_info("Reason: Legal analysis complete, summary not generated")

    # Test 4: Summary generated
    print_test(4, "Summary generated → Should route to Router Agent")
    conversation.summary_generated = True
    agent = await orchestrator.determine_next_agent(conversation)
    assert agent == "router", f"Expected 'router', got '{agent}'"
    print_success(f"Routed to: {agent}")
    print_info("Reason: Conversation complete, handle follow-up questions")

    # Test 5: Partial facts (missing "why")
    print_test(5, "Partial facts → Should still route to Intake Agent")
    conversation2 = Conversation(
        user_id="00000000-0000-0000-0000-000000000001",
        title="Test Conversation 2",
        status=ConversationStatus.ACTIVE,
        current_agent="intake",
        who={"collected": True, "claimant": "User"},
        what={"collected": True, "issue": "Broken heating"},
        when={"collected": True, "timeline": []},
        where={"collected": True, "location": "Berlin"},
        why=None,  # Missing!
        analysis_done=False,
        summary_generated=False,
    )
    agent = await orchestrator.determine_next_agent(conversation2)
    assert agent == "intake", f"Expected 'intake', got '{agent}'"
    print_success(f"Routed to: {agent}")
    print_info("Reason: Missing 'why' fact (desired outcome)")

    # Test 6: Facts completeness check
    print_test(6, "Facts completeness check → Validate _check_facts_completeness()")

    # Complete facts
    complete_conv = Conversation(
        user_id="00000000-0000-0000-0000-000000000001",
        who={"collected": True},
        what={"collected": True},
        when={"collected": True},
        where={"collected": True},
        why={"collected": True},
    )
    is_complete = orchestrator._check_facts_completeness(complete_conv)
    assert is_complete is True, "Expected facts to be complete"
    print_success("Complete facts detected correctly")

    # Incomplete facts (missing "when")
    incomplete_conv = Conversation(
        user_id="00000000-0000-0000-0000-000000000001",
        who={"collected": True},
        what={"collected": True},
        when=None,  # Missing!
        where={"collected": True},
        why={"collected": True},
    )
    is_complete = orchestrator._check_facts_completeness(incomplete_conv)
    assert is_complete is False, "Expected facts to be incomplete"
    print_success("Incomplete facts detected correctly")

    print_section("✅ ALL ORCHESTRATION TESTS PASSED!")


async def test_conversation_state_updates():
    """Test ConversationOrchestrator.update_conversation_state()"""
    print_section("Testing Conversation State Updates")

    orchestrator = ConversationOrchestrator()

    # Test 1: Intake Agent updates facts
    print_test(1, "Intake Agent → Should update 5W facts")
    conversation = Conversation(
        user_id="00000000-0000-0000-0000-000000000001",
        title="Test",
        status=ConversationStatus.ACTIVE,
    )

    facts = {
        "who": {"claimant": "User", "defendant": "Landlord"},
        "what": {"issue": "Broken heating", "legal_area": "Mietrecht"},
        "when": {"timeline": [{"date": "2025-01-10", "event": "Heating broke"}]},
        "where": {"location": "Berlin", "jurisdiction": "Berlin"},
        "why": {"desired_outcome": "Rent reduction"},
    }

    await orchestrator.update_conversation_state(conversation, "intake", facts)

    # Verify facts were set with "collected": True
    assert conversation.who.get("collected") is True, "WHO fact not marked as collected"
    assert conversation.who.get("claimant") == "User", "WHO fact data incorrect"
    assert conversation.what.get("collected") is True, "WHAT fact not marked as collected"
    assert conversation.when.get("collected") is True, "WHEN fact not marked as collected"
    assert conversation.where.get("collected") is True, "WHERE fact not marked as collected"
    assert conversation.why.get("collected") is True, "WHY fact not marked as collected"
    print_success("Facts updated correctly")
    print_info(f"WHO: {conversation.who}")
    print_info(f"WHAT: {conversation.what}")

    # Test 2: Reasoning Agent sets analysis_done
    print_test(2, "Reasoning Agent → Should set analysis_done = True")
    conversation.analysis_done = False
    await orchestrator.update_conversation_state(conversation, "reasoning", None)
    assert conversation.analysis_done is True, "analysis_done not set"
    print_success("analysis_done = True")

    # Test 3: Summary Agent sets summary_generated
    print_test(3, "Summary Agent → Should set summary_generated = True")
    conversation.summary_generated = False
    await orchestrator.update_conversation_state(conversation, "summary", None)
    assert conversation.summary_generated is True, "summary_generated not set"
    print_success("summary_generated = True")

    print_section("✅ STATE UPDATE TESTS PASSED!")


async def test_integration_with_backend():
    """Test orchestrator integration with actual backend"""
    print_section("Integration Test: Orchestrator + Backend")

    # Step 1: Create user
    print_test(1, "Create test user")
    test_email = "phase3-test@sumii.de"
    test_password = "TestPassword123!"

    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={"email": test_email, "password": test_password},
        timeout=10,
    )

    detail_lower = response.json().get("detail", "").lower()
    if response.status_code == 400 and ("already" in detail_lower or "registered" in detail_lower):
        # User already exists, login instead
        print_info("User already exists, logging in...")
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": test_email, "password": test_password},
            timeout=10,
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
    elif response.status_code == 201:
        # New user, need to login
        print_info("New user created, logging in...")
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": test_email, "password": test_password},
            timeout=10,
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
    else:
        raise Exception(f"Unexpected response: {response.status_code} - {response.json()}")

    print_success("Token obtained")

    # Step 2: Create conversation
    print_test(2, "Create conversation")
    response = requests.post(
        f"{BASE_URL}/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Phase 3 Test - Orchestration"},
        timeout=10,
    )
    assert response.status_code == 201
    conversation_id = response.json()["id"]
    print_success(f"Conversation created: {conversation_id}")

    # Step 3: Get conversation and verify orchestrator would route to intake
    print_test(3, "Verify new conversation routes to Intake")
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conversation = result.scalar_one()

        orchestrator = ConversationOrchestrator()
        agent = await orchestrator.determine_next_agent(conversation)

        assert agent == "intake", f"Expected 'intake', got '{agent}'"
        print_success(f"Orchestrator correctly routes to: {agent}")

    # Step 4: Clean up
    print_test(4, "Clean up test conversation")
    response = requests.delete(
        f"{BASE_URL}/api/v1/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert response.status_code == 204
    print_success("Conversation deleted")

    print_section("✅ INTEGRATION TEST PASSED!")


async def run_all_tests():
    """Run all Phase 3 tests"""
    print_section("🚀 PHASE 3: DYNAMIC AGENT ORCHESTRATION - COMPREHENSIVE TESTS 🚀")
    print_info("Testing: ConversationOrchestrator routing logic")
    print_info("Components: determine_next_agent(), update_conversation_state(), facts_completeness")

    try:
        # Test 1: Orchestrator routing logic
        await test_orchestrator_routing()

        # Test 2: Conversation state updates
        await test_conversation_state_updates()

        # Test 3: Integration with backend
        await test_integration_with_backend()

        print_section("🎉 ALL PHASE 3 TESTS PASSED! 🎉")
        print_success("Phase 3 (Dynamic Agent Orchestration) COMPLETE ✨")
        print_info("\nVerified:")
        print_info("  ✅ Orchestrator routes to correct agent based on conversation state")
        print_info("  ✅ Facts completeness check works correctly")
        print_info("  ✅ Conversation state updates work (facts, analysis, summary)")
        print_info("  ✅ Integration with backend endpoints")

    except Exception as e:
        print_section("❌ TESTS FAILED")
        print_error(f"Error: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())
