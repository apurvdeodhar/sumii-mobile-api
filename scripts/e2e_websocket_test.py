#!/usr/bin/env python3
"""E2E WebSocket test — simulates mobile app conversation flow.

Tests all 3 bug fixes through localhost:8000:
  1. WrapUp agent should NOT ask DOB/occupation for rental disputes
  2. FactCompletion agent should prompt document upload when user confirms having one
  3. Multi-turn conversations should not get stuck (error 3000)

Usage:
    cd sumii-mobile-api
    .venv/bin/python scripts/e2e_websocket_test.py

Requires: docker-compose up (localhost:8000 running)
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

import httpx
import websockets

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

# Test credentials
EMAIL = "deodharapurv+emailtest@gmail.com"
PASSWORD = "TestPassword123!"  # noqa: S105

# Conversation messages — realistic German rental law case
MESSAGES = [
    # Turn 1: Initial complaint (triggers router → intake)
    "Hallo, meine Heizung ist seit 3 Wochen kaputt und mein Vermieter reagiert nicht auf meine Nachrichten.",
    # Turn 2-6: Answers to intake/fact_completion questions (sent dynamically based on agent questions)
]

# Pre-scripted answers for common follow-up topics
# Ordered list of (keywords, answer) — first match wins.
# Order matters: more specific patterns before generic ones.
SCRIPTED_ANSWERS: list[tuple[list[str], str]] = [
    (["adresse", "immobilie", "wohnung", "straße", "plz"], "Musterstraße 42, 10115 Berlin."),
    (["wann", "datum", "zeitpunkt", "seit wann"], "Am 1. Februar 2026. Vermieter am 2. Februar per E-Mail informiert."),
    (["vermieter", "name des"], "Hans Mueller, E-Mail: mueller@example.de"),
    (["kontakt", "kommunikation", "geschrieben", "gemeldet"], "Per E-Mail am 2. und 10. Februar. Keine Antwort."),
    (["dokument", "unterlagen", "schriftlich", "nachweis", "vertrag", "kopie", "beleg"], "__DOCUMENT__"),
    (["auswirkung", "betroffen", "gesundheit", "alltag"], "Temperatur unter 16 Grad, ich bin erkältet geworden."),
    (["ziel", "erreichen", "ergebnis", "lösung"], "Heizung reparieren und Mietminderung für 3 Wochen."),
    (["dringend", "frist", "eilig", "deadline"], "Sehr dringend, es ist Winter und unter Null Grad."),
    (["versicherung", "rechtsschutz"], "Nein, keine Rechtsschutzversicherung."),
    (["bestätig", "stimmt", "korrekt", "richtig", "zusammenfassung"], "Ja, das stimmt alles so."),
    (["finanziell", "geld", "kosten", "betrag"], "Keine zusätzlichen Kosten bisher, aber Mietminderung gewünscht."),
]

# Document answer — triggers Bug 2 check
DOCUMENT_ANSWER = "Ja, ich habe den Mietvertrag als PDF und die E-Mails als Screenshots."

# Generic fallback
FALLBACK_ANSWER = "Die Adresse ist Musterstraße 42, 10115 Berlin. Ich möchte Mietminderung."


class TestResults:
    """Track pass/fail for each bug fix."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.turns: int = 0
        self.agents_seen: list[str] = []
        self.all_responses: list[str] = []
        self.bug1_pass: bool | None = None  # No DOB/occupation asked
        self.bug2_pass: bool | None = None  # Upload prompt when user has document
        self.bug3_pass: bool = True  # No error 3000 (starts True, set False on error)
        self.document_mention_turn: int | None = None
        self.last_answer: str = ""

    def check_bug1(self, response: str) -> None:
        """Check if response asks about DOB or occupation (should NOT for rental).

        Uses question-like patterns to avoid false positives from words like
        'bearbeiten' or 'Arbeitgeber' appearing in other contexts.
        """
        # Patterns that indicate the agent is ASKING about DOB/occupation
        dob_patterns = ["geburtsdatum", "geburtstag", "wann bist du geboren", "date of birth"]
        occupation_patterns = [
            "was ist dein beruf",
            "welchen beruf",
            "was arbeitest du",
            "deine tätigkeit",
            "your occupation",
            "beruflich tätig",
        ]
        lower = response.lower()
        for pattern in dob_patterns + occupation_patterns:
            if pattern in lower:
                self.bug1_pass = False
                self.errors.append(f"BUG 1 FAIL: Agent asked about '{pattern}' in rental dispute")
                return
        # Only set to True if we haven't already failed
        if self.bug1_pass is None:
            self.bug1_pass = True

    def check_bug2(self, response: str) -> None:
        """Check if agent prompts document upload with + Symbol.

        Two scenarios trigger a pass:
        1. User confirms having a document → agent responds with upload prompt
        2. Agent proactively asks about documents AND includes upload instructions
        """
        if self.bug2_pass is True:
            return  # Already passed

        lower = response.lower()
        upload_keywords = ["+ symbol", "hochlad", "upload", "lade das dokument", "bitte lade"]
        has_upload_prompt = any(kw in lower for kw in upload_keywords)

        # Proactive upload prompt (agent mentions + Symbol without user prompting)
        if has_upload_prompt:
            self.bug2_pass = True
            return

        # Check after user explicitly mentioned having documents
        if (
            self.document_mention_turn is not None
            and self.bug2_pass is None
            and self.turns == self.document_mention_turn + 1
            and not has_upload_prompt
        ):
            self.bug2_pass = False
            self.errors.append("BUG 2 FAIL: No upload prompt after user confirmed having document")

    def print_summary(self) -> None:
        """Print test results."""
        print(f"\n{'='*70}")
        print("E2E TEST RESULTS")
        print(f"{'='*70}")
        print(f"  Turns completed: {self.turns}")
        print(f"  Agents seen: {', '.join(dict.fromkeys(self.agents_seen))}")
        print()

        def status(val: bool | None) -> str:
            if val is None:
                return "SKIP (not reached)"
            return "PASS" if val else "FAIL"

        print(f"  Bug 1 (No DOB/occupation in rental): {status(self.bug1_pass)}")
        print(f"  Bug 2 (Upload prompt on document):   {status(self.bug2_pass)}")
        print(f"  Bug 3 (No error 3000 stuck):         {status(self.bug3_pass)}")
        print()

        if self.errors:
            print("  ERRORS:")
            for err in self.errors:
                print(f"    - {err}")
        else:
            all_tested = all(v is not None for v in [self.bug1_pass, self.bug2_pass])
            if all_tested:
                print("  ALL TESTS PASSED")
            else:
                print("  Some tests were not reached (conversation may need more turns)")
        print(f"{'='*70}")


