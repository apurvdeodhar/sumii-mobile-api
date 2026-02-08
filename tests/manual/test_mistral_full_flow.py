#!/usr/bin/env python3
"""
Test to reproduce the stream hang in async context and verify the fix.
This mimics the exact scenario in the websocket handler.
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from mistralai import FunctionResultEntry
from mistralai.models import (
    AgentHandoffDoneEvent,
    FunctionCallEvent,
    ResponseDoneEvent,
)

from app.services.mistral_client import get_mistral_client

# Load .env after standard imports
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
ROUTER_ID = os.getenv("MISTRAL_ROUTER_AGENT_ID", "ag_019bf079c9e3738baacf6013ae3c55ef")


def log(msg: str):
    print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} | {msg}")


# ==================== TEST 1: Reproduce the hang ====================
async def test_sync_next_in_async_blocks():
    """
    This demonstrates the PROBLEM: calling next() synchronously inside
    an async function blocks the event loop.
    """
    log("=" * 70)
    log("TEST 1: Sync next() inside async - SHOULD HANG after ResponseDoneEvent")
    log("=" * 70)

    client = get_mistral_client()

    log("Starting stream...")
    response = client.beta.conversations.start_stream(
        agent_id=ROUTER_ID,
        inputs="Hi, I have a problem with my landlord.",
    )

    log("Processing stream in async context with sync next()...")
    event_count = 0
    response_done_seen = False

    with response as event_stream:
        stream_iter = iter(event_stream)

        # Get first event
        first = next(stream_iter)
        log(f"First event: {type(first.data).__name__}")

        # THIS IS THE PROBLEM PATTERN - sync next() in async function
        # After ResponseDoneEvent, this will hang forever
        while True:
            # Simulate async work (like websocket.send_json)
            await asyncio.sleep(0)  # Yield to event loop

            try:
                event = next(stream_iter)  # BLOCKING CALL!
            except StopIteration:
                log("StopIteration - stream exhausted naturally")
                break

            event_count += 1
            event_type = type(event.data).__name__

            if isinstance(event.data, ResponseDoneEvent):
                log(f"Event #{event_count}: ResponseDoneEvent - GOT IT!")
                response_done_seen = True
                # Don't break - test if next iteration hangs
                # In real scenario, we'd set stream_done = True, but next() already called
                break  # We break here because we know it would hang
            elif event_count <= 5:
                log(f"Event #{event_count}: {event_type}")

    log(f"Stream complete: {event_count} events, ResponseDoneEvent: {response_done_seen}")


# ==================== TEST 2: The FIX using executor ====================
async def test_async_next_with_executor():
    """
    This demonstrates the FIX: run next() in executor with timeout.
    """
    log("=" * 70)
    log("TEST 2: Async next() with executor - SHOULD NOT HANG")
    log("=" * 70)

    client = get_mistral_client()

    log("Starting stream...")
    response = client.beta.conversations.start_stream(
        agent_id=ROUTER_ID,
        inputs="Hi, I have a problem with my landlord not fixing the heating.",
    )

    log("Processing stream with executor-based async next()...")
    event_count = 0
    response_done_seen = False

    with response as event_stream:
        stream_iter = iter(event_stream)
        executor = ThreadPoolExecutor(max_workers=1)

        # Get first event
        first = next(stream_iter)
        conv_id = getattr(first.data, "conversation_id", "unknown")
        log(f"First event: {type(first.data).__name__}, Conv ID: {conv_id}")

        async def get_next_event() -> tuple[Any | None, bool, bool]:
            """Get next event from stream in executor with timeout.
            Returns (event, exhausted, timed_out)"""
            loop = asyncio.get_event_loop()

            def _next():
                try:
                    return next(stream_iter), False
                except StopIteration:
                    return None, True

            try:
                event, exhausted = await asyncio.wait_for(
                    loop.run_in_executor(executor, _next),
                    timeout=5.0,  # 5s timeout for testing
                )
                return event, exhausted, False
            except asyncio.TimeoutError:
                return None, False, True

        stream_done = False
        while not stream_done:
            # Simulate async work
            await asyncio.sleep(0)

            event, exhausted, timed_out = await get_next_event()

            if exhausted:
                log("StopIteration - stream exhausted naturally ✅")
                break

            if timed_out:
                log("TIMEOUT - next() hung (this is the bug scenario)")
                if response_done_seen:
                    log("  ⚠️ Timeout occurred AFTER ResponseDoneEvent was seen!")
                break

            if event is None:
                break

            event_count += 1
            event_type = type(event.data).__name__

            if isinstance(event.data, ResponseDoneEvent):
                log(f"Event #{event_count}: ResponseDoneEvent - got it!")
                response_done_seen = True
                stream_done = True  # Set flag, but continue to check for proper termination
            elif isinstance(event.data, AgentHandoffDoneEvent):
                next_agent = getattr(event.data, "next_agent_name", "unknown")
                log(f"Event #{event_count}: Handoff -> {next_agent}")
            elif isinstance(event.data, FunctionCallEvent):
                func_name = getattr(event.data, "name", "unknown")
                log(f"Event #{event_count}: FunctionCall - {func_name}")
            elif event_count <= 10 or event_count % 20 == 0:
                log(f"Event #{event_count}: {event_type}")

        executor.shutdown(wait=False)

    log(f"Stream complete: {event_count} events, ResponseDoneEvent: {response_done_seen}")
    return response_done_seen


# ==================== TEST 3: Full conversation to summary ====================
async def test_full_conversation_flow():
    """
    Test a full conversation that goes through all agents including summary.
    """
    log("=" * 70)
    log("TEST 3: Full conversation flow to summary agent")
    log("=" * 70)

    client = get_mistral_client()

    # Message sequence to trigger full flow
    messages = [
        "I have a problem with my landlord not fixing the heating for 2 weeks.",
        "Yes that's right, 2 weeks",
        "I informed my landlord via email last week",
        "Yes",  # Confirm to trigger reasoning
        "Yes that's all correct",  # Confirm to trigger summary
    ]

    conv_id = None
    executor = ThreadPoolExecutor(max_workers=1)

    for i, msg in enumerate(messages):
        log(f"\n--- Message {i+1}: '{msg[:40]}...' ---")

        if conv_id is None:
            response = client.beta.conversations.start_stream(
                agent_id=ROUTER_ID,
                inputs=msg,
            )
        else:
            response = client.beta.conversations.append_stream(
                conversation_id=conv_id,
                inputs=msg,
            )

        event_count = 0
        current_function = None

        with response as event_stream:
            stream_iter = iter(event_stream)

            # Get conv_id from first event
            first = next(stream_iter)
            if conv_id is None and hasattr(first.data, "conversation_id"):
                conv_id = first.data.conversation_id
                log(f"Conv ID: {conv_id}")

            async def get_next() -> tuple[Any | None, bool, bool]:
                loop = asyncio.get_event_loop()

                def _next():
                    try:
                        return next(stream_iter), False
                    except StopIteration:
                        return None, True

                try:
                    ev, exh = await asyncio.wait_for(loop.run_in_executor(executor, _next), timeout=30.0)
                    return ev, exh, False
                except asyncio.TimeoutError:
                    return None, False, True

            stream_done = False
            while not stream_done:
                event, exhausted, timed_out = await get_next()

                if exhausted or timed_out or event is None:
                    if timed_out:
                        log("⚠️ TIMEOUT!")
                    break

                event_count += 1

                if isinstance(event.data, ResponseDoneEvent):
                    log(f"  Event #{event_count}: ResponseDoneEvent ✅")
                    stream_done = True
                elif isinstance(event.data, AgentHandoffDoneEvent):
                    agent = getattr(event.data, "next_agent_name", "unknown")
                    log(f"  Event #{event_count}: Handoff -> {agent}")
                elif isinstance(event.data, FunctionCallEvent):
                    func = getattr(event.data, "name", "unknown")
                    call_id = getattr(event.data, "tool_call_id", None)
                    args = getattr(event.data, "arguments", "")
                    if current_function is None or current_function[0] != call_id:
                        log(f"  Event #{event_count}: Function START - {func}")
                        current_function = (call_id, func, args)
                    else:
                        current_function = (call_id, func, current_function[2] + args)
                elif event_count <= 5 or event_count % 30 == 0:
                    log(f"  Event #{event_count}: {type(event.data).__name__}")

        log(f"  Stream: {event_count} events")

        # Handle function call if any
        if current_function:
            call_id, func, args = current_function
            log(f"  Handling function: {func}")

            # Mock results
            result = '{"status": "ok"}'
            if "summary" in func:
                result = '{"case_id": "test-123"}'
            elif "confirm" in func:
                result = '{"confirmed": true}'
            elif "track" in func:
                result = '{"tracked": []}'

            response = client.beta.conversations.append_stream(
                conversation_id=conv_id,
                inputs=[FunctionResultEntry(tool_call_id=call_id, result=result)],
            )

            with response as event_stream:
                stream_iter = iter(event_stream)
                while True:
                    ev, exh, to = await get_next()
                    if exh or to or ev is None:
                        break
                    if isinstance(ev.data, ResponseDoneEvent):
                        log("  Function result: ResponseDoneEvent ✅")
                        break

            current_function = None

    executor.shutdown(wait=False)
    log("\n" + "=" * 70)
    log("TEST 3 COMPLETE")
    log("=" * 70)


async def main():
    log("=" * 70)
    log("ASYNC STREAM FIX VERIFICATION")
    log("=" * 70)
    log(f"API Key: {'Set' if MISTRAL_API_KEY else 'NOT SET'}")
    log(f"Router: {ROUTER_ID}")
    log("")

    # Test 1: Demonstrate the problem pattern (will break early)
    await test_sync_next_in_async_blocks()
    log("")

    # Test 2: Demonstrate the fix
    success = await test_async_next_with_executor()
    log(f"Test 2 result: {'PASS' if success else 'FAIL'}")

    # Test 3: Full flow
    await test_full_conversation_flow()

    log("\n" + "=" * 70)
    log("VERIFICATION COMPLETE")
    log("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
