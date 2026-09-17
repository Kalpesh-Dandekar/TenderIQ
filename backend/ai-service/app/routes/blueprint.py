from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.models.blueprint import BlueprintResponse
from app.services.blueprint import BlueprintGenerationError, BlueprintService
from app.services.gemini import GeminiConfigurationError, GeminiServiceError, GoogleGeminiProvider
from app.services.pdf_extractor import PdfExtractionError, extract_pdf
from app.services.pdf_upload import read_validated_pdf

router = APIRouter(prefix="/blueprint", tags=["blueprint"])


def get_blueprint_service() -> BlueprintService:
    provider = GoogleGeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.gemini_max_attempts)
    return BlueprintService(provider, settings.blueprint_chunk_max_characters)


@router.post("/tender", response_model=BlueprintResponse)
async def generate_tender_blueprint(
    file: UploadFile = File(...), service: BlueprintService = Depends(get_blueprint_service)
) -> BlueprintResponse:
    filename, data = await read_validated_pdf(file, settings.max_pdf_size_bytes)
    try:
        extracted = extract_pdf(data, filename)
        blueprint = await run_in_threadpool(service.generate, extracted)
    except PdfExtractionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    except GeminiConfigurationError as error:
        raise HTTPException(status_code=503, detail="Gemini is not configured") from error
    except (GeminiServiceError, BlueprintGenerationError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return BlueprintResponse(blueprint=blueprint)