def pick_answer(agent_question: str, turn: int, results: TestResults) -> str:
    """Pick a contextual answer based on what the agent asked."""
    lower = agent_question.lower()

    # Match by keyword patterns (first match wins)
    for keywords, answer in SCRIPTED_ANSWERS:
        if any(kw in lower for kw in keywords):
            # Special handling for document answer — triggers Bug 2 check
            if answer == "__DOCUMENT__":
                if results.document_mention_turn is None:
                    results.document_mention_turn = turn
                chosen = DOCUMENT_ANSWER
            else:
                chosen = answer
            # Avoid repeating the same answer (causes loops)
            if chosen == results.last_answer:
                continue
            results.last_answer = chosen
            return chosen

    results.last_answer = FALLBACK_ANSWER
    return FALLBACK_ANSWER


async def login() -> str:
    """Login and return JWT token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": EMAIL, "password": PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            print(f"Login failed: {resp.status_code} {resp.text}")
            sys.exit(1)
        token: str = resp.json()["access_token"]
        print(f"  Logged in as {EMAIL} (token: {token[:20]}...)")
        return token


async def create_conversation(token: str) -> str:
    """Create a new conversation and return its ID."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/conversations",
            json={"title": "E2E Test - Heizungsausfall"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 201:
            print(f"Create conversation failed: {resp.status_code} {resp.text}")
            sys.exit(1)
        conv_id: str = resp.json()["id"]
        print(f"  Created conversation: {conv_id}")
        return conv_id


async def send_and_receive(
    ws: websockets.ClientConnection,
    message: str,
    turn: int,
    results: TestResults,
    timeout: int = 120,
) -> str:
    """Send a message and wait for message_complete. Returns full response text."""
    print(f"\n{'─'*60}")
    print(f"  TURN {turn}: {message[:80]}{'...' if len(message) > 80 else ''}")
    print(f"{'─'*60}")

    await ws.send(json.dumps({"type": "message", "content": message}))

    full_text = ""
    agent = "unknown"
    t0 = time.monotonic()

    while True:
        remaining = timeout - (time.monotonic() - t0)
        if remaining <= 0:
            results.errors.append(f"Turn {turn}: Timeout after {timeout}s")
            results.bug3_pass = False
            return full_text

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except TimeoutError:
            results.errors.append(f"Turn {turn}: Timeout waiting for response")
            results.bug3_pass = False
            return full_text

        event: dict[str, Any] = json.loads(raw)
        event_type = event.get("type", "unknown")

        if event_type == "agent_start":
            agent = event.get("agent", "unknown")
            if agent not in results.agents_seen:
                results.agents_seen.append(agent)
            print(f"    [agent_start] {agent}")

        elif event_type == "agent_handoff":
            to_agent = event.get("toAgent", event.get("to_agent", "?"))
            print(f"    [handoff] → {to_agent}")

        elif event_type == "message_chunk":
            # Don't print every chunk — too noisy
            pass

        elif event_type == "message_complete":
            full_text = event.get("content", "")
            agent = event.get("agent", agent)
            msg_id = event.get("message_id", "?")
            print(f"    [message_complete] agent={agent}, {len(full_text)} chars, id={msg_id[:8]}...")
            print(f"    Response: {full_text[:150]}{'...' if len(full_text) > 150 else ''}")
            results.turns += 1
            return full_text

        elif event_type == "thinking_complete":
            error = event.get("data", {}).get("error", False)
            if error:
                print("    [thinking_complete] ERROR=True")

        elif event_type == "error":
            error_msg = event.get("error", event.get("message", "Unknown"))
            error_code = event.get("code", "")
            print(f"    [ERROR] {error_msg} (code={error_code})")
            results.errors.append(f"Turn {turn}: Error from server: {error_msg}")
            if error_code == "conversation_error":
                results.bug3_pass = False
            return full_text

        elif event_type in (
            "thinking_chunk",
            "thinking_preview",
            "function_call",
            "tool_execution",
            "tool_execution_done",
        ):
            # Expected events — don't log verbosely
            pass

        else:
            print(f"    [{event_type}] {json.dumps(event)[:100]}")


async def run_test() -> TestResults:
    """Run the full E2E conversation test."""
    results = TestResults()

    print(f"\n{'='*70}")
    print("E2E WEBSOCKET TEST — Rental Law (Heizungsausfall)")
    print(f"{'='*70}")

    # Step 1: Login
    print("\n[1/3] Authenticating...")
    token = await login()

    # Step 2: Create conversation
    print("\n[2/3] Creating conversation...")
    conv_id = await create_conversation(token)

    # Step 3: WebSocket conversation
    print("\n[3/3] Starting WebSocket conversation...")
    ws_uri = f"{WS_URL}/ws/chat/{conv_id}?token={token}"

    max_turns = 8

    async with websockets.connect(ws_uri, close_timeout=5) as ws:
        # Turn 1: Initial message
        response = await send_and_receive(ws, MESSAGES[0], 1, results)
        results.all_responses.append(response)
        results.check_bug1(response)

        # Turns 2+: Dynamic responses based on agent questions
        for turn in range(2, max_turns + 1):
            if not response:
                print(f"\n  No response on turn {turn - 1}, stopping.")
                break

            answer = pick_answer(response, turn, results)
            response = await send_and_receive(ws, answer, turn, results)
            results.all_responses.append(response)
            results.check_bug1(response)
            results.check_bug2(response)

            # If we've tested both bugs, we can stop early
            if results.bug1_pass is not None and results.bug2_pass is not None:
                if turn >= 5:  # Minimum 5 turns for confidence
                    print("\n  Both bug checks completed, stopping.")
                    break

    return results


def main() -> None:
    """Entry point."""
    # Quick health check
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=5)
        if resp.status_code != 200:
            print(f"Health check failed: {resp.status_code}")
            sys.exit(1)
    except httpx.ConnectError:
        print(f"Cannot connect to {BASE_URL} — is docker-compose up?")
        sys.exit(1)

    print("Health check: OK")

    results = asyncio.run(run_test())
    results.print_summary()

    # Exit code: 0 if all tested bugs passed, 1 otherwise
    if results.errors or any(v is False for v in [results.bug1_pass, results.bug2_pass, results.bug3_pass]):
        sys.exit(1)


if __name__ == "__main__":
    main()
