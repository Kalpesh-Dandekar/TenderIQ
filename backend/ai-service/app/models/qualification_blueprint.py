from pydantic import Field, model_validator

from app.models.blueprint import (
    ComparisonOperator,
    NormalizedRequirement,
    RequirementCategory,
    RequirementType,
    SourceReference,
    StrictModel,
)
from app.models.blueprint_evidence import SemanticRequestCategory


class QualificationRequirementResponse(StrictModel):
    requirement_type: RequirementType = RequirementType.TEXT
    title: str = Field(min_length=1)
    requirement_text: str = Field(min_length=1)
    mandatory: bool | None = None
    value: str | int | float | bool | None = None
    operator: ComparisonOperator | None = None
    unit: str | None = None
    currency: str | None = None
    period: str | None = None
    evidence_ids: list[str] = Field(min_length=1)
    requires_review: bool = False
    review_reason: str | None = None

    @model_validator(mode="after")
    def review_has_reason(self) -> "QualificationRequirementResponse":
        if self.requires_review and not self.review_reason:
            raise ValueError("review_reason is required when requires_review is true")
        return self


class QualificationBlueprintResponse(StrictModel):
    requirements: list[QualificationRequirementResponse] = Field(default_factory=list)


class GroundedQualificationRequirement(StrictModel):
    requirement_id: str
    category: RequirementCategory
    requirement_type: RequirementType
    title: str
    requirement_text: str
    mandatory: bool | None = None
    normalized: NormalizedRequirement = Field(default_factory=NormalizedRequirement)
    evidence_handles: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    source_pages: list[int] = Field(min_length=1)
    source_section_ids: list[str] = Field(min_length=1)
    source_work_unit_ids: list[str] = Field(min_length=1)
    candidate_ids: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(min_length=1)
    source_categories: list[RequirementCategory] = Field(min_length=1)
    requires_review: bool = False
    review_reason: str | None = None


class QualificationUsage(StrictModel):
    operation: str = "QUALIFICATION_BLUEPRINT_SMOKE_TEST"
    model: str
    semantic_category: SemanticRequestCategory = SemanticRequestCategory.QUALIFICATION
    request_id: str
    evidence_record_count: int = Field(ge=0)
    input_characters: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0)
    request_count: int = Field(default=1, ge=0)
    retry_count: int = Field(default=0, ge=0)
    success: bool


class QualificationExecutionResult(StrictModel):
    requirements: list[GroundedQualificationRequirement] = Field(default_factory=list)
    generated_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    unsupported_evidence_handle_count: int = Field(ge=0)
    usage: QualificationUsage
