import hashlib

import pymupdf
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.blueprint import (
    BlueprintResponse,
    CandidateDocument,
    CandidateRequirement,
    ChunkCandidates,
    RequirementCategory,
    RequirementType,
    SourceReference,
    TenderBlueprint,
    TenderRequirement,
)
from app.models.extraction import ExtractedDocument, ExtractedPage, ExtractionAssessment, PdfMetadata
from app.routes.blueprint import get_blueprint_service
from app.services.blueprint import BlueprintGenerationError, BlueprintService, build_blueprint
from app.services.chunking import TextChunk, create_page_aware_chunks
from app.services.gemini import GeminiServiceError, GoogleGeminiProvider
from app.services.normalization import normalize_operator, normalize_requirement_value


def source(page: int, excerpt: str = "Minimum turnover INR 2 crore") -> SourceReference:
    return SourceReference(page_number=page, excerpt=excerpt)


def extracted_document(pages: list[str]) -> ExtractedDocument:
    page_models = [
        ExtractedPage(page_number=index, text=text, character_count=len(text), word_count=len(text.split()))
        for index, text in enumerate(pages, start=1)
    ]
    data = "".join(pages).encode()
    return ExtractedDocument(
        filename="tender.pdf",
        sha256=hashlib.sha256(data).hexdigest(),
        page_count=len(pages),
        total_characters=sum(len(page) for page in pages),
        total_words=sum(len(page.split()) for page in pages),
        text_pages=len(pages),
        empty_pages=0,
        assessment=ExtractionAssessment.TEXT_EXTRACTABLE,
        metadata=PdfMetadata(),
        pages=page_models,
    )


def test_blueprint_and_requirement_schemas_are_strict() -> None:
    requirement = TenderRequirement(
        requirement_id="FIN-001",
        category=RequirementCategory.FINANCIAL,
        raw_text="Minimum turnover INR 2 crore",
        normalized_text="Minimum turnover INR 2 crore",
        requirement_type=RequirementType.MONEY,
        mandatory=True,
        source_references=[source(1)],
        confidence=0.9,
    )
    blueprint = TenderBlueprint(source_filename="tender.pdf", source_sha256="a" * 64, requirements=[requirement])
    assert blueprint.requirements[0].requirement_id == "FIN-001"
    with pytest.raises(ValidationError):
        TenderBlueprint.model_validate({"source_filename": "x.pdf", "source_sha256": "a" * 64, "invented": True})


def test_required_document_and_evaluation_schema_validation() -> None:
    candidates = ChunkCandidates.model_validate(
        {
            "required_documents": [{"name": "Audited statements", "source_references": [{"page_number": 2, "excerpt": "Audited statements"}], "confidence": 0.8}],
            "evaluation_stages": [{"name": "Technical evaluation", "stage_type": "TECHNICAL", "source_references": [{"page_number": 3, "excerpt": "Technical evaluation"}], "confidence": 0.8, "criteria": [{"name": "Approach", "raw_rule": "Up to 20 marks", "maximum_score": 20, "source_references": [{"page_number": 3, "excerpt": "Up to 20 marks"}], "confidence": 0.8}]}],
        }
    )
    assert candidates.required_documents[0].name == "Audited statements"
    assert candidates.evaluation_stages[0].criteria[0].maximum_score == 20


def test_page_aware_chunking_preserves_provenance_and_splits_large_pages() -> None:
    pages = extracted_document(["A" * 8, "B" * 15]).pages
    chunks = create_page_aware_chunks(pages, 10)
    assert [chunk.chunk_id for chunk in chunks] == ["CHUNK-0001", "CHUNK-0002", "CHUNK-0003"]
    assert chunks[0].page_numbers == frozenset({1})
    assert chunks[1].page_numbers == frozenset({2})
    assert chunks[2].page_numbers == frozenset({2})


@pytest.mark.parametrize(
    ("text", "value", "currency", "unit"),
    [
        ("Minimum turnover INR 2,50,000", "250000", "INR", None),
        ("At least Rs. 5 lakh", "500000", "INR", None),
        ("Not less than INR 2 crore", "20000000", "INR", None),
        ("Maximum 25 percent", "25", None, "percent"),
    ],
)
def test_deterministic_financial_and_percentage_normalization(text: str, value: str, currency: str | None, unit: str | None) -> None:
    normalized = normalize_requirement_value(text)
    assert normalized.value == value
    assert normalized.currency == currency
    assert normalized.unit == unit


def test_operator_date_duration_and_boolean_normalization() -> None:
    assert normalize_operator("not more than 30 days") == "<="
    assert normalize_requirement_value("Submission by 25-Oct-2026").value == "2026-10-25"
    assert normalize_requirement_value("At least 36 months").unit == "month"
    assert normalize_requirement_value("The bidder shall submit the form").value is True


