#!/usr/bin/env python3
"""
Script to delete all existing Mistral agents and reset to fresh state.

This solves the agent version mismatch error (404) that occurs when agents
have been updated many times during development, accumulating versions.

Usage:
    cd sumii-mobile-api
    source .venv/bin/activate
    python scripts/reset_mistral_agents.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
from mistralai import Mistral  # noqa: E402

load_dotenv()


def list_agents(client: Mistral) -> list:
    """List all agents in the account."""
    agents = client.beta.agents.list()
    return list(agents)


def delete_agent(client: Mistral, agent_id: str, agent_name: str, api_key: str) -> bool:
    """Delete a single agent by ID using direct HTTP request."""
    import requests

    try:
        response = requests.delete(
            f"https://api.mistral.ai/v1/agents/{agent_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code in [200, 204]:
            print(f"  ✓ Deleted: {agent_name} ({agent_id})")
            return True
        else:
            print(f"  ✗ Failed to delete {agent_name}: HTTP {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"  ✗ Failed to delete {agent_name}: {e}")
        return False


def main():
    """Delete all Sumii agents from Mistral."""
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        print("ERROR: MISTRAL_API_KEY not found in environment")
        sys.exit(1)

    client = Mistral(api_key=api_key)

    print("🔍 Fetching existing agents from Mistral...")
    agents = list_agents(client)

    if not agents:
        print("No agents found. Nothing to delete.")
        return

    print(f"\n📋 Found {len(agents)} agent(s):\n")
    for agent in agents:
        print(f"  - {agent.name} (ID: {agent.id})")

    # Filter to only Sumii agents (by name pattern) - includes old and new names
    sumii_agent_names = [
        # Current names (v2)
        "Router Agent",
        "Intake Agent",
        "Facts Agent",
        "Reasoning Logic Agent",
        "Wrap-Up Agent",
        "Summary Agent",
        # Old names (v1)
        "Legal Router Agent",
        "Legal Intake Agent",
        "Fact Completion Agent",
        "Legal Summary Agent",
    ]

    sumii_agents = [a for a in agents if a.name in sumii_agent_names]

    if not sumii_agents:
        print("\nNo Sumii agents found. Nothing to delete.")
        return

    print(f"\n🗑️  Will delete {len(sumii_agents)} Sumii agent(s):")
    for agent in sumii_agents:
        print(f"  - {agent.name}")

    # Confirm deletion
    confirm = input("\n⚠️  Type 'DELETE' to confirm deletion: ")
    if confirm != "DELETE":
        print("Aborted.")
        return

    print("\n🚀 Deleting agents...")
    deleted_count = 0
    for agent in sumii_agents:
        if delete_agent(client, agent.id, agent.name, api_key):
            deleted_count += 1

    print(f"\n✅ Deleted {deleted_count}/{len(sumii_agents)} agents.")
    print("\n📝 Next steps:")
    print("  1. Restart the API: docker compose restart sumii-mobile-api")
    print("  2. Agents will be recreated fresh with version 1")
    print("  3. Start a new conversation to test")


if __name__ == "__main__":
    main()
