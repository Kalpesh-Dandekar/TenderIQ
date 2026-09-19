from enum import StrEnum

from pydantic import Field, model_validator

from app.models.blueprint import ComparisonOperator, RequirementCategory, SourceReference, StrictModel
from app.models.blueprint_evidence import SemanticRequestCategory


class ContractualRuleKind(StrEnum):
    CONTRACTUAL_OBLIGATION = "CONTRACTUAL_OBLIGATION"
    SERVICE_LEVEL = "SERVICE_LEVEL"
    DELIVERY_REQUIREMENT = "DELIVERY_REQUIREMENT"
    LEGAL_COMPLIANCE = "LEGAL_COMPLIANCE"
    CONFIDENTIALITY_DATA_PROTECTION = "CONFIDENTIALITY_DATA_PROTECTION"
    INTELLECTUAL_PROPERTY = "INTELLECTUAL_PROPERTY"
    LIABILITY_INDEMNITY = "LIABILITY_INDEMNITY"
    TERMINATION_REMEDY = "TERMINATION_REMEDY"
    DISPUTE_GOVERNANCE = "DISPUTE_GOVERNANCE"
    TRANSITION_SUPPORT = "TRANSITION_SUPPORT"
    OTHER_REQUIREMENT = "OTHER_REQUIREMENT"


class ContractualParty(StrEnum):
    BIDDER = "BIDDER"
    VENDOR = "VENDOR"
    SELECTED_BIDDER = "SELECTED_BIDDER"
    SERVICE_PROVIDER = "SERVICE_PROVIDER"
    PURCHASER = "PURCHASER"
    CLIENT = "CLIENT"
    AUTHORITY = "AUTHORITY"
    BOTH_PARTIES = "BOTH_PARTIES"
    OTHER = "OTHER"


class ObligationSemantics(StrEnum):
    MUST = "MUST"
    MUST_NOT = "MUST_NOT"
    MAY = "MAY"
    SHOULD = "SHOULD"
    CONDITIONAL = "CONDITIONAL"
    RIGHT = "RIGHT"


class DurationUnit(StrEnum):
    HOUR = "HOUR"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    YEAR = "YEAR"


class ContractualRuleResponse(StrictModel):
    kind: ContractualRuleKind
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    responsible_party: ContractualParty | None = None
    beneficiary_or_counterparty: ContractualParty | None = None
    obligation_semantics: ObligationSemantics | None = None
    action_or_obligation: str | None = None
    condition: str | None = None
    operator: ComparisonOperator | None = None
    numeric_value: float | None = None
    percentage_value: float | None = Field(default=None, ge=0, le=100)
    money_value: str | None = None
    currency: str | None = None
    duration_value: float | None = Field(default=None, ge=0)
    duration_unit: DurationUnit | None = None
    deadline_or_timing: str | None = None
    consequence_or_remedy: str | None = None
    mandatory: bool | None = None
    expected_evidence: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    requires_review: bool = False
    review_reason: str | None = None

    @model_validator(mode="after")
    def validate_review_and_duration(self) -> "ContractualRuleResponse":
        if self.requires_review and not self.review_reason:
            raise ValueError("review_reason is required when requires_review is true")
        if (self.duration_value is None) != (self.duration_unit is None):
            raise ValueError("duration value and unit must be supplied together")
        return self


class ContractualOtherBlueprintResponse(StrictModel):
    rules: list[ContractualRuleResponse] = Field(default_factory=list)


class GroundedContractualRule(ContractualRuleResponse):
    rule_id: str
    evidence_handles: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    source_pages: list[int] = Field(min_length=1)
    source_section_ids: list[str] = Field(min_length=1)
    source_work_unit_ids: list[str] = Field(min_length=1)
    candidate_ids: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(min_length=1)
    source_categories: list[RequirementCategory] = Field(min_length=1)


class ContractualOtherUsage(StrictModel):
    operation: str = "CONTRACTUAL_OTHER_BLUEPRINT_SMOKE_TEST"
    model: str
    semantic_category: SemanticRequestCategory = SemanticRequestCategory.CONTRACTUAL_OTHER
    request_ids: list[str] = Field(min_length=1)
    evidence_record_count: int = Field(ge=0)
    input_characters: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0)
    request_count: int = Field(ge=1)
    retry_count: int = Field(default=0, ge=0)
    success: bool


class ContractualOtherExecutionResult(StrictModel):
    rules: list[GroundedContractualRule] = Field(default_factory=list)
    generated_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    unsupported_evidence_handle_count: int = Field(ge=0)
    usage: ContractualOtherUsage
