from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.models.extraction import ExtractionResponse
from app.services.pdf_extractor import PdfExtractionError, extract_pdf

router = APIRouter(prefix="/extract", tags=["extraction"])


@router.post("/pdf", response_model=ExtractionResponse)
async def extract_pdf_route(file: UploadFile = File(...)) -> ExtractionResponse:
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Filename must end in .pdf")
    if file.content_type and file.content_type.lower() != "application/pdf":
        raise HTTPException(status_code=415, detail="Content type must be application/pdf")

    data = await file.read(settings.max_pdf_size_bytes + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=400, detail="PDF file must not be empty")
    if len(data) > settings.max_pdf_size_bytes:
        raise HTTPException(status_code=413, detail="PDF exceeds the configured size limit")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="File does not have a valid PDF signature")

    try:
        document = extract_pdf(data, filename)
    except PdfExtractionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return ExtractionResponse(document=document)
