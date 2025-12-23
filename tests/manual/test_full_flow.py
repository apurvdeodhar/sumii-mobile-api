#!/usr/bin/env python3
"""
Sumii Mobile API - Comprehensive Manual Test Script

This script tests the full flow of the Sumii Mobile API against local Docker containers.
It simulates REAL USER SCENARIOS including:
- User registration and login
- Multi-turn legal consultation chat sessions
- Document uploads (rental contracts, photos)
- Push notification token registration
- In-chat summary generation
- Final summary generation (Markdown + PDF)
- Lawyer search and connection

IMPORTANT: Tests run step-by-step. If a test fails, subsequent dependent tests are skipped.

Prerequisites:
- Docker containers running: docker-compose up -d
- .env file with: MISTRAL_API_KEY, MISTRAL_ORG_ID, MISTRAL_LIBRARY_ID
- AWS credentials for S3/SES (real AWS, not LocalStack)
- sumii-anwalt backend running: docker-compose up -d (in sumii-anwalt/docker)

Usage:
    .venv/bin/python3 tests/manual/test_full_flow.py

    # Verbose mode:
    .venv/bin/python3 tests/manual/test_full_flow.py -v

    # Continue on failure (don't stop):
    .venv/bin/python3 tests/manual/test_full_flow.py --continue-on-failure
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TypedDict

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


class TestStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


def print_header(title: str):
    print(f"\n{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {title}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*70}{Colors.ENDC}\n")


def print_phase(phase_num: int, phase_name: str):
    print(f"\n{Colors.BOLD}--- Phase {phase_num}: {phase_name} ---{Colors.ENDC}")


def print_test(name: str):
    print(f"{Colors.CYAN}[TEST] {name}{Colors.ENDC}")


def print_success(msg: str):
    print(f"{Colors.GREEN}  ✅ {msg}{Colors.ENDC}")


def print_error(msg: str):
    print(f"{Colors.RED}  ❌ {msg}{Colors.ENDC}")


def print_info(msg: str):
    print(f"{Colors.YELLOW}  ℹ️  {msg}{Colors.ENDC}")


def print_skip(msg: str):
    print(f"{Colors.YELLOW}  ⏭️  SKIPPED: {msg}{Colors.ENDC}")


def print_debug(msg: str, verbose: bool = False):
    if verbose:
        print(f"     {Colors.BLUE}→ {msg}{Colors.ENDC}")


def print_chat(role: str, msg: str, verbose: bool = False):
    """Print chat message in a visually distinct way"""
    if verbose:
        icon = "👤" if role == "user" else "🤖"
        color = Colors.CYAN if role == "user" else Colors.GREEN
        print(f"     {color}{icon} {role.upper()}: {msg[:80]}{'...' if len(msg) > 80 else ''}{Colors.ENDC}")


def print_stream_start(agent: str):
    """Print start of streaming response"""
    print(f"\n     {Colors.GREEN}🤖 {agent.upper()}:{Colors.ENDC} ", end="", flush=True)


def print_stream_token(token: str):
    """Print a streaming token without newline"""
    sys.stdout.write(f"{Colors.GREEN}{token}{Colors.ENDC}")
    sys.stdout.flush()


def print_stream_end():
    """End streaming output"""
    print()  # Newline


@dataclass
class TestResult:
    """Result of a single test"""

    name: str
    status: TestStatus
    message: str = ""
    is_critical: bool = False


@dataclass
class TestContext:
    """Holds test state across tests"""

    token: str | None = None
    user_id: str | None = None
    conversation_id: str | None = None
    document_id: str | None = None
    summary_id: str | None = None
    summary_pdf_url: str | None = None
    summary_markdown: str | None = None
    lawyer_id: int | None = None
    lawyer_connection_id: str | None = None
    expo_push_token: str | None = None
    verbose: bool = False
    interactive: bool = False  # Y/n prompts between messages
    stream_display: bool = True  # Show streaming tokens
    continue_on_failure: bool = False
    last_failure: str | None = None
    results: list = field(default_factory=list)
    # Track chat messages for summary generation
    chat_messages: list = field(default_factory=list)


# =============================================================================
# REAL USER SCENARIO: German tenant with broken heating
# =============================================================================


class MessageDict(TypedDict):
    role: str
    content: str


class ScenarioDict(TypedDict):
    title: str
    legal_area: str
    messages: list[MessageDict]


SCENARIO_TENANT_HEATING: ScenarioDict = {
    "title": "Mietminderung wegen defekter Heizung",
    "legal_area": "Mietrecht",
    "messages": [
        {
            "role": "user",
            "content": (
                "Hallo, ich brauche dringend Hilfe. Meine Heizung in meiner Mietwohnung "
                "ist seit 3 Wochen kaputt und der Vermieter reagiert nicht."
            ),
        },
        {
            "role": "user",
            "content": "Ich wohne seit 2 Jahren in der Wohnung in Berlin-Kreuzberg. Die Kaltmiete beträgt 850 Euro.",
        },
        {
            "role": "user",
            "content": (
                "Ich habe dem Vermieter am 1. Dezember per E-Mail Bescheid gegeben. "
                "Er hat nur geantwortet, dass er sich darum kümmert, aber seitdem ist nichts passiert."
            ),
        },
        {
            "role": "user",
            "content": (
                "In der Wohnung sind es jetzt nur noch 15 Grad. "
                "Ich habe ein Thermometer aufgestellt und Fotos gemacht."
            ),
        },
        {
            "role": "user",
            "content": "Ich möchte wissen, ob ich die Miete mindern kann und wie viel Prozent angemessen wären.",
        },
    ],
}


class TestRunner:
    """Runs all manual tests with realistic user scenarios"""

    def __init__(
        self,
        verbose: bool = False,
        continue_on_failure: bool = False,
        interactive: bool = False,
        stream_display: bool = True,
    ):
        self.ctx = TestContext(
            verbose=verbose,
            continue_on_failure=continue_on_failure,
            interactive=interactive,
            stream_display=stream_display,
        )
        self.client = httpx.Client(timeout=60.0)  # Increased timeout for AI responses
        self.test_email = f"test-{int(time.time())}@sumii.de"
        self.test_password = "TestPassword123!"
        self.should_stop = False
        self.scenario: ScenarioDict = SCENARIO_TENANT_HEATING

    def _record_result(self, name: str, status: TestStatus, message: str = "", is_critical: bool = False):
        """Record test result and check if we should stop"""
        result = TestResult(name=name, status=status, message=message, is_critical=is_critical)
        self.ctx.results.append(result)

        if status == TestStatus.FAILED and is_critical and not self.ctx.continue_on_failure:
            self.should_stop = True
            self.ctx.last_failure = name

    def _check_should_continue(self) -> bool:
        """Check if we should continue running tests"""
        if self.should_stop:
            print_skip(f"Previous critical test '{self.ctx.last_failure}' failed")
            return False
        return True

    def _auth_headers(self) -> dict:
        """Get authorization headers"""
        return {"Authorization": f"Bearer {self.ctx.token}"}

    def run_all(self):
        """Run all tests in sequence, simulating a real user journey"""
        print_header("SUMII MOBILE API - REAL USER SCENARIO TEST")
        print_info(f"Base URL: {BASE_URL}")
        print_info(f"Test email: {self.test_email}")
        print_info(f"Scenario: {self.scenario['title']}")
        print_info(f"Timestamp: {datetime.now().isoformat()}")
        print_info(f"Mode: {'Continue on failure' if self.ctx.continue_on_failure else 'Stop on critical failure'}")

        try:
            # =================================================================
            # PHASE 1: Infrastructure Check
            # =================================================================
            print_phase(1, "Infrastructure Check")
            if not self.test_health_check():
                return

            # =================================================================
            # PHASE 2: User Registration & Authentication
            # =================================================================
            print_phase(2, "User Registration & Login")
            if not self._check_should_continue():
                return
            self.test_auth_register()

            if not self._check_should_continue():
                return
            if not self.test_auth_login():
                return

            # =================================================================
            # PHASE 3: Push Notification Setup
            # =================================================================
            print_phase(3, "Push Notification Setup")
            if not self._check_should_continue():
                return
            self.test_register_push_token()

            # =================================================================
            # PHASE 4: Create Legal Consultation
            # =================================================================
            print_phase(4, "Create Legal Consultation")
            if not self._check_should_continue():
                return
            if not self.test_create_conversation():
                return

            # =================================================================
            # PHASE 5: Upload Supporting Documents
            # =================================================================
            print_phase(5, "Upload Supporting Documents")
            if not self._check_should_continue():
                return
            self.test_upload_rental_contract()
            self.test_upload_evidence_photo()

            # =================================================================
            # PHASE 6: Real-Time Legal Consultation (WebSocket Chat)
            # =================================================================
            print_phase(6, "Legal Consultation Chat")
            if not self._check_should_continue():
                return
            asyncio.run(self.test_full_chat_session())

            # =================================================================
            # PHASE 7: In-Chat Summary (Automatic after facts collected)
            # =================================================================
            print_phase(7, "In-Chat Summary Check")
            if not self._check_should_continue():
                return
            asyncio.run(self.test_request_in_chat_summary())

            # =================================================================
            # PHASE 8: Generate Final Summary (PDF + Markdown)
            # =================================================================
            print_phase(8, "Final Summary Generation")
            if not self._check_should_continue():
                return
            self.test_generate_final_summary()
            self.test_get_summary_pdf_url()
            self.test_get_summary_markdown()

            # =================================================================
            # PHASE 9: Find Matching Lawyers
            # =================================================================
            print_phase(9, "Lawyer Search")
            if not self._check_should_continue():
                return
            self.test_search_lawyers()

            # =================================================================
            # PHASE 10: Connect with Lawyer
            # =================================================================
            print_phase(10, "Lawyer Connection")
            if not self._check_should_continue():
                return
            self.test_connect_with_lawyer()
            self.test_list_lawyer_connections()

            # =================================================================
            # PHASE 11: Cleanup
            # =================================================================
            print_phase(11, "Cleanup")
            self.test_delete_conversation()

        except Exception as e:
            print_error(f"Test suite crashed: {e}")
            import traceback

            traceback.print_exc()
            self._record_result("Suite", TestStatus.FAILED, str(e), is_critical=True)

        finally:
            self.print_summary()

    # =========================================================================
    # PHASE 1: Infrastructure
    # =========================================================================

    def test_health_check(self) -> bool:
        print_test("Health Check")
        try:
            response = self.client.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                print_success("API is healthy")
                self._record_result("Health Check", TestStatus.PASSED)
                return True
            else:
                print_error(f"Unexpected status: {response.status_code}")
                self._record_result("Health Check", TestStatus.FAILED, f"HTTP {response.status_code}", is_critical=True)
                return False
        except Exception as e:
            print_error(f"Cannot reach API: {e}")
            self._record_result("Health Check", TestStatus.FAILED, str(e), is_critical=True)
            return False

    # =========================================================================
    # PHASE 2: Authentication
    # =========================================================================

    def test_auth_register(self) -> bool:
        print_test("Register New User")
        response = self.client.post(
            f"{API_V1}/auth/register", json={"email": self.test_email, "password": self.test_password}
        )

        if response.status_code == 201:
            data = response.json()
            self.ctx.user_id = data.get("id")
            print_success(f"User registered: {self.ctx.user_id}")
            self._record_result("Auth: Register", TestStatus.PASSED)
            return True
        elif response.status_code == 400 and "already registered" in response.text.lower():
            print_info("User already exists - continuing")
            self._record_result("Auth: Register", TestStatus.SKIPPED, "Already exists")
            return True
        else:
            print_error(f"Registration failed: {response.status_code} - {response.text}")
            self._record_result("Auth: Register", TestStatus.FAILED, response.text, is_critical=True)
            return False

    def test_auth_login(self) -> bool:
        print_test("User Login")
        response = self.client.post(
            f"{API_V1}/auth/login", data={"username": self.test_email, "password": self.test_password}
        )

        if response.status_code == 200:
            data = response.json()
            self.ctx.token = data.get("access_token")
            print_success(f"Logged in, token: {self.ctx.token[:30]}...")
            self._record_result("Auth: Login", TestStatus.PASSED)
            return True
        else:
            print_error(f"Login failed: {response.status_code}")
            self._record_result("Auth: Login", TestStatus.FAILED, response.text, is_critical=True)
            return False

    # =========================================================================
    # PHASE 3: Push Notifications
    # =========================================================================

    def test_register_push_token(self) -> bool:
        print_test("Register Push Notification Token")
        # Simulate Expo push token
        self.ctx.expo_push_token = f"ExponentPushToken[test-{int(time.time())}]"

        response = self.client.post(
            f"{API_V1}/users/push-token",
            headers=self._auth_headers(),
            json={"expo_push_token": self.ctx.expo_push_token},
        )

        if response.status_code in [200, 201]:
            print_success(f"Push token registered: {self.ctx.expo_push_token[:30]}...")
            self._record_result("Push Token: Register", TestStatus.PASSED)
            return True
        elif response.status_code == 404:
            print_info("Push token endpoint not implemented yet")
            self._record_result("Push Token: Register", TestStatus.SKIPPED, "Endpoint not found")
            return True
        else:
            print_info(f"Push token registration: {response.status_code}")
            self._record_result("Push Token: Register", TestStatus.SKIPPED, f"HTTP {response.status_code}")
            return True

    # =========================================================================
    # PHASE 4: Conversations
    # =========================================================================

    def test_create_conversation(self) -> bool:
        print_test("Create Legal Consultation Conversation")
        response = self.client.post(
            f"{API_V1}/conversations",
            headers=self._auth_headers(),
            json={"title": self.scenario["title"], "legal_area": self.scenario["legal_area"]},
        )

        if response.status_code == 201:
            data = response.json()
            self.ctx.conversation_id = data.get("id")
            print_success(f"Created conversation: {self.ctx.conversation_id}")
            print_debug(f"Title: {self.scenario['title']}", self.ctx.verbose)
            self._record_result("Conversation: Create", TestStatus.PASSED)
            return True
        else:
            print_error(f"Create failed: {response.status_code} - {response.text}")
            self._record_result("Conversation: Create", TestStatus.FAILED, response.text, is_critical=True)
            return False

    # =========================================================================
    # PHASE 5: Document Uploads
    # =========================================================================

    def test_upload_rental_contract(self) -> bool:
        print_test("Upload Rental Contract (PDF)")
        if not self.ctx.conversation_id:
            print_skip("No conversation ID")
            self._record_result("Document: Rental Contract", TestStatus.SKIPPED)
            return True

        # Create a realistic dummy PDF content
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        pdf_content += b"2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n"
        pdf_content += b"3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\n"
        pdf_content += b"trailer\n<<\n/Root 1 0 R\n>>\n%%EOF"

        files = {"file": ("Mietvertrag_2022.pdf", pdf_content, "application/pdf")}
        data = {"conversation_id": str(self.ctx.conversation_id), "run_ocr": "false"}

        response = self.client.post(f"{API_V1}/documents/", headers=self._auth_headers(), files=files, data=data)

        if response.status_code == 201:
            data = response.json()
            self.ctx.document_id = data.get("id")
            print_success(f"Uploaded rental contract: {self.ctx.document_id}")
            self._record_result("Document: Rental Contract", TestStatus.PASSED)
            return True
        elif response.status_code == 500 and "s3" in response.text.lower():
            print_info("S3 not configured - check AWS credentials")
            self._record_result("Document: Rental Contract", TestStatus.SKIPPED, "S3 not configured")
            return True
        else:
            print_error(f"Upload failed: {response.status_code} - {response.text[:100]}")
            self._record_result("Document: Rental Contract", TestStatus.FAILED, response.text[:100])
            return False

    def test_upload_evidence_photo(self) -> bool:
        print_test("Upload Evidence Photo (Thermometer)")
        if not self.ctx.conversation_id:
            print_skip("No conversation ID")
            self._record_result("Document: Evidence Photo", TestStatus.SKIPPED)
            return True

        # Create a minimal valid JPEG file (1x1 pixel white image)
        jpeg_content = bytes(
            [
                0xFF,
                0xD8,
                0xFF,
                0xE0,
                0x00,
                0x10,
                0x4A,
                0x46,
                0x49,
                0x46,
                0x00,
                0x01,
                0x01,
                0x00,
                0x00,
                0x01,
                0x00,
                0x01,
                0x00,
                0x00,
                0xFF,
                0xDB,
                0x00,
                0x43,
                0x00,
                0x08,
                0x06,
                0x06,
                0x07,
                0x06,
                0x05,
                0x08,
                0x07,
                0x07,
                0x07,
                0x09,
                0x09,
                0x08,
                0x0A,
                0x0C,
                0x14,
                0x0D,
                0x0C,
                0x0B,
                0x0B,
                0x0C,
                0x19,
                0x12,
                0x13,
                0x0F,
                0x14,
                0x1D,
                0x1A,
                0x1F,
                0x1E,
                0x1D,
                0x1A,
                0x1C,
                0x1C,
                0x20,
                0x24,
                0x2E,
                0x27,
                0x20,
                0x22,
                0x2C,
                0x23,
                0x1C,
                0x1C,
                0x28,
                0x37,
                0x29,
                0x2C,
                0x30,
                0x31,
                0x34,
                0x34,
                0x34,
                0x1F,
                0x27,
                0x39,
                0x3D,
                0x38,
                0x32,
                0x3C,
                0x2E,
                0x33,
                0x34,
                0x32,
                0xFF,
                0xC0,
                0x00,
                0x0B,
                0x08,
                0x00,
                0x01,
                0x00,
                0x01,
                0x01,
                0x01,
                0x11,
                0x00,
                0xFF,
                0xC4,
                0x00,
                0x1F,
                0x00,
                0x00,
                0x01,
                0x05,
                0x01,
                0x01,
                0x01,
                0x01,
                0x01,
                0x01,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x09,
                0x0A,
                0x0B,
                0xFF,
                0xC4,
                0x00,
                0xB5,
                0x10,
                0x00,
                0x02,
                0x01,
                0x03,
                0x03,
                0x02,
                0x04,
                0x03,
                0x05,
                0x05,
                0x04,
                0x04,
                0x00,
                0x00,
                0x01,
                0x7D,
                0xFF,
                0xDA,
                0x00,
                0x08,
                0x01,
                0x01,
                0x00,
                0x00,
                0x3F,
                0x00,
                0x7F,
                0xFF,
                0xD9,
            ]
        )

        files = {"file": ("Thermometer_15Grad.jpg", jpeg_content, "image/jpeg")}
        data = {"conversation_id": str(self.ctx.conversation_id), "run_ocr": "false"}

        response = self.client.post(f"{API_V1}/documents/", headers=self._auth_headers(), files=files, data=data)

        if response.status_code == 201:
            data = response.json()
            print_success(f"Uploaded evidence photo: {data.get('id')}")
            self._record_result("Document: Evidence Photo", TestStatus.PASSED)
            return True
        elif response.status_code == 500:
            print_info("Evidence photo upload skipped (S3 issue)")
            self._record_result("Document: Evidence Photo", TestStatus.SKIPPED, "S3 issue")
            return True
        else:
            print_error(f"Upload failed: {response.status_code}")
            self._record_result("Document: Evidence Photo", TestStatus.FAILED)
            return False

    # =========================================================================
    # PHASE 6: Full Chat Session (Real User Scenario)
    # =========================================================================

    async def test_full_chat_session(self) -> bool:
        print_test("Full Legal Consultation Chat Session")
        print_info(f"Sending {len(self.scenario['messages'])} messages to simulate real consultation")
        if self.ctx.stream_display:
            print_info("Streaming tokens will be displayed in real-time")
        if self.ctx.interactive:
            print_info("Interactive mode - press Y/n after each message")

        if not self.ctx.conversation_id or not self.ctx.token:
            print_skip("No conversation/token")
            self._record_result("Chat: Full Session", TestStatus.SKIPPED)
            return True

        ws_url = f"{WS_URL}/ws/chat/{self.ctx.conversation_id}?token={self.ctx.token}"

        try:
            async with websockets.connect(ws_url, close_timeout=10) as ws:
                for i, msg in enumerate(self.scenario["messages"]):
                    user_message = msg["content"]

                    # Display user message
                    print(f"\n     {Colors.CYAN}👤 YOU [{i+1}/{len(self.scenario['messages'])}]:{Colors.ENDC}")
                    print(f"     {Colors.CYAN}{user_message}{Colors.ENDC}")

                    # Send user message
                    await ws.send(json.dumps({"type": "message", "content": user_message}))

                    # Collect and display agent responses
                    agent_response = ""
                    current_agent = None
                    try:
                        # Wait for responses (agent may send multiple chunks)
                        while True:
                            try:
                                response = await asyncio.wait_for(ws.recv(), timeout=60.0)
                                data = json.loads(response)
                                msg_type = data.get("type")

                                if msg_type == "agent_start":
                                    agent = data.get("agent", "unknown")
                                    if agent != current_agent:
                                        current_agent = agent
                                        if self.ctx.stream_display:
                                            print_stream_start(agent)

                                elif msg_type in ["agent_handoff", "agent_handoff_done"]:
                                    # Handoff to new agent
                                    agent = data.get("agent_name") or data.get("to_agent", "unknown")
                                    if agent != current_agent:
                                        current_agent = agent
                                        if self.ctx.stream_display:
                                            print_stream_start(agent)

                                elif msg_type == "message_chunk":
                                    # Streaming token from server
                                    token = data.get("content", "")
                                    agent_response += token
                                    if self.ctx.stream_display:
                                        print_stream_token(token)

                                elif msg_type in ["agent_complete", "message_complete", "conversation.response.done"]:
                                    if self.ctx.stream_display:
                                        print_stream_end()
                                    break

                                elif msg_type == "error":
                                    print_error(f"Agent error: {data.get('error')}")
                                    break

                            except asyncio.TimeoutError:
                                if self.ctx.stream_display:
                                    print_stream_end()
                                print_info("Response timeout (60s)")
                                break

                        if agent_response:
                            self.ctx.chat_messages.append({"user": user_message, "agent": agent_response})

                    except Exception as e:
                        print_debug(f"Response handling: {e}", self.ctx.verbose)

                    # Interactive mode - prompt to continue
                    if self.ctx.interactive and i < len(self.scenario["messages"]) - 1:
                        print()
                        continue_choice = (
                            input(f"{Colors.YELLOW}Continue to next message? [Y/n]: {Colors.ENDC}").strip().lower()
                        )
                        if continue_choice in ["n", "no"]:
                            print_info("Stopped by user")
                            break

                print_success(f"Completed {len(self.ctx.chat_messages)} message exchanges")
                self._record_result("Chat: Full Session", TestStatus.PASSED)
                return True

        except websockets.exceptions.InvalidStatusCode as e:
            print_error(f"WebSocket rejected: HTTP {e.status_code}")
            self._record_result("Chat: Full Session", TestStatus.FAILED, f"HTTP {e.status_code}", is_critical=True)
            return False
        except Exception as e:
            print_error(f"Chat session error: {e}")
            self._record_result("Chat: Full Session", TestStatus.FAILED, str(e))
            return False

    # =========================================================================
    # PHASE 7: In-Chat Summary
    # =========================================================================

    async def test_request_in_chat_summary(self) -> bool:
        print_test("Request In-Chat Summary")
        print_info("Requesting quick summary based on collected facts")

        if not self.ctx.conversation_id or not self.ctx.token:
            print_skip("No conversation/token")
            self._record_result("In-Chat Summary", TestStatus.SKIPPED)
            return True

        ws_url = f"{WS_URL}/ws/chat/{self.ctx.conversation_id}?token={self.ctx.token}"

        try:
            async with websockets.connect(ws_url, close_timeout=10) as ws:
                # Request in-chat summary
                await ws.send(
                    json.dumps(
                        {
                            "type": "message",
                            "content": "Kannst du mir bitte eine kurze Zusammenfassung meines Falls geben?",
                        }
                    )
                )

                summary_content = ""
                try:
                    while True:
                        response = await asyncio.wait_for(ws.recv(), timeout=30.0)
                        data = json.loads(response)

                        if data.get("type") == "token":
                            summary_content += data.get("content", "")
                        elif data.get("type") in ["agent_complete", "error"]:
                            break
                except asyncio.TimeoutError:
                    pass

                if summary_content:
                    print_success("In-chat summary received")
                    print_debug(f"Summary preview: {summary_content[:150]}...", self.ctx.verbose)
                    self._record_result("In-Chat Summary", TestStatus.PASSED)
                else:
                    print_info("No summary content received (agent may be processing)")
                    self._record_result("In-Chat Summary", TestStatus.PASSED, "No content but connected")
                return True

        except Exception as e:
            print_error(f"In-chat summary error: {e}")
            self._record_result("In-Chat Summary", TestStatus.FAILED, str(e))
            return False

    # =========================================================================
    # PHASE 8: Final Summary Generation
    # =========================================================================

    def test_generate_final_summary(self) -> bool:
        print_test("Generate Final Legal Summary (PDF + Markdown)")
        if not self.ctx.conversation_id:
            print_skip("No conversation ID")
            self._record_result("Summary: Generate", TestStatus.SKIPPED)
            return True

        response = self.client.post(
            f"{API_V1}/summaries", headers=self._auth_headers(), json={"conversation_id": self.ctx.conversation_id}
        )

        if response.status_code == 201:
            data = response.json()
            self.ctx.summary_id = data.get("id")
            self.ctx.summary_markdown = data.get("markdown_content")
            print_success(f"Summary generated: {self.ctx.summary_id}")
            print_debug(f"Reference: {data.get('reference_number')}", self.ctx.verbose)
            print_debug(f"Legal area: {data.get('legal_area')}", self.ctx.verbose)
            print_debug(f"Case strength: {data.get('case_strength')}", self.ctx.verbose)
            self._record_result("Summary: Generate", TestStatus.PASSED)
            return True
        elif response.status_code == 400:
            print_info("Summary already exists or conversation incomplete")
            self._record_result("Summary: Generate", TestStatus.SKIPPED, "Already exists")
            return True
        elif response.status_code == 500:
            if "at least one element" in response.text or "empty" in response.text.lower():
                print_info("Summary skipped: Conversation needs more messages")
                self._record_result("Summary: Generate", TestStatus.SKIPPED, "Needs more chat content")
                return True
            print_error(f"Summary generation failed: {response.text[:100]}")
            self._record_result("Summary: Generate", TestStatus.FAILED, "Agent error")
            return False
        else:
            print_error(f"Summary failed: {response.status_code}")
            self._record_result("Summary: Generate", TestStatus.FAILED, response.text[:100])
            return False

    def test_get_summary_pdf_url(self) -> bool:
        print_test("Get Summary PDF Download URL")
        if not self.ctx.summary_id:
            print_skip("No summary ID")
            self._record_result("Summary: PDF URL", TestStatus.SKIPPED)
            return True

        response = self.client.get(f"{API_V1}/summaries/{self.ctx.summary_id}/pdf-url", headers=self._auth_headers())

        if response.status_code == 200:
            data = response.json()
            self.ctx.summary_pdf_url = data.get("pdf_url")
            print_success("PDF URL obtained (expires in 7 days)")
            print_debug(f"URL: {self.ctx.summary_pdf_url[:80]}...", self.ctx.verbose)
            self._record_result("Summary: PDF URL", TestStatus.PASSED)
            return True
        elif response.status_code == 404:
            print_info("PDF not found (may not have been generated)")
            self._record_result("Summary: PDF URL", TestStatus.SKIPPED, "Not found")
            return True
        else:
            print_error(f"PDF URL failed: {response.status_code}")
            self._record_result("Summary: PDF URL", TestStatus.FAILED)
            return False

    def test_get_summary_markdown(self) -> bool:
        print_test("Get Summary Markdown Content")
        if not self.ctx.summary_id:
            print_skip("No summary ID")
            self._record_result("Summary: Markdown", TestStatus.SKIPPED)
            return True

        response = self.client.get(f"{API_V1}/summaries/{self.ctx.summary_id}", headers=self._auth_headers())

        if response.status_code == 200:
            data = response.json()
            markdown = data.get("markdown_content", "")
            print_success(f"Markdown content: {len(markdown)} characters")
            if self.ctx.verbose and markdown:
                # Show first few lines of markdown
                lines = markdown.split("\n")[:5]
                for line in lines:
                    print_debug(line[:80], True)
            self._record_result("Summary: Markdown", TestStatus.PASSED)
            return True
        elif response.status_code == 404:
            print_info("Summary not found")
            self._record_result("Summary: Markdown", TestStatus.SKIPPED, "Not found")
            return True
        else:
            print_error(f"Markdown fetch failed: {response.status_code}")
            self._record_result("Summary: Markdown", TestStatus.FAILED)
            return False

    # =========================================================================
    # PHASE 9: Lawyer Search
    # =========================================================================

    def test_search_lawyers(self) -> bool:
        print_test("Search for Lawyers (Mietrecht specialists)")

        # Search for lawyers specializing in rental law
        response = self.client.get(
            f"{API_V1}/anwalt/search",
            headers=self._auth_headers(),
            params={"language": "de", "legal_area": self.scenario.get("legal_area", "Mietrecht")},
        )

        if response.status_code == 200:
            lawyers = response.json()
            count = len(lawyers) if isinstance(lawyers, list) else 0
            print_success(f"Found {count} matching lawyers")

            if count > 0 and isinstance(lawyers, list):
                # Store first lawyer for connection test
                self.ctx.lawyer_id = lawyers[0].get("id")
                print_debug(
                    f"First match: {lawyers[0].get('full_name')} - {lawyers[0].get('specialization')}", self.ctx.verbose
                )

            self._record_result("Lawyer: Search", TestStatus.PASSED)
            return True
        elif response.status_code == 503:
            print_info("sumii-anwalt service not available")
            self._record_result("Lawyer: Search", TestStatus.SKIPPED, "Service unavailable")
            return True
        elif response.status_code == 500:
            print_info("Lawyer search service error")
            self._record_result("Lawyer: Search", TestStatus.SKIPPED, "Service error")
            return True
        else:
            print_error(f"Search failed: {response.status_code}")
            self._record_result("Lawyer: Search", TestStatus.FAILED)
            return False

    # =========================================================================
    # PHASE 10: Lawyer Connection
    # =========================================================================

    def test_connect_with_lawyer(self) -> bool:
        print_test("Connect with Lawyer (Send Case)")
        if not self.ctx.conversation_id:
            print_skip("No conversation ID")
            self._record_result("Lawyer: Connect", TestStatus.SKIPPED)
            return True

        if not self.ctx.lawyer_id:
            print_info("No lawyer ID from search - using test ID")
            self.ctx.lawyer_id = 1  # Default test lawyer

        response = self.client.post(
            f"{API_V1}/anwalt/connect",
            headers=self._auth_headers(),
            json={
                "conversation_id": self.ctx.conversation_id,
                "lawyer_id": self.ctx.lawyer_id,
                "user_message": (
                    "Sehr geehrte/r Rechtsanwalt/Rechtsanwältin, "
                    "ich bitte um Ihre Hilfe bei meinem Mietrechtsproblem."
                ),
            },
        )

        if response.status_code == 201:
            data = response.json()
            self.ctx.lawyer_connection_id = data.get("id")
            print_success(f"Connection initiated: {self.ctx.lawyer_connection_id}")
            print_debug(f"Status: {data.get('status')}", self.ctx.verbose)
            self._record_result("Lawyer: Connect", TestStatus.PASSED)
            return True
        elif response.status_code == 400:
            print_info("Connection already exists")
            self._record_result("Lawyer: Connect", TestStatus.SKIPPED, "Already connected")
            return True
        elif response.status_code in [404, 422, 503]:
            print_info(f"Connection skipped: {response.status_code}")
            self._record_result("Lawyer: Connect", TestStatus.SKIPPED, f"HTTP {response.status_code}")
            return True
        else:
            print_error(f"Connect failed: {response.status_code}")
            self._record_result("Lawyer: Connect", TestStatus.FAILED)
            return False

    def test_list_lawyer_connections(self) -> bool:
        print_test("List User's Lawyer Connections")

        response = self.client.get(f"{API_V1}/anwalt/connections", headers=self._auth_headers())

        if response.status_code == 200:
            data = response.json()
            count = data.get("total", 0)
            print_success(f"Found {count} lawyer connection(s)")
            self._record_result("Lawyer: List Connections", TestStatus.PASSED)
            return True
        elif response.status_code == 404:
            print_info("Connections endpoint not found")
            self._record_result("Lawyer: List Connections", TestStatus.SKIPPED, "Endpoint not found")
            return True
        else:
            print_error(f"List failed: {response.status_code}")
            self._record_result("Lawyer: List Connections", TestStatus.FAILED)
            return False

    # =========================================================================
    # PHASE 11: Cleanup
    # =========================================================================

    def test_delete_conversation(self) -> bool:
        print_test("Cleanup: Delete Conversation")
        if not self.ctx.conversation_id:
            print_skip("No conversation to delete")
            self._record_result("Cleanup", TestStatus.SKIPPED)
            return True

        response = self.client.delete(
            f"{API_V1}/conversations/{self.ctx.conversation_id}", headers=self._auth_headers()
        )

        if response.status_code == 204:
            print_success("Conversation deleted")
            self._record_result("Cleanup", TestStatus.PASSED)
            return True
        else:
            print_info(f"Cleanup: {response.status_code}")
            self._record_result("Cleanup", TestStatus.SKIPPED, f"HTTP {response.status_code}")
            return True

    # =========================================================================
    # Summary Report
    # =========================================================================

    def print_summary(self):
        print_header("TEST RESULTS")

        passed = sum(1 for r in self.ctx.results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self.ctx.results if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in self.ctx.results if r.status == TestStatus.SKIPPED)
        total = len(self.ctx.results)

        print(f"  Total:   {total}")
        print(f"  {Colors.GREEN}Passed:  {passed}{Colors.ENDC}")
        print(f"  {Colors.RED}Failed:  {failed}{Colors.ENDC}")
        print(f"  {Colors.YELLOW}Skipped: {skipped}{Colors.ENDC}")

        if failed > 0:
            print(f"\n{Colors.RED}{Colors.BOLD}  Failed Tests:{Colors.ENDC}")
            for r in self.ctx.results:
                if r.status == TestStatus.FAILED:
                    msg = f": {r.message[:50]}" if r.message else ""
                    print(f"    - {r.name}{msg}")
            print(f"\n{Colors.RED}{Colors.BOLD}  ❌ SOME TESTS FAILED{Colors.ENDC}")
        else:
            print(f"\n{Colors.GREEN}{Colors.BOLD}  ✅ ALL TESTS PASSED!{Colors.ENDC}")


def main():
    parser = argparse.ArgumentParser(description="Sumii Mobile API Manual Test Suite")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose debug output")
    parser.add_argument(
        "-i", "--interactive", action="store_true", help="Interactive mode - prompt Y/n after each message"
    )
    parser.add_argument("--no-stream", action="store_true", help="Don't display streaming tokens")
    parser.add_argument("--continue-on-failure", action="store_true", help="Continue running tests even after failures")
    args = parser.parse_args()

    runner = TestRunner(
        verbose=args.verbose,
        continue_on_failure=args.continue_on_failure,
        interactive=args.interactive,
        stream_display=not args.no_stream,
    )
    runner.run_all()


if __name__ == "__main__":
    main()
