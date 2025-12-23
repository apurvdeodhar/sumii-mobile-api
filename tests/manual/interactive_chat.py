#!/usr/bin/env python3
"""
Sumii Mobile API - Interactive Chat Test

This script provides an INTERACTIVE way to test the WebSocket chat with Mistral AI.
It shows streaming chunks in real-time and prompts for Y/n after each message.

Features:
- Shows each streaming token as it arrives from Mistral
- Prompts Y/n after each AI response to continue
- Can type custom messages or use predefined scenarios
- Displays full agent responses

Usage:
    # Interactive mode (type your own messages)
    .venv/bin/python3 tests/manual/interactive_chat.py

    # Run with predefined scenario
    .venv/bin/python3 tests/manual/interactive_chat.py --scenario tenant

    # Auto-run scenario without prompts (for CI)
    .venv/bin/python3 tests/manual/interactive_chat.py --scenario tenant --auto
"""

import argparse
import asyncio
import json
import sys
import time

import httpx
import websockets

# Configuration
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"
API_V1 = f"{BASE_URL}/api/v1"


# ANSI Colors
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


# Predefined scenarios
SCENARIOS = {
    "tenant": {
        "title": "Mietminderung wegen defekter Heizung",
        "legal_area": "Mietrecht",
        "messages": [
            "Hallo, ich brauche dringend Hilfe. Meine Heizung ist seit "
            "3 Wochen kaputt und der Vermieter reagiert nicht.",
            "Ich wohne seit 2 Jahren in Berlin-Kreuzberg. Die Kaltmiete beträgt 850 Euro.",
            "Ich habe dem Vermieter am 1. Dezember per E-Mail Bescheid gegeben.",
            "In der Wohnung sind es nur noch 15 Grad. Ich habe Fotos gemacht.",
            "Ich möchte wissen, ob ich die Miete mindern kann.",
        ],
    },
    "employment": {
        "title": "Kündigung nach Krankheit",
        "legal_area": "Arbeitsrecht",
        "messages": [
            "Ich wurde gekündigt nachdem ich 3 Wochen krank war.",
            "Ich arbeite seit 5 Jahren im Unternehmen als Buchhalter.",
            "Die Kündigung kam am Tag meiner Rückkehr ohne Vorwarnung.",
        ],
    },
}