def test_deduplication_preserves_sources_and_stable_ids() -> None:
    first = CandidateRequirement(category=RequirementCategory.FINANCIAL, raw_text="Minimum turnover INR 2 crore", requirement_type=RequirementType.MONEY, mandatory=True, source_references=[source(1)], confidence=0.8)
    second = first.model_copy(update={"source_references": [source(5)], "confidence": 0.9})
    document = CandidateDocument(name="Audited statements", mandatory=True, source_references=[source(2, "Audited statements")], confidence=0.8)
    candidates = [ChunkCandidates(requirements=[first]), ChunkCandidates(requirements=[second], required_documents=[document])]
    blueprint = build_blueprint(extracted_document(["one", "two", "three", "four", "five"]), candidates)
    assert [item.requirement_id for item in blueprint.requirements] == ["FIN-001"]
    assert [item.page_number for item in blueprint.requirements[0].source_references] == [1, 5]
    assert blueprint.required_documents[0].document_id == "DOC-001"


def test_uncertain_conflicting_requirement_is_marked_for_review() -> None:
    first = CandidateRequirement(category=RequirementCategory.ELIGIBILITY, raw_text="Registration is required", mandatory=True, source_references=[source(1, "Registration is required")], confidence=0.7)
    second = first.model_copy(update={"mandatory": False, "source_references": [source(2, "Registration is required")]})
    blueprint = build_blueprint(extracted_document(["one", "two"]), [ChunkCandidates(requirements=[first, second])])
    assert blueprint.requirements[0].mandatory is None
    assert blueprint.requirements[0].requires_review is True


def test_malformed_output_retries_once_then_succeeds_without_network() -> None:
    provider = GoogleGeminiProvider(None, "test-model", max_attempts=2)
    responses = iter(["not-json", ChunkCandidates().model_dump_json()])
    provider._generate_override = lambda _prompt: next(responses)
    result = provider.extract_chunk(TextChunk("CHUNK-0001", ()))
    assert result.requirements == []


def test_malformed_output_stops_after_bounded_attempts() -> None:
    provider = GoogleGeminiProvider(None, "test-model", max_attempts=2)
    calls = 0

    def invalid(_prompt: str) -> str:
        nonlocal calls
        calls += 1
        return "not-json"

    provider._generate_override = invalid
    with pytest.raises(GeminiServiceError, match="malformed structured output"):
        provider.extract_chunk(TextChunk("CHUNK-0001", ()))
    assert calls == 2


class FakeBlueprintService:
    def generate(self, document: ExtractedDocument) -> TenderBlueprint:
        return TenderBlueprint(source_filename=document.filename, source_sha256=document.sha256)


def make_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Offline mocked Blueprint endpoint test content.")
    data = document.tobytes()
    document.close()
    return data


def test_blueprint_endpoint_validation_and_mocked_success() -> None:
    app.dependency_overrides[get_blueprint_service] = lambda: FakeBlueprintService()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        invalid = client.post("/blueprint/tender", files={"file": ("bad.txt", b"bad", "text/plain")})
        assert invalid.status_code == 415
        response = client.post("/blueprint/tender", files={"file": ("tender.pdf", make_pdf(), "application/pdf")})
        assert response.status_code == 200
        assert BlueprintResponse.model_validate(response.json()).blueprint.source_filename == "tender.pdf"
    finally:
        app.dependency_overrides.clear()


def test_blueprint_endpoint_handles_mocked_service_error() -> None:
    class FailingService:
        def generate(self, _document: ExtractedDocument) -> TenderBlueprint:
            raise GeminiServiceError("Gemini candidate extraction failed")

    app.dependency_overrides[get_blueprint_service] = lambda: FailingService()
    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/blueprint/tender", files={"file": ("tender.pdf", make_pdf(), "application/pdf")}
        )
        assert response.status_code == 502
        assert response.json() == {"detail": "Gemini candidate extraction failed"}
    finally:
        app.dependency_overrides.clear()


def test_blueprint_service_rejects_ungrounded_page_reference() -> None:
    class FakeProvider:
        def extract_chunk(self, _chunk: TextChunk) -> ChunkCandidates:
            return ChunkCandidates(
                requirements=[CandidateRequirement(category=RequirementCategory.OTHER, raw_text="Tender rule text is meaningful", source_references=[source(99, "Tender rule text")], confidence=0.5)]
            )

    service = BlueprintService(FakeProvider(), 1000)
    with pytest.raises(BlueprintGenerationError, match="outside its source chunk"):
        service.generate(extracted_document(["Tender rule text is meaningful"]))
