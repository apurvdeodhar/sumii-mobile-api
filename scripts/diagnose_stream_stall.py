#!/usr/bin/env python3
"""Diagnostic: Reproduce error 3000 and test restart_stream recovery.

Phase 1: Build a multi-turn conversation until a function call occurs
Phase 2: Deliberately skip the function result → poison the conversation
Phase 3: Confirm error 3000 on next message (prove the conversation is stuck)
Phase 4: Use get_history + restart_stream to fork past the poisoned state
Phase 5: Send a message on the recovered conversation → prove it works

Usage:
    cd sumii-mobile-api
    .venv/bin/python scripts/diagnose_stream_stall.py

Requires: MISTRAL_API_KEY in .env (Sumii Local Dev workspace)
"""

import os
import sys
import time
from datetime import datetime
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from mistralai import Mistral  # noqa: E402
from mistralai.models import (  # noqa: E402
    AgentHandoffDoneEvent,
    FunctionCallEvent,
    MessageOutputEvent,
    ResponseDoneEvent,
    ResponseErrorEvent,
    ResponseStartedEvent,
)

API_KEY = os.getenv("MISTRAL_API_KEY")
if not API_KEY:
    print("ERROR: MISTRAL_API_KEY not found in .env")
    sys.exit(1)


def get_client() -> Mistral:
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
    return Mistral(api_key=API_KEY, client=httpx.Client(timeout=timeout))


def find_router_agent(client: Mistral) -> str | None:
    """Find the Router Agent ID from the Mistral workspace."""
    try:
        agents = client.beta.agents.list()
        agent_list = agents.data if hasattr(agents, "data") else agents
        if agent_list:
            for agent in agent_list:
                name = agent.name if hasattr(agent, "name") else agent.get("name", "")
                aid = agent.id if hasattr(agent, "id") else agent.get("id")
                if name and "router" in name.lower():
                    return aid
    except Exception as e:
        print(f"Warning: SDK list failed: {e}")
    return None