class InteractiveChatTest:
    """Interactive chat testing with Mistral AI"""

    def __init__(self, auto_mode: bool = False):
        self.auto_mode = auto_mode
        self.client = httpx.Client(timeout=30.0)
        self.token = None
        self.user_id = None
        self.conversation_id = None
        self.email = f"interactive-{int(time.time())}@sumii.de"
        self.password = "TestPassword123!"

    def print_header(self, text: str):
        print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.ENDC}")
        print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")

    def print_info(self, text: str):
        print(f"{Colors.YELLOW}ℹ️  {text}{Colors.ENDC}")

    def print_success(self, text: str):
        print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

    def print_error(self, text: str):
        print(f"{Colors.RED}❌ {text}{Colors.ENDC}")

    def print_user_message(self, text: str):
        print(f"\n{Colors.CYAN}{Colors.BOLD}👤 YOU:{Colors.ENDC}")
        print(f"{Colors.CYAN}{text}{Colors.ENDC}")

    def print_agent_start(self, agent: str):
        print(f"\n{Colors.GREEN}{Colors.BOLD}🤖 AGENT ({agent}):{Colors.ENDC}")

    def print_token(self, token: str):
        """Print a streaming token without newline"""
        sys.stdout.write(f"{Colors.GREEN}{token}{Colors.ENDC}")
        sys.stdout.flush()

    def print_agent_complete(self):
        print()  # Newline after streaming
        print(f"{Colors.DIM}--- Agent finished ---{Colors.ENDC}")

    def prompt_continue(self) -> bool:
        """Prompt user to continue or stop"""
        if self.auto_mode:
            return True
        print()
        response = input(f"{Colors.YELLOW}Continue? [Y/n]: {Colors.ENDC}").strip().lower()
        return response in ["", "y", "yes"]

    def prompt_message(self) -> str | None:
        """Prompt user for a message or exit"""
        print()
        message = input(f"{Colors.CYAN}Your message (or 'quit' to exit): {Colors.ENDC}").strip()
        if message.lower() in ["quit", "exit", "q"]:
            return None
        return message

    def setup(self) -> bool:
        """Setup: register, login, create conversation"""
        self.print_header("SETUP")

        # Health check
        try:
            resp = self.client.get(f"{BASE_URL}/health")
            if resp.status_code != 200:
                self.print_error("API not healthy")
                return False
            self.print_success("API is healthy")
        except Exception as e:
            self.print_error(f"Cannot reach API: {e}")
            return False

        # Register
        resp = self.client.post(f"{API_V1}/auth/register", json={"email": self.email, "password": self.password})
        if resp.status_code == 201:
            self.user_id = resp.json().get("id")
            self.print_success(f"Registered: {self.email}")
        elif resp.status_code == 400:
            self.print_info("User already exists")
        else:
            self.print_error(f"Register failed: {resp.status_code}")
            return False

        # Login
        resp = self.client.post(f"{API_V1}/auth/login", data={"username": self.email, "password": self.password})
        if resp.status_code != 200:
            self.print_error(f"Login failed: {resp.status_code}")
            return False
        self.token = resp.json().get("access_token")
        self.print_success("Logged in")

        return True

    def create_conversation(self, title: str = "Interactive Test", legal_area: str = "Mietrecht") -> bool:
        """Create a new conversation"""
        resp = self.client.post(
            f"{API_V1}/conversations",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"title": title, "legal_area": legal_area},
        )
        if resp.status_code != 201:
            self.print_error(f"Create conversation failed: {resp.status_code}")
            return False
        self.conversation_id = resp.json().get("id")
        self.print_success(f"Created conversation: {self.conversation_id}")
        return True

    async def send_message_streaming(self, message: str) -> str:
        """Send a message and stream the response"""
        ws_url = f"{WS_URL}/ws/chat/{self.conversation_id}?token={self.token}"

        full_response = ""
        current_agent = None

        try:
            async with websockets.connect(ws_url, close_timeout=10) as ws:
                # Send user message
                self.print_user_message(message)
                await ws.send(json.dumps({"type": "message", "content": message}))

                # Receive streaming response
                while True:
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=60.0)
                        data = json.loads(response)
                        msg_type = data.get("type")

                        if msg_type == "agent_start":
                            agent = data.get("agent", "unknown")
                            if agent != current_agent:
                                current_agent = agent
                                self.print_agent_start(agent)

                        elif msg_type in ["agent_handoff", "agent_handoff_done"]:
                            # Handoff to new agent
                            agent = data.get("agent_name") or data.get("to_agent", "unknown")
                            if agent != current_agent:
                                current_agent = agent
                                self.print_agent_start(agent)

                        elif msg_type == "message_chunk":
                            # Streaming token from server
                            token = data.get("content", "")
                            full_response += token
                            self.print_token(token)

                        elif msg_type in ["agent_complete", "message_complete", "conversation.response.done"]:
                            self.print_agent_complete()
                            break

                        elif msg_type == "error":
                            self.print_error(f"Agent error: {data.get('error')}")
                            break

                    except asyncio.TimeoutError:
                        self.print_info("Response timeout (60s)")
                        break

        except websockets.exceptions.InvalidStatusCode as e:
            self.print_error(f"WebSocket rejected: HTTP {e.status_code}")
        except Exception as e:
            self.print_error(f"WebSocket error: {e}")

        return full_response

    async def run_scenario(self, scenario_name: str):
        """Run a predefined scenario"""
        if scenario_name not in SCENARIOS:
            self.print_error(f"Unknown scenario: {scenario_name}")
            print(f"Available: {', '.join(SCENARIOS.keys())}")
            return

        scenario = SCENARIOS[scenario_name]
        self.print_header(f"SCENARIO: {scenario['title']}")

        title = str(scenario["title"])
        legal_area = str(scenario.get("legal_area", "Mietrecht"))
        if not self.create_conversation(title, legal_area):
            return

        print(f"\n{Colors.YELLOW}This scenario has {len(scenario['messages'])} messages.{Colors.ENDC}")

        for i, message in enumerate(scenario["messages"], 1):
            print(f"\n{Colors.BOLD}--- Message {i}/{len(scenario['messages'])} ---{Colors.ENDC}")

            await self.send_message_streaming(message)

            if i < len(scenario["messages"]):
                if not self.prompt_continue():
                    self.print_info("Stopped by user")
                    break

        self.print_success("Scenario completed!")

    async def run_interactive(self):
        """Run in fully interactive mode"""
        self.print_header("INTERACTIVE CHAT MODE")

        if not self.create_conversation("Interactive Session"):
            return

        print(f"\n{Colors.YELLOW}Type your messages to chat with the legal AI.{Colors.ENDC}")
        print(f"{Colors.YELLOW}Type 'quit' to exit.{Colors.ENDC}")

        while True:
            message = self.prompt_message()
            if message is None:
                break
            if not message:
                continue

            await self.send_message_streaming(message)

        self.print_success("Chat session ended")

    def cleanup(self):
        """Delete test data"""
        if self.conversation_id and self.token:
            self.client.delete(
                f"{API_V1}/conversations/{self.conversation_id}", headers={"Authorization": f"Bearer {self.token}"}
            )
            self.print_info("Cleaned up test conversation")


async def main():
    parser = argparse.ArgumentParser(description="Interactive Chat Test for Sumii Mobile API")
    parser.add_argument("--scenario", "-s", choices=list(SCENARIOS.keys()), help="Run a predefined scenario")
    parser.add_argument("--auto", "-a", action="store_true", help="Auto-run without prompts (for CI)")
    parser.add_argument("--no-cleanup", action="store_true", help="Don't delete test conversation after")
    args = parser.parse_args()

    tester = InteractiveChatTest(auto_mode=args.auto)

    try:
        if not tester.setup():
            sys.exit(1)

        if args.scenario:
            await tester.run_scenario(args.scenario)
        else:
            await tester.run_interactive()

    finally:
        if not args.no_cleanup:
            tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
