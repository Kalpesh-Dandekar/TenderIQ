from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementCategory(StrEnum):
    ELIGIBILITY = "ELIGIBILITY"
    TECHNICAL = "TECHNICAL"
    FINANCIAL = "FINANCIAL"
    DOCUMENT = "DOCUMENT"
    COMMERCIAL = "COMMERCIAL"
    CONTRACTUAL = "CONTRACTUAL"
    SECURITY = "SECURITY"
    OTHER = "OTHER"


class RequirementType(StrEnum):
    TEXT = "TEXT"
    NUMERIC = "NUMERIC"
    MONEY = "MONEY"
    PERCENTAGE = "PERCENTAGE"
    DATE = "DATE"
    DURATION = "DURATION"
    BOOLEAN = "BOOLEAN"


class ComparisonOperator(StrEnum):
    EQ = "="
    GTE = ">="
    GT = ">"
    LTE = "<="
    LT = "<"


class SourceReference(StrictModel):
    page_number: int = Field(ge=1)
    section: str | None = None
    clause: str | None = None
    excerpt: str = Field(min_length=1, max_length=600)


class NormalizedRequirement(StrictModel):
    value: str | int | float | bool | None = None
    operator: ComparisonOperator | None = None
    unit: str | None = None
    currency: str | None = None
    period: str | None = None


class ImportantDate(StrictModel):
    label: str
    value: str
    source_references: list[SourceReference] = Field(default_factory=list)


class TenderMetadata(StrictModel):
    title: str | None = None
    reference_number: str | None = None
    issuing_organization: str | None = None
    tender_type: str | None = None
    contract_type: str | None = None
    submission_mode: str | None = None
    currency: str | None = None
    important_dates: list[ImportantDate] = Field(default_factory=list)
    bid_validity: str | None = None
    bid_security: str | None = None
    tender_fee: str | None = None
    performance_security: str | None = None


class TenderRequirement(StrictModel):
    requirement_id: str
    category: RequirementCategory
    raw_text: str = Field(min_length=1)
    normalized_text: str
    requirement_type: RequirementType = RequirementType.TEXT
    mandatory: bool | None = None
    normalized: NormalizedRequirement = Field(default_factory=NormalizedRequirement)
    expected_evidence: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False


class RequiredDocument(StrictModel):
    document_id: str
    name: str = Field(min_length=1)
    document_type: str | None = None
    mandatory: bool | None = None
    purpose: str | None = None
    associated_requirement_ids: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False


class EvaluationCriterion(StrictModel):
    criterion_id: str
    name: str
    raw_rule: str
    maximum_score: float | None = None
    minimum_score: float | None = None
    weight_percent: float | None = Field(default=None, ge=0, le=100)
    formula: str | None = None
    disqualification_condition: str | None = None
    source_references: list[SourceReference] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False


class EvaluationStage(StrictModel):
    stage_id: str
    name: str
    sequence: int = Field(ge=1)
    stage_type: str
    raw_rule: str | None = None
    minimum_score: float | None = None
    weight_percent: float | None = Field(default=None, ge=0, le=100)
    formula: str | None = None
    disqualification_conditions: list[str] = Field(default_factory=list)
    criteria: list[EvaluationCriterion] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False


class TenderBlueprint(StrictModel):
    schema_version: str = "1.0"
    source_filename: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    metadata: TenderMetadata = Field(default_factory=TenderMetadata)
    requirements: list[TenderRequirement] = Field(default_factory=list)
    required_documents: list[RequiredDocument] = Field(default_factory=list)
    evaluation_stages: list[EvaluationStage] = Field(default_factory=list)


class BlueprintResponse(StrictModel):
    success: bool = True
    blueprint: TenderBlueprint


class CandidateRequirement(StrictModel):
    category: RequirementCategory
    raw_text: str = Field(min_length=1)
    requirement_type: RequirementType = RequirementType.TEXT
    mandatory: bool | None = None
    expected_evidence: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False


class CandidateDocument(StrictModel):
    name: str = Field(min_length=1)
    document_type: str | None = None
    mandatory: bool | None = None
    purpose: str | None = None
    source_references: list[SourceReference] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False


class CandidateCriterion(StrictModel):
    name: str
    raw_rule: str
    maximum_score: float | None = None
    minimum_score: float | None = None
    weight_percent: float | None = Field(default=None, ge=0, le=100)
    formula: str | None = None
    disqualification_condition: str | None = None
    source_references: list[SourceReference] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False


class CandidateEvaluationStage(StrictModel):
    name: str
    stage_type: str
    raw_rule: str | None = None
    minimum_score: float | None = None
    weight_percent: float | None = Field(default=None, ge=0, le=100)
    formula: str | None = None
    disqualification_conditions: list[str] = Field(default_factory=list)
    criteria: list[CandidateCriterion] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False


class CandidateMetadata(StrictModel):
    title: str | None = None
    reference_number: str | None = None
    issuing_organization: str | None = None
    tender_type: str | None = None
    contract_type: str | None = None
    submission_mode: str | None = None
    currency: str | None = None
    important_dates: list[ImportantDate] = Field(default_factory=list)
    bid_validity: str | None = None
    bid_security: str | None = None
    tender_fee: str | None = None
    performance_security: str | None = None


class ChunkCandidates(StrictModel):
    metadata: CandidateMetadata = Field(default_factory=CandidateMetadata)
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    required_documents: list[CandidateDocument] = Field(default_factory=list)
    evaluation_stages: list[CandidateEvaluationStage] = Field(default_factory=list)
