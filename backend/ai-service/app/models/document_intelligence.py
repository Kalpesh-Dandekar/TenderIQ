from enum import StrEnum

from pydantic import Field

from app.models.blueprint import NormalizedRequirement, RequirementCategory, SourceReference, StrictModel
from app.models.extraction import ExtractedPage


class CandidateType(StrEnum):
    MONEY = "MONEY"
    PERCENTAGE = "PERCENTAGE"
    DATE = "DATE"
    DURATION = "DURATION"
    QUANTITATIVE = "QUANTITATIVE"
    MANDATORY_SIGNAL = "MANDATORY_SIGNAL"
    DOCUMENT_EVIDENCE = "DOCUMENT_EVIDENCE"
    SEMANTIC = "SEMANTIC"


class ResolutionCapability(StrEnum):
    LOCAL_DETERMINISTIC = "LOCAL_DETERMINISTIC"
    LLM_REQUIRED = "LLM_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class DocumentSection(StrictModel):
    section_id: str
    heading: str | None = None
    text: str
    page_numbers: list[int] = Field(min_length=1)
    category: RequirementCategory = RequirementCategory.OTHER
    relevance_confidence: float = Field(ge=0, le=1)
    is_table_of_contents: bool = False


class CandidateEvidence(StrictModel):
    source_reference: SourceReference
    section_id: str


class LocalCandidate(StrictModel):
    candidate_id: str
    candidate_type: CandidateType
    category: RequirementCategory
    raw_text: str = Field(min_length=1)
    normalized: NormalizedRequirement = Field(default_factory=NormalizedRequirement)
    mandatory_signal: bool | None = None
    evidence: list[CandidateEvidence] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    ambiguous: bool = False
    ambiguity_reason: str | None = None
    resolution_capability: ResolutionCapability


class ProcessingMetrics(StrictModel):
    total_pages: int = Field(ge=0)
    total_extracted_characters: int = Field(ge=0)
    detected_sections: int = Field(ge=0)
    total_candidates: int = Field(ge=0)
    locally_deterministic_candidates: int = Field(ge=0)
    llm_required_candidates: int = Field(ge=0)
    review_required_candidates: int = Field(ge=0)
    relevant_source_characters: int = Field(ge=0)
    potential_llm_context_characters: int = Field(ge=0)
    uncovered_safeguard_work_units: int = Field(default=0, ge=0)
    total_llm_work_units: int = Field(default=0, ge=0)
    llm_context_characters: int = Field(default=0, ge=0)
    unique_llm_context_characters: int = Field(default=0, ge=0)
    context_budget_characters: int | None = Field(default=None, ge=0)
    context_budget_exceeded: bool = False
    gemini_request_count: int = 0
    gemini_retry_count: int = 0
    gemini_input_tokens: int | None = None
    gemini_output_tokens: int | None = None


class LocalDocumentAnalysis(StrictModel):
    analysis_version: str = "1.0"
    source_filename: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pages: list[ExtractedPage]
    sections: list[DocumentSection]
    candidates: list[LocalCandidate]
    metrics: ProcessingMetrics
