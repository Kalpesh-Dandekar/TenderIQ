from enum import StrEnum

from pydantic import Field, model_validator

from app.models.blueprint import ComparisonOperator, RequirementCategory, SourceReference, StrictModel
from app.models.blueprint_evidence import SemanticRequestCategory


class CommercialFinancialRuleKind(StrEnum):
    FINANCIAL_SCORE_FORMULA = "FINANCIAL_SCORE_FORMULA"
    WEIGHTED_SCORE_FORMULA = "WEIGHTED_SCORE_FORMULA"
    COMMERCIAL_RULE = "COMMERCIAL_RULE"
    FINANCIAL_REQUIREMENT = "FINANCIAL_REQUIREMENT"


class FormulaVariableRole(StrEnum):
    LOWEST_VALID_BID = "LOWEST_VALID_BID"
    BIDDER_BID_VALUE = "BIDDER_BID_VALUE"
    FINANCIAL_SCORE = "FINANCIAL_SCORE"
    TECHNICAL_SCORE = "TECHNICAL_SCORE"
    CONSOLIDATED_SCORE = "CONSOLIDATED_SCORE"
    TECHNICAL_WEIGHT = "TECHNICAL_WEIGHT"
    FINANCIAL_WEIGHT = "FINANCIAL_WEIGHT"


class FormulaSemantics(StrEnum):
    RATIO_PERCENT = "RATIO_PERCENT"
    WEIGHTED_SUM = "WEIGHTED_SUM"


class CommercialFinancialRuleResponse(StrictModel):
    kind: CommercialFinancialRuleKind
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    mandatory: bool | None = None
    formula_expression: str | None = None
    formula_variables: list[FormulaVariableRole] = Field(default_factory=list)
    formula_semantics: FormulaSemantics | None = None
    formula_multiplier: float | None = None
    technical_weight_percent: float | None = Field(default=None, ge=0, le=100)
    financial_weight_percent: float | None = Field(default=None, ge=0, le=100)
    percentage_value: float | None = Field(default=None, ge=0, le=100)
    money_value: str | None = None
    currency: str | None = None
    operator: ComparisonOperator | None = None
    unit: str | None = None
    expected_evidence: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    requires_review: bool = False
    review_reason: str | None = None

    @model_validator(mode="after")
    def validate_review(self) -> "CommercialFinancialRuleResponse":
        if self.requires_review and not self.review_reason:
            raise ValueError("review_reason is required when requires_review is true")
        return self


class CommercialFinancialBlueprintResponse(StrictModel):
    rules: list[CommercialFinancialRuleResponse] = Field(default_factory=list)


class GroundedCommercialFinancialRule(StrictModel):
    rule_id: str
    kind: CommercialFinancialRuleKind
    title: str
    description: str
    mandatory: bool | None = None
    formula_expression: str | None = None
    formula_variables: list[FormulaVariableRole] = Field(default_factory=list)
    formula_semantics: FormulaSemantics | None = None
    formula_multiplier: float | None = None
    technical_weight_percent: float | None = Field(default=None, ge=0, le=100)
    financial_weight_percent: float | None = Field(default=None, ge=0, le=100)
    percentage_value: float | None = Field(default=None, ge=0, le=100)
    money_value: str | None = None
    currency: str | None = None
    operator: ComparisonOperator | None = None
    unit: str | None = None
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


class CommercialFinancialUsage(StrictModel):
    operation: str = "COMMERCIAL_FINANCIAL_BLUEPRINT_SMOKE_TEST"
    model: str
    semantic_category: SemanticRequestCategory = SemanticRequestCategory.COMMERCIAL_FINANCIAL
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


class CommercialFinancialExecutionResult(StrictModel):
    rules: list[GroundedCommercialFinancialRule] = Field(default_factory=list)
    generated_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    unsupported_evidence_handle_count: int = Field(ge=0)
    usage: CommercialFinancialUsage
