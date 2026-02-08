#!/usr/bin/env python3
"""
Manual test script to verify Mistral SDK streaming behavior.
This tests whether the stream iterator properly terminates after ResponseDoneEvent.

Usage:
    cd sumii-mobile-api
    source venv/bin/activate
    python tests/manual/test_mistral_stream.py

Environment:
    Requires MISTRAL_API_KEY to be set
"""

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

# Load env from .env file if present
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    print("Note: python-dotenv not installed, using environment variables directly")

from mistralai.models import (
    AgentHandoffDoneEvent,
    FunctionCallEvent,
    MessageOutputEvent,
    ResponseDoneEvent,
)

from app.services.mistral_client import get_mistral_client

# Configuration
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
TEST_AGENT_ID = os.getenv("MISTRAL_ROUTER_AGENT_ID", "ag_019bf079c9e3738baacf6013ae3c55ef")
TIMEOUT_SECONDS = 10  # How long to wait for next event before considering it hung


def log(msg: str):
    """Simple timestamped logging."""
    print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} | {msg}")


def test_sync_stream():
    """Test synchronous streaming with the Mistral SDK."""
    log("=" * 60)
    log("TEST 1: Synchronous Stream Iteration")
    log("=" * 60)

    if not MISTRAL_API_KEY:
        log("ERROR: MISTRAL_API_KEY not set!")
        return False

    client = get_mistral_client()

    log(f"Starting stream with agent: {TEST_AGENT_ID}")
    log("Sending test message: 'Hello, I have a legal question about my landlord'")

    try:
        response = client.beta.conversations.start_stream(
            agent_id=TEST_AGENT_ID,
            inputs="Hello, I have a legal question about my landlord not fixing the heating.",
        )

        log("Stream started, iterating events...")
        event_count = 0
        response_done_received = False

        with response as event_stream:
            # Get conversation ID from first event
            first_event = next(iter(event_stream))
            conv_id = getattr(first_event.data, "conversation_id", "unknown")
            log(f"Conversation ID: {conv_id}")

            # Process events
            for event in event_stream:
                event_count += 1
                event_type = type(event.data).__name__

                if isinstance(event.data, MessageOutputEvent):
                    content = getattr(event.data, "content", "")
                    if content:
                        content_preview = str(content)[:50] + "..." if len(str(content)) > 50 else str(content)
                        log(f"  Event #{event_count}: MessageOutput - {content_preview}")
                elif isinstance(event.data, AgentHandoffDoneEvent):
                    next_agent = getattr(event.data, "next_agent_name", "unknown")
                    log(f"  Event #{event_count}: AgentHandoff -> {next_agent}")
                elif isinstance(event.data, FunctionCallEvent):
                    func_name = getattr(event.data, "name", "unknown")
                    log(f"  Event #{event_count}: FunctionCall - {func_name}")
                elif isinstance(event.data, ResponseDoneEvent):
                    log(f"  Event #{event_count}: ResponseDoneEvent - STREAM COMPLETE!")
                    response_done_received = True
                    # NOTE: We DO NOT break here to test if stream naturally ends
                else:
                    log(f"  Event #{event_count}: {event_type}")

        log(f"Stream ended naturally after {event_count} events")
        log(f"ResponseDoneEvent received: {response_done_received}")
        return True

    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        return False


