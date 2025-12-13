"""
Test Fixtures and Constants
Shared test data to avoid hardcoded values across test files
"""

# Test user credentials (for integration/e2e tests only)
# These are NOT real credentials - only for test databases
TEST_USER_EMAIL = "test-user@sumii.de"
TEST_USER_PASSWORD = "TestPassword123!"  # Test-only password, never used in production
TEST_USER_EMAIL_2 = "test-user-2@sumii.de"
TEST_USER_PASSWORD_2 = "TestPassword456!"  # Test-only password

# Test conversation data
TEST_CONVERSATION_TITLE = "Test Conversation"
TEST_CONVERSATION_TITLE_2 = "Test Conversation 2"

# Test document data
TEST_DOCUMENT_FILENAME = "test_document.pdf"
TEST_DOCUMENT_FILENAME_2 = "test_document_2.pdf"
TEST_DOCUMENT_CONTENT_TYPE = "application/pdf"
TEST_DOCUMENT_SIZE = 1024

# Test message content
TEST_MESSAGE_CONTENT = "Ich habe ein Problem mit meiner Miete."
TEST_MESSAGE_CONTENT_2 = "Können Sie mir mehr Details geben?"

# Base URLs (for integration/e2e tests)
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

# Test file paths (if needed)
TEST_PDF_CONTENT = b"%PDF-1.4 fake pdf content"
TEST_IMAGE_CONTENT = b"\x89PNG\r\n\x1a\n"  # Fake PNG header
