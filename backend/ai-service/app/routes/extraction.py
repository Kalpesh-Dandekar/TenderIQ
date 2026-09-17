from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.models.extraction import ExtractionResponse
from app.services.pdf_extractor import PdfExtractionError, extract_pdf
from app.services.pdf_upload import read_validated_pdf

router = APIRouter(prefix="/extract", tags=["extraction"])


@router.post("/pdf", response_model=ExtractionResponse)
async def extract_pdf_route(file: UploadFile = File(...)) -> ExtractionResponse:
    filename, data = await read_validated_pdf(file, settings.max_pdf_size_bytes)

    try:
        document = extract_pdf(data, filename)
    except PdfExtractionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return ExtractionResponse(document=document)
