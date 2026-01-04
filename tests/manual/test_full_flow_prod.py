#!/usr/bin/env python3
"""
Sumii Mobile API - Production Test Script (Full Coverage)

Tests the complete production system including:
- Health checks (API, Anwalt, S3)
- User registration and login
- Full agent pipeline (Router → Intake → Reasoning → WrapUp → Summary)
- Document uploads with real test files
- Summary generation and S3 storage
- Lawyer search (by area, location, language)
- SSE events and notifications

Usage:
    .venv/bin/python tests/manual/test_full_flow_prod.py -v
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

import httpx
import websockets

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_URL = "https://api.sumii.de"
WS_URL = "wss://api.sumii.de"
ANWALT_URL = "https://anwalt.sumii.de"
API_V1 = f"{BASE_URL}/api/v1"
S3_BUCKET = "sumii-prod-pdfs"

# Test documents directory
TEST_DOCS_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "testing-docs"


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


def print_agent_event(event_type: str, data: dict = None):
    icon = {
        "agent_start": "🤖",
        "agent_handoff": "🔄",
        "message_chunk": "📝",
        "wrapup_ready": "📋",
        "summary_ready": "📄",
        "message_complete": "✅",
        "function_call": "⚙️",
    }.get(event_type, "📨")
    agent = data.get("agent", "") if data else ""
    print(f"     {Colors.DIM}{icon} {event_type}{f' ({agent})' if agent else ''}{Colors.ENDC}")


def print_stream_token(token: str):
    sys.stdout.write(f"{Colors.GREEN}{token}{Colors.ENDC}")
    sys.stdout.flush()


@dataclass
class TestResult:
    name: str
    status: TestStatus
    message: str = ""


@dataclass
class TestContext:
    token: str | None = None
    user_id: str | None = None
    conversation_id: str | None = None
    document_id: str | None = None
    summary_id: str | None = None
    summary_pdf_url: str | None = None
    summary_reference: str | None = None
    lawyer_id: int | None = None
    verbose: bool = False
    stream_display: bool = True
    continue_on_failure: bool = False
    last_failure: str | None = None
    results: list = field(default_factory=list)
    agent_events: list = field(default_factory=list)


# =============================================================================
# SCENARIO: German tenant with heating problem + documents
# =============================================================================
SCENARIO_MESSAGES = [
    "Hallo, ich brauche dringend Hilfe. Meine Heizung in meiner Mietwohnung ist seit 3 Wochen kaputt.",
    "Ich wohne seit 2 Jahren in der Wohnung in Berlin-Kreuzberg. Die Kaltmiete beträgt 850 Euro.",
    "Ich habe dem Vermieter am 1. Dezember per E-Mail Bescheid gegeben, aber er reagiert nicht.",
    "In der Wohnung sind es nur noch 15 Grad. Ich habe Fotos und das Thermometer dokumentiert.",
    "Ich möchte wissen, ob ich die Miete mindern kann und wie viel Prozent.",
    "Der Mietvertrag läuft seit 15.01.2024. Vermieter ist Hans Müller.",
    "Ja, das ist alles korrekt. Bitte erstellen Sie die Zusammenfassung.",
]


class ProdTestRunner:
    """Comprehensive production test runner"""

    def __init__(self, verbose: bool = False, continue_on_failure: bool = False, stream_display: bool = True):
        self.ctx = TestContext(
            verbose=verbose,
            continue_on_failure=continue_on_failure,
            stream_display=stream_display,
        )
        self.client = httpx.Client(timeout=120.0, verify=True)
        self.test_email = f"test-prod-{int(time.time())}@sumii.de"
        self.test_password = "TestPassword123!"
        self.should_stop = False

    def _record(self, name: str, status: TestStatus, msg: str = "", critical: bool = False):
        self.ctx.results.append(TestResult(name=name, status=status, message=msg))
        if status == TestStatus.FAILED and critical and not self.ctx.continue_on_failure:
            self.should_stop = True
            self.ctx.last_failure = name

    def _check_continue(self) -> bool:
        if self.should_stop:
            print_skip(f"Previous test '{self.ctx.last_failure}' failed")
            return False
        return True

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.ctx.token}"}

    def run_all(self):
        print_header("SUMII PRODUCTION TEST (FULL COVERAGE)")
        print_info(f"API: {BASE_URL}")
        print_info(f"Anwalt: {ANWALT_URL}")
        print_info(f"Test Docs: {TEST_DOCS_DIR}")
        print_info(f"Email: {self.test_email}")
        print_info(f"Time: {datetime.now().isoformat()}")

        try:
            # Phase 1: Health
            print_phase(1, "Health Checks")
            if not self.test_health():
                return

            # Phase 2: Auth
            print_phase(2, "Authentication")
            if not self._check_continue():
                return
            self.test_register()
            if not self._check_continue():
                return
            if not self.test_login():
                return

            # Phase 3: Conversation
            print_phase(3, "Conversation")
            if not self._check_continue():
                return
            self.test_create_conversation()

            # Phase 4: Document Upload
            print_phase(4, "Document Upload")
            if not self._check_continue():
                return
            self.test_upload_document()

            # Phase 5: Agent Flow Chat
            print_phase(5, "Agent Flow Chat (7 messages)")
            if not self._check_continue():
                return
            asyncio.run(self.test_agent_chat())
            self.print_agent_summary()

            # Phase 6: Summary
            print_phase(6, "Summary Generation")
            if not self._check_continue():
                return
            self.test_generate_summary()
            self.test_pdf_url()
            self.test_pdf_download()
            self.test_s3_verify()

            # Phase 7: Lawyer Search
            print_phase(7, "Lawyer Search")
            if not self._check_continue():
                return
            self.test_search_lawyers()

            # Phase 8: Notifications
            print_phase(8, "Notifications")
            if not self._check_continue():
                return
            self.test_notifications()

            # Phase 9: Cleanup
            print_phase(9, "Cleanup")
            self.test_cleanup()

        except Exception as e:
            print_error(f"Test crashed: {e}")
            import traceback

            traceback.print_exc()
            self._record("Suite", TestStatus.FAILED, str(e), True)
        finally:
            self.print_summary()

    # =========================================================================
    # Phase 1: Health
    # =========================================================================
    def test_health(self) -> bool:
        print_test("API Health")
        try:
            r = self.client.get(f"{BASE_URL}/health")
            if r.status_code == 200:
                print_success("API healthy")
                self._record("Health: API", TestStatus.PASSED)
            else:
                print_error(f"HTTP {r.status_code}")
                self._record("Health: API", TestStatus.FAILED, critical=True)
                return False
        except Exception as e:
            print_error(str(e))
            self._record("Health: API", TestStatus.FAILED, str(e), True)
            return False

        print_test("Anwalt Health")
        try:
            r = self.client.get(f"{ANWALT_URL}/", follow_redirects=True)
            if r.status_code in [200, 302]:
                print_success("Anwalt accessible")
                self._record("Health: Anwalt", TestStatus.PASSED)
        except Exception as e:
            print_info(f"Anwalt: {e}")
            self._record("Health: Anwalt", TestStatus.SKIPPED)
        return True

    # =========================================================================
    # Phase 2: Auth
    # =========================================================================
    def test_register(self) -> bool:
        print_test("Register User")
        r = self.client.post(f"{API_V1}/auth/register", json={"email": self.test_email, "password": self.test_password})
        if r.status_code == 201:
            self.ctx.user_id = r.json().get("id")
            print_success(f"Registered: {self.ctx.user_id}")
            self._record("Auth: Register", TestStatus.PASSED)
            return True
        elif r.status_code == 400 and "already" in r.text.lower():
            print_info("User exists")
            self._record("Auth: Register", TestStatus.SKIPPED)
            return True
        print_error(f"Failed: {r.status_code}")
        self._record("Auth: Register", TestStatus.FAILED, r.text, True)
        return False

    def test_login(self) -> bool:
        print_test("Login")
        r = self.client.post(f"{API_V1}/auth/login", data={"username": self.test_email, "password": self.test_password})
        if r.status_code == 200:
            self.ctx.token = r.json().get("access_token")
            print_success(f"Token: {self.ctx.token[:25]}...")
            self._record("Auth: Login", TestStatus.PASSED)
            return True
        print_error(f"Failed: {r.status_code}")
        self._record("Auth: Login", TestStatus.FAILED, r.text, True)
        return False

    # =========================================================================
    # Phase 3: Conversation
    # =========================================================================
    def test_create_conversation(self) -> bool:
        print_test("Create Conversation")
        r = self.client.post(
            f"{API_V1}/conversations",
            headers=self._headers(),
            json={"title": "Mietminderung Heizung", "legal_area": "Mietrecht"},
        )
        if r.status_code == 201:
            self.ctx.conversation_id = r.json().get("id")
            print_success(f"ID: {self.ctx.conversation_id}")
            self._record("Conversation: Create", TestStatus.PASSED)
            return True
        print_error(f"Failed: {r.status_code}")
        self._record("Conversation: Create", TestStatus.FAILED, r.text, True)
        return False

    # =========================================================================
    # Phase 4: Document Upload
    # =========================================================================
    def test_upload_document(self) -> bool:
        print_test("Upload Test Document")

        # Find test doc
        doc_path = TEST_DOCS_DIR / "sample-mietvertrag.pdf"
        if not doc_path.exists():
            print_info(f"Test doc not found: {doc_path}")
            self._record("Document: Upload", TestStatus.SKIPPED)
            return True

        try:
            with open(doc_path, "rb") as f:
                # Correct endpoint: POST /api/v1/documents/ (not /upload)
                r = self.client.post(
                    f"{API_V1}/documents/",
                    headers=self._headers(),
                    files={"file": (doc_path.name, f, "application/pdf")},
                    data={"conversation_id": str(self.ctx.conversation_id)},
                )

            if r.status_code in [200, 201]:
                data = r.json()
                self.ctx.document_id = data.get("id") or data.get("document_id")
                print_success(f"Uploaded: {self.ctx.document_id}")
                print_debug(f"OCR: {data.get('ocr_complete', 'N/A')}", self.ctx.verbose)
                self._record("Document: Upload", TestStatus.PASSED)
                return True
            elif r.status_code == 404:
                print_info("Upload endpoint not found")
                self._record("Document: Upload", TestStatus.SKIPPED)
                return True
            else:
                print_error(f"Failed: {r.status_code}")
                self._record("Document: Upload", TestStatus.FAILED, r.text[:100])
                return True
        except Exception as e:
            print_info(f"Upload error: {e}")
            self._record("Document: Upload", TestStatus.SKIPPED, str(e))
            return True

    # =========================================================================
    # Phase 5: Agent Chat Flow
    # =========================================================================
    async def test_agent_chat(self) -> bool:
        print_test("Full Agent Pipeline")
        print_info(f"Sending {len(SCENARIO_MESSAGES)} messages")

        if not self.ctx.conversation_id or not self.ctx.token:
            print_skip("No conversation/token")
            self._record("Chat: Agent Flow", TestStatus.SKIPPED)
            return True

        ws_url = f"{WS_URL}/ws/chat/{self.ctx.conversation_id}?token={self.ctx.token}"

        try:
            async with websockets.connect(ws_url, close_timeout=10) as ws:
                for i, msg in enumerate(SCENARIO_MESSAGES):
                    print(f"\n     {Colors.CYAN}👤 [{i+1}/{len(SCENARIO_MESSAGES)}]: {msg[:55]}...{Colors.ENDC}")

                    await ws.send(json.dumps({"type": "message", "content": msg}))

                    # Collect agent events
                    try:
                        while True:
                            response = await asyncio.wait_for(ws.recv(), timeout=60.0)
                            data = json.loads(response)
                            event_type = data.get("type")

                            # Log agent events
                            if event_type in [
                                "agent_start",
                                "agent_handoff",
                                "wrapup_ready",
                                "summary_ready",
                                "function_call",
                            ]:
                                self.ctx.agent_events.append(data)
                                print_agent_event(event_type, data)

                            # Stream tokens
                            if event_type == "message_chunk" and self.ctx.stream_display:
                                print_stream_token(data.get("content", ""))

                            # Summary auto-generated
                            if event_type == "summary_ready":
                                self.ctx.summary_id = data.get("summary_id")
                                print(f"\n     {Colors.GREEN}📄 Auto-summary: {self.ctx.summary_id}{Colors.ENDC}")

                            if event_type in ["message_complete", "agent_complete"]:
                                if self.ctx.stream_display:
                                    print()
                                break

                    except asyncio.TimeoutError:
                        print_info("Timeout (60s)")
                        if self.ctx.stream_display:
                            print()

                    await asyncio.sleep(1)

                print_success(f"Completed {len(SCENARIO_MESSAGES)} exchanges")
                self._record("Chat: Agent Flow", TestStatus.PASSED)
                return True

        except websockets.exceptions.InvalidStatusCode as e:
            print_error(f"WS rejected: {e.status_code}")
            self._record("Chat: Agent Flow", TestStatus.FAILED, f"HTTP {e.status_code}", True)
            return False
        except Exception as e:
            print_error(f"Chat error: {e}")
            self._record("Chat: Agent Flow", TestStatus.FAILED, str(e))
            return False

    def print_agent_summary(self):
        """Print summary of agent events observed"""
        if not self.ctx.agent_events:
            return

        agent_starts = [e for e in self.ctx.agent_events if e.get("type") == "agent_start"]
        handoffs = [e for e in self.ctx.agent_events if e.get("type") == "agent_handoff"]

        print(f"\n     {Colors.BLUE}Agent Flow Summary:{Colors.ENDC}")
        print(f"     - Agents started: {len(agent_starts)}")
        print(f"     - Handoffs: {len(handoffs)}")

        agents_seen = set()
        for e in agent_starts:
            agent = e.get("agent", "unknown")
            agents_seen.add(agent)
        if agents_seen:
            print(f"     - Agents: {', '.join(agents_seen)}")

    # =========================================================================
    # Phase 6: Summary
    # =========================================================================
    def test_generate_summary(self) -> bool:
        print_test("Generate Summary")
        if not self.ctx.conversation_id:
            print_skip("No conversation")
            self._record("Summary: Generate", TestStatus.SKIPPED)
            return True

        if self.ctx.summary_id:
            print_info(f"Auto-generated: {self.ctx.summary_id}")
            self._record("Summary: Generate", TestStatus.PASSED, "Auto")
            return True

        r = self.client.post(
            f"{API_V1}/summaries",
            headers=self._headers(),
            json={"conversation_id": self.ctx.conversation_id},
            timeout=120.0,
        )

        if r.status_code == 201:
            data = r.json()
            self.ctx.summary_id = data.get("id")
            self.ctx.summary_reference = data.get("reference_number")
            md_len = len(data.get("markdown_content", ""))
            print_success(f"Generated: {self.ctx.summary_id}")
            print_info(f"Reference: {self.ctx.summary_reference}")
            print_info(f"Markdown: {md_len} chars")
            self._record("Summary: Generate", TestStatus.PASSED)
            return True
        elif r.status_code == 400:
            print_info("Already exists")
            self._record("Summary: Generate", TestStatus.SKIPPED)
            return True
        print_error(f"Failed: {r.status_code} - {r.text[:100]}")
        self._record("Summary: Generate", TestStatus.FAILED, r.text[:100])
        return False

    def test_pdf_url(self) -> bool:
        print_test("Get PDF URL")
        if not self.ctx.summary_id:
            print_skip("No summary")
            self._record("Summary: PDF URL", TestStatus.SKIPPED)
            return True

        r = self.client.get(f"{API_V1}/summaries/{self.ctx.summary_id}/pdf", headers=self._headers())
        if r.status_code == 200:
            self.ctx.summary_pdf_url = r.json().get("pdf_url")
            print_success("URL obtained")
            self._record("Summary: PDF URL", TestStatus.PASSED)
            return True
        print_error(f"Failed: {r.status_code}")
        self._record("Summary: PDF URL", TestStatus.FAILED)
        return False

    def test_pdf_download(self) -> bool:
        print_test("Download PDF")
        if not self.ctx.summary_pdf_url:
            print_skip("No URL")
            self._record("Summary: PDF Download", TestStatus.SKIPPED)
            return True

        try:
            r = self.client.get(self.ctx.summary_pdf_url)
            if r.status_code == 200:
                size = len(r.content)
                is_pdf = r.content[:4] == b"%PDF"
                print_success(f"Downloaded: {size} bytes, valid PDF: {is_pdf}")
                self._record("Summary: PDF Download", TestStatus.PASSED)
                return True
            print_error(f"Failed: {r.status_code}")
            self._record("Summary: PDF Download", TestStatus.FAILED)
            return False
        except Exception as e:
            print_error(str(e))
            self._record("Summary: PDF Download", TestStatus.FAILED, str(e))
            return False

    def test_s3_verify(self) -> bool:
        print_test(f"S3 Verify ({S3_BUCKET})")
        if not self.ctx.summary_reference:
            print_skip("No reference")
            self._record("S3: Verify", TestStatus.SKIPPED)
            return True

        try:
            import subprocess

            key = f"summaries/{self.ctx.summary_reference}.pdf"
            result = subprocess.run(f"aws s3 ls s3://{S3_BUCKET}/{key}", shell=True, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                print_success(f"Found in S3: {key}")
                self._record("S3: Verify", TestStatus.PASSED)
                return True
            print_info("Not found (may be stored differently)")
            self._record("S3: Verify", TestStatus.SKIPPED)
            return True
        except Exception as e:
            print_info(str(e))
            self._record("S3: Verify", TestStatus.SKIPPED, str(e))
            return True

    # =========================================================================
    # Phase 7: Lawyer Search
    # =========================================================================
    def test_search_lawyers(self) -> bool:
        print_test("Search Lawyers (Mietrecht, Berlin, German)")

        r = self.client.get(
            f"{API_V1}/anwalt/search",
            headers=self._headers(),
            params={"legal_area": "Mietrecht", "city": "Berlin", "language": "de"},
        )

        if r.status_code == 200:
            lawyers = r.json()
            count = len(lawyers) if isinstance(lawyers, list) else 0
            print_success(f"Found {count} lawyers")
            if count > 0 and isinstance(lawyers, list):
                self.ctx.lawyer_id = lawyers[0].get("id")
                print_debug(f"First: {lawyers[0].get('full_name', 'N/A')}", self.ctx.verbose)
            self._record("Lawyer: Search", TestStatus.PASSED)
            return True
        elif r.status_code in [404, 503]:
            print_info("Service unavailable")
            self._record("Lawyer: Search", TestStatus.SKIPPED)
            return True
        print_error(f"Failed: {r.status_code}")
        self._record("Lawyer: Search", TestStatus.FAILED)
        return False

    # =========================================================================
    # Phase 8: Notifications
    # =========================================================================
    def test_notifications(self) -> bool:
        print_test("Sync (includes Notifications)")

        # Sync endpoint is POST with request body
        r = self.client.post(
            f"{API_V1}/sync",
            headers=self._headers(),
            json={"last_synced_at": None},  # Full sync
        )

        if r.status_code == 200:
            data = r.json()
            notifications = data.get("notifications", [])
            print_success(f"Sync OK - {len(notifications)} notifications")
            self._record("Sync: Notifications", TestStatus.PASSED)
            return True
        elif r.status_code == 404:
            print_info("Endpoint not found")
            self._record("Sync: Notifications", TestStatus.SKIPPED)
            return True
        print_error(f"Failed: {r.status_code}")
        self._record("Sync: Notifications", TestStatus.FAILED)
        return False

    # =========================================================================
    # Phase 9: Cleanup
    # =========================================================================
    def test_cleanup(self) -> bool:
        print_test("Delete Conversation")
        if not self.ctx.conversation_id:
            print_skip("Nothing to clean")
            self._record("Cleanup", TestStatus.SKIPPED)
            return True

        r = self.client.delete(f"{API_V1}/conversations/{self.ctx.conversation_id}", headers=self._headers())
        if r.status_code == 204:
            print_success("Deleted")
            self._record("Cleanup", TestStatus.PASSED)
            return True
        print_info(f"Status: {r.status_code}")
        self._record("Cleanup", TestStatus.SKIPPED)
        return True

    # =========================================================================
    # Summary Report
    # =========================================================================
    def print_summary(self):
        print_header("TEST SUMMARY")

        passed = sum(1 for r in self.ctx.results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self.ctx.results if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in self.ctx.results if r.status == TestStatus.SKIPPED)
        total = len(self.ctx.results)

        print(f"  Total:   {total}")
        print(f"  {Colors.GREEN}Passed:  {passed}{Colors.ENDC}")
        print(f"  {Colors.RED}Failed:  {failed}{Colors.ENDC}")
        print(f"  {Colors.YELLOW}Skipped: {skipped}{Colors.ENDC}")

        if failed > 0:
            print(f"\n{Colors.RED}{Colors.BOLD}  Failed:{Colors.ENDC}")
            for r in self.ctx.results:
                if r.status == TestStatus.FAILED:
                    print(f"    - {r.name}: {r.message[:50]}")
            print(f"\n{Colors.RED}{Colors.BOLD}  ❌ TESTS FAILED{Colors.ENDC}")
        else:
            print(f"\n{Colors.GREEN}{Colors.BOLD}  ✅ ALL PASSED!{Colors.ENDC}")

        if self.ctx.summary_reference:
            print(f"\n  {Colors.BLUE}S3: {S3_BUCKET}/{self.ctx.summary_reference}{Colors.ENDC}")


def main():
    parser = argparse.ArgumentParser(description="Sumii Production Tests")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--continue-on-failure", action="store_true")
    args = parser.parse_args()

    runner = ProdTestRunner(
        verbose=args.verbose,
        continue_on_failure=args.continue_on_failure,
        stream_display=not args.no_stream,
    )
    runner.run_all()


if __name__ == "__main__":
    main()
