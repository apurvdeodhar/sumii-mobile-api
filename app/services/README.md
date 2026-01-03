# Backend Services

## OCR Service (P0 - Dec 2024)

**File:** `ocr_service.py`

Extracts text from uploaded documents using Mistral AI Pixtral OCR.

### Features

- **Images** - Uses `pixtral-12b-2024-12-19` model
- **PDFs** - Uses Mistral OCR API
- **German prompts** - Optimized for German legal documents

### Usage

```python
from app.services.ocr_service import ocr_service

# Extract text from image
text = await ocr_service.extract_text_from_image(image_bytes, "doc.jpg")

# Extract text from PDF
text = await ocr_service.extract_text_from_pdf(pdf_bytes)

# Auto-detect by file type
text = await ocr_service.extract_text(file_bytes, "image/jpeg")
```

### Integration

Automatically called on document upload when `run_ocr=True` (default).
Results stored in `Document.ocr_text`.

---

## Storage Service

**File:** `storage_service.py`

Manages S3 file storage with pre-signed URLs.

### Key Methods

| Method | Description |
|--------|-------------|
| `upload_document(file, filename)` | Upload document, return S3 key |
| `upload_summary(content, ref_number)` | Upload summary PDF/MD |
| `generate_presigned_url(s3_key, days=7)` | Get time-limited access URL |
| `delete_object(s3_key)` | Delete file from S3 |

### S3 Bucket Structure

```
sumii-{env}-pdfs/
├── documents/{user_id}/{uuid}.{ext}
├── summaries/{reference_number}.pdf
└── summaries/{reference_number}.md
```

---

## Summary Service

**File:** `summary_service.py`

Generates legal summaries from conversations using AI.

### Flow

```
1. Get conversation messages
2. Call Mistral AI Summary Agent
3. Generate structured markdown
4. Convert to PDF via pdf_service
5. Upload both to S3
6. Return SummaryResponse with signed URL
```

### Output

- **Markdown** - Structured legal summary
- **PDF** - Professional formatted document
- **Metadata** - Legal area, case strength, urgency

---

## PDF Service

**File:** `pdf_service.py`

Generates PDF documents from HTML templates using WeasyPrint.

### Methods

| Method | Description |
|--------|-------------|
| `template_to_pdf(case_data, ref_number)` | Generate from Jinja2 template |
| `markdown_to_pdf(markdown)` | Simple markdown to PDF |

### Template

Located at `app/templates/legal_case_report.html`

---

## Other Services

| Service | Description |
|---------|-------------|
| `ocr_service.py` | Mistral Pixtral OCR extraction |
| `orchestrator.py` | AI agent orchestration |
| `email_service.py` | Email notifications (SES) |
| `push_service.py` | Push notifications (Expo) |
