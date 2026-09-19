from enum import StrEnum

from pydantic import Field, model_validator

from app.models.blueprint import ComparisonOperator, RequirementCategory, SourceReference, StrictModel
from app.models.blueprint_evidence import SemanticRequestCategory


class TechnicalRequirementKind(StrEnum):
    SCORED_CRITERION = "SCORED_CRITERION"
    OVERALL_THRESHOLD = "OVERALL_THRESHOLD"
    TECHNICAL_REQUIREMENT = "TECHNICAL_REQUIREMENT"


class TechnicalRequirementResponse(StrictModel):
    kind: TechnicalRequirementKind
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    mandatory: bool | None = None
    maximum_marks: float | None = Field(default=None, ge=0)
    minimum_qualifying_marks: float | None = Field(default=None, ge=0)
    threshold_value: float | None = Field(default=None, ge=0)
    threshold_operator: ComparisonOperator | None = None
    weight_percent: float | None = Field(default=None, ge=0, le=100)
    expected_evidence: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    requires_review: bool = False
    review_reason: str | None = None

    @model_validator(mode="after")
    def validate_review_and_kind(self) -> "TechnicalRequirementResponse":
        if self.requires_review and not self.review_reason:
            raise ValueError("review_reason is required when requires_review is true")
        if self.kind == TechnicalRequirementKind.OVERALL_THRESHOLD and self.threshold_value is None:
            raise ValueError("overall threshold requires threshold_value")
        return self


class TechnicalBlueprintResponse(StrictModel):
    requirements: list[TechnicalRequirementResponse] = Field(default_factory=list)


class GroundedTechnicalRequirement(StrictModel):
    requirement_id: str
    kind: TechnicalRequirementKind
    title: str
    description: str
    mandatory: bool | None = None
    maximum_marks: float | None = Field(default=None, ge=0)
    minimum_qualifying_marks: float | None = Field(default=None, ge=0)
    threshold_value: float | None = Field(default=None, ge=0)
    threshold_operator: ComparisonOperator | None = None
    weight_percent: float | None = Field(default=None, ge=0, le=100)
    expected_evidence: list[str] = Field(default_factory=list)
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


class TechnicalUsage(StrictModel):
    operation: str = "TECHNICAL_BLUEPRINT_SMOKE_TEST"
    model: str
    semantic_category: SemanticRequestCategory = SemanticRequestCategory.TECHNICAL
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


class TechnicalExecutionResult(StrictModel):
    requirements: list[GroundedTechnicalRequirement] = Field(default_factory=list)
    generated_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    unsupported_evidence_handle_count: int = Field(ge=0)
    usage: TechnicalUsage
