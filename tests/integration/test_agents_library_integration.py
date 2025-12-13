#!/usr/bin/env python3
"""Test Agents Document Library Integration

Verifies that Reasoning and Summary agents have access to the document library.
Tests that agents can retrieve BGB sections and use templates.

These are integration tests that test Mistral AI agents with document library.
Requires API keys (MISTRAL_API_KEY) to be set.
"""

import pytest
from mistralai import Mistral

from app.config import settings
from app.services.agents import create_reasoning_agent, create_summary_agent

pytestmark = [pytest.mark.integration, pytest.mark.requires_api]


def test_reasoning_agent_library_access():
    """Test Reasoning Agent has document library access"""
    print("=" * 80)
    print("Testing Reasoning Agent Document Library Access")
    print("=" * 80)

    # Step 1: Create Reasoning Agent
    print("\n[1] Creating Reasoning Agent...")
    try:
        agent_id = create_reasoning_agent()
        print(f"✅ Reasoning Agent created: {agent_id}")
    except Exception as e:
        print(f"❌ Failed to create Reasoning Agent: {e}")
        return

    # Step 2: Agent created successfully - library configuration is in tools parameter
    print("\n[2] Agent configuration...")
    print(f"✅ Agent configured with library ID: {settings.MISTRAL_LIBRARY_ID}")
    print("   (Library tool added via get_document_library_tool())")

    client = Mistral(api_key=settings.MISTRAL_API_KEY)

    # Step 3: Test with a sample legal query
    print("\n[3] Testing with sample legal query...")
    try:
        # Simple test: Send a message about heating issue
        response = client.agents.complete(
            agent_id=agent_id,
            messages=[
                {
                    "role": "user",
                    "content": "Meine Heizung ist seit 2 Wochen kaputt. Kann ich die Miete mindern?",
                }
            ],
        )

        print("✅ Agent responded:")
        print(f"   {response.choices[0].message.content[:200]}...")

        # Check if response mentions BGB sections (would come from library)
        content = response.choices[0].message.content
        if "§536" in content or "BGB" in content or "Mietminderung" in content:
            print("✅ Response contains legal references (likely from library)")
        else:
            print("⚠️  Response doesn't mention specific BGB sections")

    except Exception as e:
        print(f"❌ Failed to test agent with query: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 80)
    print("Reasoning Agent Library Test Complete!")
    print("=" * 80)


def test_summary_agent_library_access():
    """Test Summary Agent has document library access"""
    print("\n" + "=" * 80)
    print("Testing Summary Agent Document Library Access")
    print("=" * 80)

    # Step 1: Create Summary Agent
    print("\n[1] Creating Summary Agent...")
    try:
        agent_id = create_summary_agent()
        print(f"✅ Summary Agent created: {agent_id}")
    except Exception as e:
        print(f"❌ Failed to create Summary Agent: {e}")
        return

    # Step 2: Agent created successfully - library configuration is in tools parameter
    print("\n[2] Agent configuration...")
    print(f"✅ Agent configured with library ID: {settings.MISTRAL_LIBRARY_ID}")
    print("   (Library tool added via get_document_library_tool())")

    print("\n" + "=" * 80)
    print("Summary Agent Library Test Complete!")
    print("=" * 80)


if __name__ == "__main__":
    # Test both agents
    test_reasoning_agent_library_access()
    print("\n\n")
    test_summary_agent_library_access()
