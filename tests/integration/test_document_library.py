#!/usr/bin/env python3
"""Test Document Library Service

Tests the DocumentLibraryService for creating Mistral document libraries.

These are integration tests that test Mistral document library creation.
Requires API keys (MISTRAL_API_KEY) to be set.
"""

from pathlib import Path

import pytest

from app.services.document_library import DocumentLibraryService

pytestmark = [pytest.mark.integration, pytest.mark.requires_api]


def test_mvp_library():
    """Test MVP library creation (Phase 1)"""
    print("=" * 80)
    print("Testing MVP Document Library Creation (Phase 1)")
    print("=" * 80)

    service = DocumentLibraryService()

    # Step 1: Verify template file exists
    print("\n[1] Verifying template file exists...")
    template_path = Path("docs/library/templates/SumiiCaseReportTemplate.md")
    if template_path.exists():
        print(f"✅ Template found: {template_path}")
    else:
        print(f"❌ Template NOT found: {template_path}")
        print(f"   Current working directory: {Path.cwd()}")
        return

    # Step 2: Create library
    print("\n[2] Creating Mistral document library...")
    try:
        library_id = service.create_sumii_library()
        print(f"✅ Library created: {library_id}")
    except Exception as e:
        print(f"❌ Library creation failed: {e}")
        return

    # Step 3: Upload template
    print("\n[3] Uploading legal template...")
    try:
        service.upload_legal_template()
        print("✅ Template uploaded successfully")
    except Exception as e:
        print(f"❌ Template upload failed: {e}")
        return

    # Step 4: Get library info
    print("\n[4] Retrieving library info...")
    try:
        info = service.get_library_info()
        print("✅ Library Info:")
        print(f"   ID: {info['id']}")
        print(f"   Name: {info['name']}")
        print(f"   Description: {info['description']}")
    except Exception as e:
        print(f"❌ Failed to get library info: {e}")

    print("\n" + "=" * 80)
    print("MVP Library Test Complete!")
    print("=" * 80)


def test_complete_library():
    """Test complete library creation (Phase 2)"""
    print("=" * 80)
    print("Testing Complete Document Library Creation (Phase 2)")
    print("=" * 80)

    service = DocumentLibraryService()

    # Check which files exist
    print("\n[1] Checking document files...")
    template_path = Path("docs/library/templates/SumiiCaseReportTemplate.md")
    bgb_path = Path("docs/library/bgb_mietrecht_sections.md")
    cases_path = Path("docs/library/case_examples_mietrecht.md")

    files_exist = {
        "Template": template_path.exists(),
        "BGB Sections": bgb_path.exists(),
        "Case Examples": cases_path.exists(),
    }

    for name, exists in files_exist.items():
        status = "✅" if exists else "❌"
        print(f"   {status} {name}")

    if not all(files_exist.values()):
        print("\n⚠️  Phase 2 files not ready. Run Phase 1 (MVP) first.")
        return

    # Create complete library
    print("\n[2] Creating complete library...")
    try:
        library_id = service.setup_complete_library()
        print(f"✅ Complete library created: {library_id}")
    except Exception as e:
        print(f"❌ Complete library creation failed: {e}")
        import traceback

        traceback.print_exc()
        return

    # Get library info
    print("\n[3] Retrieving library info...")
    try:
        info = service.get_library_info()
        print("✅ Library Info:")
        print(f"   ID: {info['id']}")
        print(f"   Name: {info['name']}")
        print(f"   Description: {info['description']}")
    except Exception as e:
        print(f"❌ Failed to get library info: {e}")

    print("\n" + "=" * 80)
    print("Complete Library Test Complete!")
    print("=" * 80)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "complete":
        test_complete_library()
    else:
        test_mvp_library()
