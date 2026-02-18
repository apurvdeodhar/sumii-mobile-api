"""
Verify Mistral Conversations API streaming events.

Tests the claims from p1-task10-research.md:
1. Every MessageOutputEvent carries agent_id
2. AgentHandoffDoneEvent fires between agent streams
3. output_index increments per agent block
4. content_index tracks sections within an agent
5. First agent (Router) has no preceding handoff event

Run: export $(grep -E '^MISTRAL_API_KEY=' .env | xargs) && .venv/bin/python tests/manual/test_stream_events.py
"""

import os
from datetime import datetime

from mistralai import (
    AgentHandoffDoneEvent,
    FunctionCallEvent,
    MessageOutputEvent,
    Mistral,
    ResponseDoneEvent,
    ResponseErrorEvent,
    ToolExecutionDoneEvent,
    ToolExecutionStartedEvent,
)

ROUTER_AGENT_ID = "ag_019c3d0b677b704d83be5c3fd9bfae6c"


def main():
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("ERROR: MISTRAL_API_KEY not set")
        return

    client = Mistral(api_key=api_key)

    print("=" * 70)
    print("STREAM EVENT VERIFICATION TEST")
    print("=" * 70)
    print(f"Router Agent: {ROUTER_AGENT_ID}")
    print(f"Time: {datetime.now().isoformat()}")
    print()

    # Track all events
    events_log = []
    agent_id_seen = {}  # agent_id -> count of chunks
    handoff_sequence = []
    output_indices = set()
    content_indices = set()
    first_delta_agent_id = None
    first_delta_had_handoff_before = False
    agent_id_null_count = 0
    agent_id_set_count = 0

    print("Starting stream with message: 'Ich habe ein Problem mit meinem Vermieter'")
    print("-" * 70)

    try:
        response = client.beta.conversations.start_stream(
            agent_id=ROUTER_AGENT_ID,
            inputs=(
                "Ich habe ein Problem mit meinem Vermieter. Er hat meine Kaution von 2000 Euro "
                "nicht zurückgezahlt nach dem Auszug am 1. Januar 2026. Mein Name ist Max Mustermann, "
                "ich wohnte in der Berliner Straße 42, München."
            ),
            store=False,  # Don't persist this test conversation
        )

        with response as stream:
            event_count = 0
            for raw_event in stream:
                event_count += 1
                # Unwrap ConversationEvents wrapper
                event = getattr(raw_event, "data", raw_event)
                event_type = type(event).__name__

                if isinstance(event, MessageOutputEvent):
                    agent_id = getattr(event, "agent_id", None)
                    output_idx = getattr(event, "output_index", None)
                    content_idx = getattr(event, "content_index", None)
                    content = event.content

                    # Track first delta
                    if first_delta_agent_id is None:
                        first_delta_agent_id = agent_id
                        first_delta_had_handoff_before = len(handoff_sequence) > 0

                    # Track agent_id population
                    if agent_id is not None:
                        agent_id_set_count += 1
                        agent_id_seen[agent_id] = agent_id_seen.get(agent_id, 0) + 1
                    else:
                        agent_id_null_count += 1

                    # Track indices
                    if output_idx is not None:
                        output_indices.add(output_idx)
                    if content_idx is not None:
                        content_indices.add(content_idx)

                    # Determine content type
                    if isinstance(content, str):
                        content_display = content[:60]
                        content_type = "str"
                    elif isinstance(content, list):
                        content_type = f"list[{len(content)}]"
                        content_display = str([type(c).__name__ for c in content])
                    elif hasattr(content, "thinking"):
                        content_type = "ThinkChunk"
                        content_display = "(thinking traces)"
                    elif hasattr(content, "text"):
                        content_type = "TextChunk"
                        content_display = content.text[:60] if content.text else ""
                    else:
                        content_type = type(content).__name__
                        content_display = str(content)[:60]

                    print(
                        f"  [{event_count:3d}] MessageOutputEvent  agent_id={agent_id}  "
                        f'out_idx={output_idx}  cnt_idx={content_idx}  type={content_type}  content="{content_display}"'
                    )

                    events_log.append(
                        {
                            "type": "message.output.delta",
                            "agent_id": agent_id,
                            "output_index": output_idx,
                            "content_index": content_idx,
                            "content_type": content_type,
                        }
                    )

                elif isinstance(event, AgentHandoffDoneEvent):
                    prev_name = getattr(event, "previous_agent_name", "?")
                    next_name = getattr(event, "next_agent_name", "?")
                    prev_id = getattr(event, "previous_agent_id", "?")
                    next_id = getattr(event, "next_agent_id", "?")

                    handoff_sequence.append(f"{prev_name} -> {next_name}")

                    print(f"  [{event_count:3d}] AgentHandoffDone   {prev_name} ({prev_id}) -> {next_name} ({next_id})")

                    events_log.append(
                        {
                            "type": "agent.handoff.done",
                            "prev": prev_name,
                            "next": next_name,
                            "prev_id": prev_id,
                            "next_id": next_id,
                        }
                    )

                elif isinstance(event, FunctionCallEvent):
                    name = getattr(event, "name", "?")
                    print(f"  [{event_count:3d}] FunctionCallEvent  name={name}")
                    events_log.append({"type": "function_call", "name": name})

                elif isinstance(event, ToolExecutionStartedEvent):
                    name = getattr(event, "name", "?")
                    print(f"  [{event_count:3d}] ToolExecStarted    name={name}")
                    events_log.append({"type": "tool.started", "name": name})

                elif isinstance(event, ToolExecutionDoneEvent):
                    name = getattr(event, "name", "?")
                    print(f"  [{event_count:3d}] ToolExecDone       name={name}")
                    events_log.append({"type": "tool.done", "name": name})

                elif isinstance(event, ResponseDoneEvent):
                    usage = getattr(event, "usage", None)
                    print(f"  [{event_count:3d}] ResponseDone       usage={usage}")
                    events_log.append({"type": "response.done"})

                elif isinstance(event, ResponseErrorEvent):
                    msg = getattr(event, "message", "?")
                    code = getattr(event, "code", "?")
                    print(f"  [{event_count:3d}] ResponseError      code={code}  msg={msg}")
                    events_log.append({"type": "response.error", "code": code, "msg": msg})

                else:
                    print(f"  [{event_count:3d}] {event_type}  (unhandled)")
                    events_log.append({"type": event_type})

    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")

    # ═══════════════════════════════════════════════
    # RESULTS
    # ═══════════════════════════════════════════════
    print()
    print("=" * 70)
    print("VERIFICATION RESULTS")
    print("=" * 70)

    # Test 1: agent_id populated
    total_deltas = agent_id_set_count + agent_id_null_count
    print("\n1. agent_id on MessageOutputEvent:")
    print(f"   Total deltas: {total_deltas}")
    print(f"   With agent_id: {agent_id_set_count}")
    print(f"   Null agent_id: {agent_id_null_count}")
    if agent_id_null_count == 0 and agent_id_set_count > 0:
        print("   ✅ PASS — every delta has agent_id")
    elif agent_id_set_count > 0:
        print(f"   ⚠️  PARTIAL — {agent_id_null_count}/{total_deltas} had null agent_id")
    else:
        print("   ❌ FAIL — no agent_id found on any delta")

    # Test 2: agent_id per-agent breakdown
    print("\n2. Unique agents seen in stream:")
    for aid, count in agent_id_seen.items():
        print(f"   {aid}: {count} chunks")

    # Test 3: Handoff sequence
    print(f"\n3. Handoff sequence ({len(handoff_sequence)} handoffs):")
    for h in handoff_sequence:
        print(f"   → {h}")

    # Test 4: First delta had no preceding handoff (Router starts directly)
    print("\n4. First agent (Router) starts without handoff:")
    print(f"   First delta agent_id: {first_delta_agent_id}")
    print(f"   Had handoff before first delta: {first_delta_had_handoff_before}")
    if not first_delta_had_handoff_before and first_delta_agent_id is not None:
        print("   ✅ PASS — Router starts streaming without a preceding handoff.done")
    else:
        print(f"   ⚠️  CHECK — first delta had handoff before={first_delta_had_handoff_before}")

    # Test 5: output_index values
    print(f"\n5. output_index values seen: {sorted(output_indices)}")
    if len(output_indices) > 1:
        print("   ✅ PASS — multiple output_indices confirm per-agent blocks")
    elif len(output_indices) == 1:
        print("   ⚠️  Only 1 output_index — may be single-agent response")
    else:
        print("   ❌ No output_index found")

    # Test 6: content_index values
    print(f"\n6. content_index values seen: {sorted(content_indices)}")

    # Summary
    print()
    print("=" * 70)
    print(f"Total events: {len(events_log)}")
    print(f"Unique agents: {len(agent_id_seen)}")
    print(f"Handoffs: {len(handoff_sequence)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