async def async_next_with_timeout(iterator, timeout: float) -> tuple[Any, bool, bool]:
    """
    Get next item from iterator with timeout.
    Returns (item, timed_out, exhausted) tuple.
    """
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)

    def get_next():
        try:
            return next(iterator), False, False  # item, timed_out, exhausted
        except StopIteration:
            return None, False, True

    try:
        result = await asyncio.wait_for(loop.run_in_executor(executor, get_next), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        return None, True, False  # timed_out
    finally:
        executor.shutdown(wait=False)


async def test_async_stream_with_timeout():
    """Test streaming with async timeout handling."""
    log("=" * 60)
    log("TEST 2: Async Stream with Timeout (workaround for hang)")
    log("=" * 60)

    if not MISTRAL_API_KEY:
        log("ERROR: MISTRAL_API_KEY not set!")
        return False

    client = get_mistral_client()

    log(f"Starting stream with agent: {TEST_AGENT_ID}")
    log("Sending test message: 'Hello, I have a legal question about heating'")

    try:
        response = client.beta.conversations.start_stream(
            agent_id=TEST_AGENT_ID,
            inputs="Hi, my landlord won't fix the heating. What can I do?",
        )

        log(f"Stream started, iterating with {TIMEOUT_SECONDS}s timeout per event...")
        event_count = 0
        response_done_received = False

        with response as event_stream:
            # Get first event
            first_event = next(iter(event_stream))
            conv_id = getattr(first_event.data, "conversation_id", "unknown")
            log(f"Conversation ID: {conv_id}")

            # Create iterator
            stream_iter = iter(event_stream)

            # Process with timeout
            while True:
                event_count += 1

                # Get next event with timeout
                item, timed_out, exhausted = await async_next_with_timeout(stream_iter, timeout=TIMEOUT_SECONDS)

                if exhausted:
                    log("✅ Stream exhausted naturally (StopIteration)")
                    break

                if timed_out:
                    log(f"⚠️ TIMEOUT after {TIMEOUT_SECONDS}s waiting for event #{event_count}")
                    if response_done_received:
                        log("✅ ResponseDoneEvent was received before timeout - this is the bug!")
                        log("   The stream hung after ResponseDoneEvent instead of raising StopIteration")
                    break

                event = item
                event_type = type(event.data).__name__

                if isinstance(event.data, MessageOutputEvent):
                    log(f"  Event #{event_count}: MessageOutput")
                elif isinstance(event.data, AgentHandoffDoneEvent):
                    next_agent = getattr(event.data, "next_agent_name", "unknown")
                    log(f"  Event #{event_count}: AgentHandoff -> {next_agent}")
                elif isinstance(event.data, FunctionCallEvent):
                    func_name = getattr(event.data, "name", "unknown")
                    log(f"  Event #{event_count}: FunctionCall - {func_name}")
                elif isinstance(event.data, ResponseDoneEvent):
                    log(f"  Event #{event_count}: ResponseDoneEvent - STREAM SHOULD END!")
                    response_done_received = True
                    # Don't break - test if stream hangs here
                else:
                    log(f"  Event #{event_count}: {event_type}")

        log(f"Stream processing complete. Total events: {event_count}")
        log(f"ResponseDoneEvent received: {response_done_received}")
        return True

    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_simple_quick_conversation():
    """Test a very simple conversation that shouldn't trigger function calls."""
    log("=" * 60)
    log("TEST 3: Simple Quick Conversation (no function calls)")
    log("=" * 60)

    if not MISTRAL_API_KEY:
        log("ERROR: MISTRAL_API_KEY not set!")
        return False

    client = get_mistral_client()

    log(f"Starting stream with agent: {TEST_AGENT_ID}")
    log("Sending simple message: 'Hi'")

    try:
        response = client.beta.conversations.start_stream(
            agent_id=TEST_AGENT_ID,
            inputs="Hi",
        )

        log("Stream started...")
        event_count = 0
        events_list = []

        start_time = time.time()
        with response as event_stream:
            for event in event_stream:
                event_count += 1
                event_type = type(event.data).__name__
                events_list.append(event_type)

                if isinstance(event.data, ResponseDoneEvent):
                    log(f"  Event #{event_count}: ResponseDoneEvent - stream ending...")
                    # Break immediately after ResponseDoneEvent
                    break
                elif event_count <= 5:
                    log(f"  Event #{event_count}: {event_type}")
                elif event_count == 6:
                    log("  ... (more events)")

        elapsed = time.time() - start_time
        log(f"Stream completed in {elapsed:.2f}s with {event_count} events")
        log(f"Event types: {', '.join(set(events_list))}")
        return True

    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        return False


async def main():
    """Run all tests."""
    log("=" * 60)
    log("MISTRAL SDK STREAM BEHAVIOR TEST")
    log("=" * 60)
    log(f"API Key set: {bool(MISTRAL_API_KEY)}")
    log(f"Test Agent ID: {TEST_AGENT_ID}")
    log("")

    # Test 1: Simple sync stream
    result1 = test_simple_quick_conversation()
    log("")

    # Test 2: Full sync stream (may hang)
    log("Starting sync stream test (may hang if bug exists)...")
    log("Press Ctrl+C to skip if it hangs")
    try:
        result2 = test_sync_stream()
    except KeyboardInterrupt:
        log("INTERRUPTED - sync stream hung as expected")
        result2 = False
    log("")

    # Test 3: Async stream with timeout (workaround)
    result3 = await test_async_stream_with_timeout()
    log("")

    log("=" * 60)
    log("RESULTS:")
    log(f"  Simple conversation: {'PASS' if result1 else 'FAIL'}")
    log(f"  Sync stream: {'PASS' if result2 else 'FAIL (likely hung)'}")
    log(f"  Async with timeout: {'PASS' if result3 else 'FAIL'}")
    log("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
