from pydantic import Field

from app.models.blueprint import StrictModel, TenderBlueprint
from app.models.commercial_financial_blueprint import GroundedCommercialFinancialRule
from app.models.contractual_other_blueprint import GroundedContractualRule
from app.models.qualification_blueprint import GroundedQualificationRequirement
from app.models.technical_blueprint import GroundedTechnicalRequirement


class GroundedSemanticBlueprint(StrictModel):
    qualification_requirements: list[GroundedQualificationRequirement] = Field(default_factory=list)
    technical_requirements: list[GroundedTechnicalRequirement] = Field(default_factory=list)
    commercial_financial_rules: list[GroundedCommercialFinancialRule] = Field(default_factory=list)
    contractual_rules: list[GroundedContractualRule] = Field(default_factory=list)


class AggregateBlueprintResult(StrictModel):
    blueprint: TenderBlueprint
    grounded_semantics: GroundedSemanticBlueprint | None = None


class AggregateBlueprintResponse(StrictModel):
    success: bool = True
    blueprint: TenderBlueprint
    grounded_semantics: GroundedSemanticBlueprint | None = None
