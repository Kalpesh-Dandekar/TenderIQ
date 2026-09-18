from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.models.blueprint import BlueprintResponse
from app.models.hybrid_blueprint import BlueprintMode
from app.services.blueprint import BlueprintGenerationError, BlueprintService
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.gemini import GeminiConfigurationError, GeminiServiceError, GoogleGeminiProvider
from app.services.hybrid_blueprint import HybridBlueprintError, HybridBlueprintService
from app.services.pdf_extractor import PdfExtractionError, extract_pdf
from app.services.pdf_upload import read_validated_pdf

router = APIRouter(prefix="/blueprint", tags=["blueprint"])


def get_blueprint_service() -> HybridBlueprintService:
    provider = GoogleGeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.gemini_max_attempts)
    full_llm_service = BlueprintService(provider, settings.blueprint_chunk_max_characters)
    return HybridBlueprintService(LocalDocumentIntelligenceService(), provider, full_llm_service)


@router.post("/tender", response_model=BlueprintResponse)
async def generate_tender_blueprint(
    file: UploadFile = File(...),
    mode: BlueprintMode = Query(default=BlueprintMode.HYBRID),
    service: HybridBlueprintService = Depends(get_blueprint_service),
) -> BlueprintResponse:
    filename, data = await read_validated_pdf(file, settings.max_pdf_size_bytes)
    try:
        extracted = extract_pdf(data, filename)
        blueprint = await run_in_threadpool(service.generate, extracted, mode)
    except PdfExtractionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    except GeminiConfigurationError as error:
        raise HTTPException(status_code=503, detail="Gemini is not configured") from error
    except HybridBlueprintError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except (GeminiServiceError, BlueprintGenerationError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return BlueprintResponse(blueprint=blueprint)
