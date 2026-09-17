# TenderIQ AI Service — B3 PDF Extraction

FastAPI service for deterministic, page-wise tender PDF text extraction with PyMuPDF. B3 returns source metadata, extraction statistics, a SHA-256 digest, and an OCR-readiness assessment. It does not perform OCR, LLM processing, or Tender Blueprint generation.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Configuration is documented in `.env.example`. Set `MAX_PDF_SIZE_MB` in the process environment to change the 25 MB default; the service intentionally does not require a dotenv package.

## Endpoints

- `GET http://localhost:8000/health`
- `POST http://localhost:8000/extract/pdf` with multipart field `file`

PowerShell example:

```powershell
curl.exe -X POST http://localhost:8000/extract/pdf -F "file=@C:\path\to\tender.pdf;type=application/pdf"
```

Each page is returned separately with human-friendly page numbering, text, character count, and word count. Document totals include text and empty-page counts. The SHA-256 digest identifies the received bytes but does not prove authenticity.

The deterministic assessment uses centralized thresholds:

- `TEXT_EXTRACTABLE`: meaningful text exists on at least 80% of pages.
- `PARTIALLY_EXTRACTABLE`: meaningful text exists, but on fewer than 80% of pages.
- `OCR_MAY_BE_REQUIRED`: no meaningful pages or less than 20 extracted characters per document page on average.

The assessment is a processing hint, not a definitive claim that OCR is required. OCR and Tender Blueprint generation are not implemented in B3.

## Tests

```powershell
python -m pytest
```