def stream_message(
    client: Mistral,
    conv_id: str | None,
    agent_id: str,
    message: str,
    label: str,
    consume_fully_but_skip_function_result: bool = False,
) -> dict[str, Any]:
    """Send a message and consume the stream.

    If consume_fully_but_skip_function_result=True: consumes the ENTIRE stream
    (including DONE), records function calls, but the caller should NOT send
    function results back. This simulates what happens when our production code
    receives a complete stream with function calls but fails to send results
    (e.g., due to a timeout in the continuation loop or a crash).

    Returns dict with: conv_id, text, error_code, error_msg, had_function_call, function_calls, event_count
    """
    print(f"\n{'='*70}")
    print(f"[{label}] Sending ({len(message)} chars): {message[:80]}...")
    if consume_fully_but_skip_function_result:
        print("  MODE: Consume full stream but DO NOT send function results back")
    print(f"{'='*70}")

    current_conv_id: str | None = conv_id
    event_count: int = 0
    error_code: int | None = None
    error_msg: str | None = None
    had_function_call: bool = False
    function_calls: list[dict[str, str]] = []
    text_parts: list[str] = []

    try:
        if conv_id:
            stream = client.beta.conversations.append_stream(
                conversation_id=conv_id,
                inputs=[{"role": "user", "content": message}],
            )
        else:
            stream = client.beta.conversations.start_stream(
                agent_id=agent_id,
                inputs=[{"role": "user", "content": message}],
            )

        t0 = time.monotonic()

        with stream as s:
            for event in s:
                event_count += 1
                n = event_count

                # Capture conv_id from first event
                if current_conv_id is None and hasattr(event.data, "conversation_id"):
                    current_conv_id = event.data.conversation_id

                if isinstance(event.data, ResponseErrorEvent):
                    error_msg = getattr(event.data, "message", "Unknown")
                    error_code = getattr(event.data, "code", None)
                    print(f"  #{n:3d} | ERROR: {error_msg} (code={error_code})")
                    break

                elif isinstance(event.data, ResponseDoneEvent):
                    dt = round((time.monotonic() - t0) * 1000)
                    print(f"  #{n:3d} | DONE ({dt}ms total)")

                elif isinstance(event.data, AgentHandoffDoneEvent):
                    next_agent = getattr(event.data, "next_agent_name", "?")
                    print(f"  #{n:3d} | HANDOFF -> {next_agent}")

                elif isinstance(event.data, FunctionCallEvent):
                    fn_name = getattr(event.data, "function_name", "?")
                    tool_call_id = getattr(event.data, "tool_call_id", "?")
                    had_function_call = True
                    # Only log first chunk per function call
                    if not any(fc["tool_call_id"] == tool_call_id for fc in function_calls):
                        function_calls.append({"tool_call_id": tool_call_id, "function_name": fn_name})
                        print(f"  #{n:3d} | FUNCTION_CALL: {fn_name} (id={tool_call_id[:16]}...)")

                elif isinstance(event.data, MessageOutputEvent):
                    content = getattr(event.data, "content", "")
                    if isinstance(content, str):
                        text_parts.append(content)
                    elif isinstance(content, list):
                        for chunk in content:
                            if hasattr(chunk, "text"):
                                text_parts.append(chunk.text)
                    if n <= 3 or n % 20 == 0:
                        print(f"  #{n:3d} | TEXT ({len(''.join(text_parts))} chars)")

                elif isinstance(event.data, ResponseStartedEvent):
                    print(f"  #{n:3d} | STREAM STARTED")

        full_text = "".join(text_parts)
        dt = round((time.monotonic() - t0) * 1000)

        if consume_fully_but_skip_function_result and had_function_call:
            print(f"\n  Stream fully consumed: {event_count} events, {len(full_text)} chars, {dt}ms")
            print(f"  >>> Function call(s) received: {[fc['function_name'] for fc in function_calls]}")
            print("  >>> DELIBERATELY NOT sending function result(s) back to Mistral <<<")
            print("  >>> Conversation should now be in poisoned state <<<")
        else:
            print(f"\n  Result: {event_count} events, {len(full_text)} chars, {dt}ms")

    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")
        error_msg = str(e)
        full_text = "".join(text_parts)

    return {
        "conv_id": current_conv_id,
        "text": full_text,
        "error_code": error_code,
        "error_msg": error_msg,
        "had_function_call": had_function_call,
        "function_calls": function_calls,
        "event_count": event_count,
    }


def inspect_history(client: Mistral, conv_id: str) -> list:
    """Fetch and display conversation history entries."""
    print(f"\n{'─'*70}")
    print(f"[HISTORY] Fetching history for {conv_id}")
    print(f"{'─'*70}")

    try:
        history = client.beta.conversations.get_history(conversation_id=conv_id)
        entries = history.entries if hasattr(history, "entries") else history
        if not entries:
            print("  (no entries)")
            return []

        print(f"  Total entries: {len(entries)}\n")
        for i, entry in enumerate(entries):
            entry_type = getattr(entry, "type", "?")
            entry_id = getattr(entry, "id", "?")
            completed = getattr(entry, "completed_at", None)
            status = "COMPLETE" if completed else "INCOMPLETE"

            # Truncated content preview
            content = getattr(entry, "content", None)
            preview = ""
            if content:
                if isinstance(content, str):
                    preview = content[:60]
                elif isinstance(content, list):
                    texts = [getattr(c, "text", str(c))[:30] for c in content[:2]]
                    preview = " | ".join(texts)

            # Special fields
            extra = ""
            if entry_type == "function.call":
                fn_name = getattr(entry, "name", "?")
                extra = f" fn={fn_name}"
            elif entry_type == "function.result":
                extra = " (result)"
            elif entry_type == "agent.handoff":
                next_agent = getattr(entry, "agent_name", "?")
                extra = f" -> {next_agent}"

            print(f"  [{i:2d}] {entry_type:20s} | {status:10s} | id={str(entry_id)[:20]}...{extra}")
            if preview:
                print(f"       preview: {preview}")

        return list(entries)
    except Exception as e:
        print(f"  ERROR fetching history: {e}")
        return []


def find_last_user_message_entry(entries: list) -> str | None:
    """Find the entry ID of the last user message (message.input)."""
    for entry in reversed(entries):
        if getattr(entry, "type", "") == "message.input":
            return getattr(entry, "id", None)
    return None


