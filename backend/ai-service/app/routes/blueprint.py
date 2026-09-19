from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.models.aggregate_blueprint import AggregateBlueprintResponse
from app.models.hybrid_blueprint import BlueprintMode
from app.services.aggregate_blueprint import AggregateBlueprintService
from app.services.blueprint import BlueprintGenerationError, BlueprintService
from app.services.commercial_financial_blueprint import (
    CommercialFinancialBlueprintService,
    CommercialFinancialSmokeTestError,
    GoogleCommercialFinancialProvider,
)
from app.services.contractual_other_blueprint import (
    ContractualOtherBlueprintService,
    ContractualOtherSmokeTestError,
    GoogleContractualOtherProvider,
)
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.evidence_packager import BlueprintEvidencePackager
from app.services.gemini import GeminiConfigurationError, GeminiServiceError, GoogleGeminiProvider
from app.services.qualification_blueprint import (
    GoogleQualificationProvider,
    QualificationBlueprintService,
    QualificationSmokeTestError,
)
from app.services.pdf_extractor import PdfExtractionError, extract_pdf
from app.services.pdf_upload import read_validated_pdf
from app.services.technical_blueprint import GoogleTechnicalProvider, TechnicalBlueprintService, TechnicalSmokeTestError

router = APIRouter(prefix="/blueprint", tags=["blueprint"])


def get_blueprint_service() -> AggregateBlueprintService:
    provider = GoogleGeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.gemini_max_attempts)
    full_llm_service = BlueprintService(provider, settings.blueprint_chunk_max_characters)
    return AggregateBlueprintService(
        LocalDocumentIntelligenceService(),
        BlueprintEvidencePackager(),
        QualificationBlueprintService(GoogleQualificationProvider(settings.gemini_api_key, settings.gemini_model)),
        TechnicalBlueprintService(GoogleTechnicalProvider(settings.gemini_api_key, settings.gemini_model)),
        CommercialFinancialBlueprintService(
            GoogleCommercialFinancialProvider(settings.gemini_api_key, settings.gemini_model)
        ),
        ContractualOtherBlueprintService(GoogleContractualOtherProvider(settings.gemini_api_key, settings.gemini_model)),
        full_llm_service,
    )


@router.post("/tender", response_model=AggregateBlueprintResponse)
async def generate_tender_blueprint(
    file: UploadFile = File(...),
    mode: BlueprintMode = Query(default=BlueprintMode.HYBRID),
    service: AggregateBlueprintService = Depends(get_blueprint_service),
) -> AggregateBlueprintResponse:
    filename, data = await read_validated_pdf(file, settings.max_pdf_size_bytes)
    try:
        extracted = extract_pdf(data, filename)
        result = await run_in_threadpool(service.generate, extracted, mode)
    except PdfExtractionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    except GeminiConfigurationError as error:
        raise HTTPException(status_code=503, detail="Gemini is not configured") from error
    except (
        GeminiServiceError,
        BlueprintGenerationError,
        QualificationSmokeTestError,
        TechnicalSmokeTestError,
        CommercialFinancialSmokeTestError,
        ContractualOtherSmokeTestError,
    ) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return AggregateBlueprintResponse(
        blueprint=result.blueprint,
        grounded_semantics=result.grounded_semantics,
    )
