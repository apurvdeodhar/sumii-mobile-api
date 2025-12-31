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

## Other Services

| Service | Description |
|---------|-------------|
| `orchestrator.py` | AI agent orchestration |
| `pdf_service.py` | PDF generation for summaries |
| `storage_service.py` | S3 file storage |
| `email_service.py` | Email notifications |
| `push_service.py` | Push notifications |
| `summary_service.py` | Legal summary generation |