def find_entry_before_poison(entries: list) -> str | None:
    """Find a safe entry ID to restart from.

    Strategy: find the last message.input entry (user message) — this is always
    a safe point to fork from since user messages don't have pending state.
    We skip the very last entry in case it's the poisoned one.
    """
    # Find second-to-last message.input (the last "clean" user message)
    user_entries = []
    for entry in entries:
        if getattr(entry, "type", "") == "message.input":
            user_entries.append(entry)

    # Return the second-to-last user message (last one before the poison)
    if len(user_entries) >= 2:
        return getattr(user_entries[-2], "id", None)
    elif user_entries:
        return getattr(user_entries[0], "id", None)
    return None


def attempt_restart_stream(client: Mistral, conv_id: str, from_entry_id: str, message: str) -> dict[str, Any]:
    """Try restart_stream to fork past poisoned state."""
    print(f"\n{'='*70}")
    print(f"[RESTART_STREAM] Forking from entry {from_entry_id[:20]}...")
    print(f"  Original conv: {conv_id}")
    print(f"  Message: {message[:80]}...")
    print(f"{'='*70}")

    new_conv_id: str | None = None
    event_count: int = 0
    error_code: int | None = None
    error_msg: str | None = None
    text_parts: list[str] = []

    try:
        stream = client.beta.conversations.restart_stream(
            conversation_id=conv_id,
            from_entry_id=from_entry_id,
            inputs=[{"role": "user", "content": message}],
        )

        t0 = time.monotonic()

        with stream as s:
            for event in s:
                event_count += 1
                n = event_count

                # Capture NEW conv_id
                if new_conv_id is None and hasattr(event.data, "conversation_id"):
                    new_conv_id = event.data.conversation_id
                    print(f"  #{n:3d} | NEW CONV: {new_conv_id}")

                if isinstance(event.data, ResponseErrorEvent):
                    error_msg = getattr(event.data, "message", "Unknown")
                    error_code = getattr(event.data, "code", None)
                    print(f"  #{n:3d} | ERROR: {error_msg} (code={error_code})")
                    break

                elif isinstance(event.data, ResponseDoneEvent):
                    dt = round((time.monotonic() - t0) * 1000)
                    print(f"  #{n:3d} | DONE ({dt}ms)")

                elif isinstance(event.data, AgentHandoffDoneEvent):
                    next_agent = getattr(event.data, "next_agent_name", "?")
                    print(f"  #{n:3d} | HANDOFF -> {next_agent}")

                elif isinstance(event.data, FunctionCallEvent):
                    fn_name = getattr(event.data, "function_name", "?")
                    print(f"  #{n:3d} | FUNCTION_CALL: {fn_name}")

                elif isinstance(event.data, MessageOutputEvent):
                    content = getattr(event.data, "content", "")
                    if isinstance(content, str):
                        text_parts.append(content)
                    elif isinstance(content, list):
                        for chunk in content:
                            if hasattr(chunk, "text"):
                                text_parts.append(chunk.text)
                    if n <= 3 or n % 20 == 0:
                        print(f"  #{n:3d} | TEXT ({len(''.join(text_parts))} chars)")

                elif isinstance(event.data, ResponseStartedEvent):
                    print(f"  #{n:3d} | STREAM STARTED")

        full_text = "".join(text_parts)
        dt = round((time.monotonic() - t0) * 1000)
        print(f"\n  Result: {event_count} events, {len(full_text)} chars, {dt}ms")

    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")
        error_msg = str(e)
        full_text = "".join(text_parts)

    return {
        "new_conv_id": new_conv_id,
        "text": full_text,
        "error_code": error_code,
        "error_msg": error_msg,
        "event_count": event_count,
    }


