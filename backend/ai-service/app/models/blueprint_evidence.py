from enum import StrEnum

from pydantic import Field

from app.models.blueprint import NormalizedRequirement, RequirementCategory, SourceReference, StrictModel
from app.models.document_intelligence import CandidateType, ResolutionCapability


class BlueprintPurpose(StrEnum):
    METADATA_DATES = "METADATA_DATES"
    SCOPE = "SCOPE"
    ELIGIBILITY = "ELIGIBILITY"
    TECHNICAL_REQUIREMENTS = "TECHNICAL_REQUIREMENTS"
    TECHNICAL_EVALUATION = "TECHNICAL_EVALUATION"
    FINANCIAL_COMMERCIAL_EVALUATION = "FINANCIAL_COMMERCIAL_EVALUATION"
    REQUIRED_DOCUMENTS = "REQUIRED_DOCUMENTS"
    SECURITY = "SECURITY"
    COMMERCIAL = "COMMERCIAL"
    CONTRACTUAL = "CONTRACTUAL"
    OTHER_PROCUREMENT = "OTHER_PROCUREMENT"


class EvidenceOrigin(StrEnum):
    CANDIDATE = "CANDIDATE"
    RESIDUAL_CONTEXT = "RESIDUAL_CONTEXT"


class SemanticRequestCategory(StrEnum):
    QUALIFICATION = "QUALIFICATION"
    TECHNICAL = "TECHNICAL"
    COMMERCIAL_FINANCIAL = "COMMERCIAL_FINANCIAL"
    CONTRACTUAL_OTHER = "CONTRACTUAL_OTHER"


class LocalEvidenceHint(StrictModel):
    candidate_id: str
    candidate_type: CandidateType
    category: RequirementCategory
    resolution_capability: ResolutionCapability
    normalized: NormalizedRequirement = Field(default_factory=NormalizedRequirement)
    mandatory_signal: bool | None = None
    confidence: float = Field(ge=0, le=1)
    ambiguity_reason: str | None = None


class BlueprintEvidenceItem(StrictModel):
    evidence_id: str
    origin: EvidenceOrigin
    purpose: BlueprintPurpose
    categories: list[RequirementCategory] = Field(min_length=1)
    text: str = Field(min_length=1)
    source_pages: list[int] = Field(min_length=1)
    source_section_ids: list[str] = Field(min_length=1)
    source_work_unit_ids: list[str] = Field(min_length=1)
    candidate_ids: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(min_length=1)
    local_hints: list[LocalEvidenceHint] = Field(default_factory=list)
    requires_review: bool = False

    @property
    def character_count(self) -> int:
        return len(self.text)


class BlueprintEvidencePackage(StrictModel):
    package_id: str
    primary_purpose: BlueprintPurpose
    categories: list[RequirementCategory] = Field(min_length=1)
    source_pages: list[int] = Field(min_length=1)
    source_section_ids: list[str] = Field(min_length=1)
    source_work_unit_ids: list[str] = Field(min_length=1)
    candidate_ids: list[str] = Field(default_factory=list)
    evidence_items: list[BlueprintEvidenceItem] = Field(min_length=1)
    review_flags: list[str] = Field(default_factory=list)
    context: str = Field(min_length=1)
    character_count: int = Field(ge=1)


class CompactEvidenceRecord(StrictModel):
    handle: str
    evidence_id: str
    source_pages: list[int] = Field(min_length=1)
    text: str = Field(min_length=1)
    requires_review: bool = False
    semantic_hints: list[str] = Field(default_factory=list)


class BlueprintSemanticRequest(StrictModel):
    request_id: str
    category: SemanticRequestCategory
    records: list[CompactEvidenceRecord] = Field(min_length=1)
    compact_context: str = Field(min_length=1)
    character_count: int = Field(ge=1)


class GeminiFacingMetrics(StrictModel):
    semantic_categories: list[SemanticRequestCategory] = Field(default_factory=list)
    future_request_count: int = Field(default=0, ge=0)
    evidence_records: int = Field(default=0, ge=0)
    total_compact_context_characters: int = Field(default=0, ge=0)
    largest_request_characters: int = Field(default=0, ge=0)
    median_request_characters: float = Field(default=0, ge=0)
    review_records: int = Field(default=0, ge=0)
    source_pages_represented: int = Field(default=0, ge=0)


class EvidencePackagingMetrics(StrictModel):
    input_work_units: int = Field(ge=0)
    input_work_unit_characters: int = Field(ge=0)
    evidence_items_before_deduplication: int = Field(ge=0)
    evidence_items_after_deduplication: int = Field(ge=0)
    candidate_derived_evidence: int = Field(ge=0)
    residual_context_evidence: int = Field(ge=0)
    duplicate_evidence_consolidated: int = Field(ge=0)
    confidently_irrelevant_exclusions: int = Field(ge=0)
    preserved_uncertain_evidence: int = Field(ge=0)
    package_count: int = Field(ge=0)
    package_characters: int = Field(ge=0)
    source_pages_represented: int = Field(ge=0)
    source_work_units_represented: int = Field(ge=0)
    review_evidence_preserved: int = Field(ge=0)
    largest_package_characters: int = Field(ge=0)
    median_package_characters: float = Field(ge=0)
    extracted_document_characters: int = Field(ge=0)
    package_to_document_ratio: float = Field(ge=0)
    package_to_work_unit_ratio: float = Field(ge=0)
    estimated_future_requests: int = Field(ge=0)


class BlueprintEvidencePlan(StrictModel):
    packages: list[BlueprintEvidencePackage] = Field(default_factory=list)
    semantic_requests: list[BlueprintSemanticRequest] = Field(default_factory=list)
    metrics: EvidencePackagingMetrics
    gemini_facing_metrics: GeminiFacingMetrics = Field(default_factory=GeminiFacingMetrics)