def main():
    print("=" * 70)
    print("Mistral Error 3000 Reproduction & restart_stream Recovery Test")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 70)

    client = get_client()

    # Find Router Agent
    print("\nFinding Router Agent...")
    agent_id = find_router_agent(client)
    if not agent_id:
        print("ERROR: Could not find Router Agent. Is docker-compose up?")
        sys.exit(1)
    print(f"Found: {agent_id}")

    # ─── PHASE 1: Build conversation until function call ─────────────────
    print(f"\n\n{'#'*70}")
    print("PHASE 1: Build conversation until agent triggers a function call")
    print(f"{'#'*70}")

    # Normal conversation turns (consume fully, send results if needed)
    normal_messages = [
        "Hallo, ich habe ein Problem mit meinem Vermieter.",
        "Er hat die Nebenkosten falsch abgerechnet. Die Abrechnung ist viel zu hoch.",
        "Ich wohne seit 3 Jahren in der Wohnung. Mein Vermieter heisst Hans Mueller.",
        "Die Abrechnung kam am 15. Januar 2026. Ich habe am 20. Januar widersprochen.",
        "Ja, ich habe den Widerspruch per Email geschickt. Er hat nicht geantwortet.",
        "Die Nachzahlung betraegt 1200 Euro. Das ist viel zu viel, normalerweise zahle ich 150 Euro.",
    ]

    # This message typically triggers extract_facts function call
    poison_message = "Ich moechte die Korrektur der Nebenkostenabrechnung und die Rueckzahlung."

    conv_id = None
    poisoned = False

    # Step A: Normal turns — consume fully (function calls get generic results via handoff_execution=server)
    for i, msg in enumerate(normal_messages, 1):
        res = stream_message(
            client,
            conv_id,
            agent_id,
            msg,
            f"Phase1 Turn {i}/{len(normal_messages)}",
        )
        conv_id = res["conv_id"]

        if res["error_code"]:
            print(f"\n  Unexpected error at turn {i}: {res['error_msg']}")
            break
        time.sleep(0.5)

    # Step B: Poison turn — consume the ENTIRE stream (including DONE) but DO NOT
    # send function results back. This is what happens in production when:
    # - Stream completes with function call events
    # - But continuation loop fails/crashes/times out before sending results
    print("\n  >>> Now sending poison message — will consume full stream but skip function results <<<")
    res = stream_message(
        client,
        conv_id,
        agent_id,
        poison_message,
        f"Phase1 POISON Turn {len(normal_messages) + 1}",
        consume_fully_but_skip_function_result=True,
    )
    conv_id = res["conv_id"]

    if res["had_function_call"]:
        poisoned = True
    else:
        print("\n  No function call in poison turn — conversation may not be poisoned.")
        print("  Agent responded with text instead. Continuing to check...")
        # Try one more message that might trigger a function call
        extra_msg = (
            "Ich habe einen Mietvertrag seit April 2023, die Abrechnung fuer 2025 war 1200 Euro, "
            "normalerweise zahle ich 150 Euro. Ich will die Korrektur und Rueckzahlung."
        )
        res = stream_message(
            client,
            conv_id,
            agent_id,
            extra_msg,
            "Phase1 EXTRA POISON attempt",
            consume_fully_but_skip_function_result=True,
        )
        conv_id = res["conv_id"]
        if res["had_function_call"]:
            poisoned = True
        else:
            print("\n  WARNING: Could not trigger a function call.")
            print("  This is non-deterministic — try running the script again.")

    # ─── PHASE 2: Confirm error 3000 ────────────────────────────────────
    print(f"\n\n{'#'*70}")
    print("PHASE 2: Confirm conversation is stuck (expect error 3000)")
    print(f"{'#'*70}")

    test_msg = "Ja, ich habe auch die alten Abrechnungen als PDF vorliegen."
    res2 = stream_message(client, conv_id, agent_id, test_msg, "Phase2 — Error 3000 test")

    if res2["error_code"] == 3000:
        print("\n  CONFIRMED: Error 3000 — conversation is stuck!")
        print(f"  Error message: {res2['error_msg']}")
    elif res2["error_code"]:
        print(f"\n  Got error {res2['error_code']}: {res2['error_msg']}")
        print("  (Expected 3000, got different error)")
    else:
        print(f"\n  UNEXPECTED: No error! Response: {res2['text'][:100]}")
        print("  The conversation might not be poisoned. Continuing anyway...")

    # ─── PHASE 3: Inspect history to find recovery point ────────────────
    print(f"\n\n{'#'*70}")
    print("PHASE 3: Inspect conversation history to find fork point")
    print(f"{'#'*70}")

    entries = inspect_history(client, conv_id)

    if not entries:
        print("\n  Cannot proceed — no history entries found.")
        sys.exit(1)

    # Find the right entry to fork from
    fork_entry_id = find_entry_before_poison(entries)
    last_user_entry_id = find_last_user_message_entry(entries)

    print(f"\n  Last user message entry: {str(last_user_entry_id)[:20]}...")
    print(f"  Last safe entry (for fork): {str(fork_entry_id)[:20]}...")

    if not fork_entry_id:
        print("\n  ERROR: Could not find a safe entry to fork from.")
        sys.exit(1)

    # ─── PHASE 4: restart_stream recovery ───────────────────────────────
    print(f"\n\n{'#'*70}")
    print("PHASE 4: Attempt recovery via restart_stream")
    print(f"{'#'*70}")

    recovery_msg = (
        "Ich moechte die Korrektur der Nebenkostenabrechnung und die Rueckzahlung des zu viel gezahlten Betrags."
    )
    res3 = attempt_restart_stream(client, conv_id, fork_entry_id, recovery_msg)

    if res3["error_code"]:
        print(f"\n  RECOVERY FAILED: Error {res3['error_code']}: {res3['error_msg']}")

        # Try forking from the last user message instead
        if last_user_entry_id and last_user_entry_id != fork_entry_id:
            print("\n  Trying alternative fork point: last user message entry...")
            res3 = attempt_restart_stream(client, conv_id, last_user_entry_id, recovery_msg)
            if res3["error_code"]:
                print(f"\n  ALTERNATIVE ALSO FAILED: {res3['error_code']}: {res3['error_msg']}")
            else:
                print("\n  ALTERNATIVE RECOVERY SUCCEEDED!")
    else:
        print("\n  RECOVERY SUCCEEDED!")

    new_conv_id = res3.get("new_conv_id")

    # ─── PHASE 5: Verify recovered conversation works ───────────────────
    if new_conv_id and not res3["error_code"]:
        print(f"\n\n{'#'*70}")
        print("PHASE 5: Verify recovered conversation accepts new messages")
        print(f"{'#'*70}")

        verify_msg = "Ich habe keine Rechtsschutzversicherung."
        res4 = stream_message(client, new_conv_id, agent_id, verify_msg, "Phase5 — Verify")

        if res4["error_code"]:
            print(f"\n  VERIFICATION FAILED: {res4['error_code']}: {res4['error_msg']}")
        else:
            print("\n  VERIFICATION PASSED: Recovered conversation works!")
            print(f"  Response: {res4['text'][:150]}...")

    # ─── FINAL REPORT ───────────────────────────────────────────────────
    print(f"\n\n{'='*70}")
    print("FINAL REPORT")
    print(f"{'='*70}")
    print(f"  Original conversation:  {conv_id}")
    print("  Poisoned by:            Incomplete function call (no result sent)")
    print(f"  Error 3000 confirmed:   {'YES' if res2.get('error_code') == 3000 else 'NO'}")
    print(f"  Fork entry ID:          {str(fork_entry_id)[:30]}...")
    print(f"  restart_stream result:  {'SUCCESS' if new_conv_id and not res3.get('error_code') else 'FAILED'}")
    if new_conv_id:
        print(f"  New conversation:       {new_conv_id}")
    verify_passed = "res4" in locals() and not res4.get("error_code")  # noqa: F821
    print("  Post-recovery verify:   ", end="")
    if new_conv_id and not res3.get("error_code"):
        if verify_passed:
            print("PASSED — conversation fully recovered")
        else:
            print("NOT TESTED or FAILED")
    else:
        print("SKIPPED — recovery failed")

    print("\n  CONCLUSION:")
    if new_conv_id and not res3.get("error_code"):
        print("  restart_stream CAN recover from error 3000!")
        print("  Implementation plan: On error 3000, call get_history to find")
        print("  the last safe entry, then restart_stream to fork the conversation.")
        print("  The new conversation_id replaces the poisoned one.")
    else:
        print("  restart_stream did NOT recover. Need alternative approach.")


if __name__ == "__main__":
    main()
