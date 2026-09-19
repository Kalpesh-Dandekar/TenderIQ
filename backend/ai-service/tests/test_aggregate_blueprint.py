from types import SimpleNamespace

from app.models.aggregate_blueprint import AggregateBlueprintResponse
from app.models.blueprint import (
    CandidateDocument, CandidateRequirement, NormalizedRequirement, RequirementCategory, RequirementType,
    SourceReference, TenderBlueprint,
)
from app.models.commercial_financial_blueprint import (
    CommercialFinancialRuleKind, FormulaSemantics, FormulaVariableRole, GroundedCommercialFinancialRule,
)
from app.models.contractual_other_blueprint import (
    ContractualParty, ContractualRuleKind, GroundedContractualRule, ObligationSemantics,
)
from app.models.document_intelligence import CandidateEvidence, CandidateType, LocalCandidate, ResolutionCapability
from app.models.extraction import ExtractedDocument, ExtractedPage, ExtractionAssessment, PdfMetadata
from app.models.hybrid_blueprint import BlueprintMode
from app.models.qualification_blueprint import GroundedQualificationRequirement
from app.models.technical_blueprint import GroundedTechnicalRequirement, TechnicalRequirementKind
from app.services.aggregate_blueprint import AggregateBlueprintService


def source(page: int, excerpt: str, section: str = "Section") -> SourceReference:
    return SourceReference(page_number=page, section=section, excerpt=excerpt)


def document() -> ExtractedDocument:
    page = ExtractedPage(page_number=1, text="Grounded tender text", character_count=20, word_count=3)
    return ExtractedDocument(
        filename="tender.pdf", sha256="a" * 64, page_count=1, total_characters=20, total_words=3,
        text_pages=1, empty_pages=0, assessment=ExtractionAssessment.TEXT_EXTRACTABLE,
        metadata=PdfMetadata(), pages=[page],
    )


class Engine:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = 0

    def execute(self, _plan):
        self.calls += 1
        return self.result


class Packager:
    def __init__(self, categories) -> None:
        self.plan = SimpleNamespace(semantic_requests=[SimpleNamespace(category=value) for value in categories])

    def package(self, *_args):
        return self.plan


class FullLlm:
    def generate(self, value):
        return TenderBlueprint(source_filename=value.filename, source_sha256=value.sha256)


def candidate(candidate_id: str, category=RequirementCategory.ELIGIBILITY, kind=CandidateType.SEMANTIC):
    return LocalCandidate(
        candidate_id=candidate_id, candidate_type=kind, category=category, raw_text=f"Requirement {candidate_id}",
        mandatory_signal=True, evidence=[CandidateEvidence(source_reference=source(1, candidate_id), section_id="S-1")],
        confidence=.8, resolution_capability=ResolutionCapability.LLM_REQUIRED,
    )


def test_aggregate_exposes_grounded_categories_and_preserves_baseline(monkeypatch) -> None:
    qualification_item = GroundedQualificationRequirement(
        requirement_id="QREQ-1", category=RequirementCategory.ELIGIBILITY,
        requirement_type=RequirementType.MONEY, title="Turnover", requirement_text="Minimum turnover",
        mandatory=True, normalized=NormalizedRequirement(value="400000000", operator=">=", currency="INR"),
        evidence_handles=["E1"], evidence_ids=["EVI-1"], source_pages=[20, 21], source_section_ids=["S20", "S21"],
        source_work_unit_ids=["WU-1"], candidate_ids=["C-Q"],
        source_references=[source(20, "Minimum turnover", "Eligibility"), source(21, "Audited turnover", "Schedule")],
        source_categories=[RequirementCategory.ELIGIBILITY], requires_review=True,
        review_reason="Confirm the applicable financial-year period",
    )
    technical_items = [
        GroundedTechnicalRequirement(
            requirement_id="TREQ-1", kind=TechnicalRequirementKind.SCORED_CRITERION, title="Experience",
            description="Relevant experience", maximum_marks=20, minimum_qualifying_marks=12,
            evidence_handles=["E2"], evidence_ids=["EVI-2"], source_pages=[27], source_section_ids=["S27"],
            source_work_unit_ids=["WU-2"], candidate_ids=["C-T1"], source_references=[source(27, "20 12", "Technical")],
            source_categories=[RequirementCategory.TECHNICAL],
        ),
        GroundedTechnicalRequirement(
            requirement_id="TREQ-2", kind=TechnicalRequirementKind.OVERALL_THRESHOLD, title="Technical threshold",
            description="Minimum technical score", threshold_value=65, threshold_operator=">=",
            evidence_handles=["E3"], evidence_ids=["EVI-3"], source_pages=[28], source_section_ids=["S28"],
            source_work_unit_ids=["WU-2"], candidate_ids=["C-T2"], source_references=[source(28, "65 marks", "Technical")],
            source_categories=[RequirementCategory.TECHNICAL],
        ),
        GroundedTechnicalRequirement(
            requirement_id="TREQ-3", kind=TechnicalRequirementKind.TECHNICAL_REQUIREMENT, title="Methodology",
            description="Provide methodology", mandatory=True, expected_evidence=["Methodology"],
            evidence_handles=["E4"], evidence_ids=["EVI-4"], source_pages=[16], source_section_ids=["S16"],
            source_work_unit_ids=["WU-2"], candidate_ids=["C-T3"], source_references=[source(16, "Provide methodology", "Scope")],
            source_categories=[RequirementCategory.TECHNICAL],
        ),
    ]
    commercial_items = [
        GroundedCommercialFinancialRule(
            rule_id="CFR-1", kind=CommercialFinancialRuleKind.FINANCIAL_SCORE_FORMULA, title="Financial score",
            description="Financial score formula", formula_expression="(LOWEST_VALID_BID/BIDDER_BID_VALUE)*100",
            formula_variables=[FormulaVariableRole.LOWEST_VALID_BID, FormulaVariableRole.BIDDER_BID_VALUE],
            formula_semantics=FormulaSemantics.RATIO_PERCENT, formula_multiplier=100,
            evidence_handles=["E5"], evidence_ids=["EVI-5"], source_pages=[24], source_section_ids=["S24"],
            source_work_unit_ids=["WU-3"], candidate_ids=["C-C1"], source_references=[source(24, "Financial Score", "Financial")],
            source_categories=[RequirementCategory.FINANCIAL],
        ),
        GroundedCommercialFinancialRule(
            rule_id="CFR-2", kind=CommercialFinancialRuleKind.WEIGHTED_SCORE_FORMULA, title="Consolidated score",
            description="Weighted score formula", formula_expression="TECHNICAL_SCORE*0.70+FINANCIAL_SCORE*0.30",
            formula_variables=[FormulaVariableRole.TECHNICAL_SCORE, FormulaVariableRole.FINANCIAL_SCORE],
            formula_semantics=FormulaSemantics.WEIGHTED_SUM, technical_weight_percent=70, financial_weight_percent=30,
            evidence_handles=["E6"], evidence_ids=["EVI-6"], source_pages=[24], source_section_ids=["S24"],
            source_work_unit_ids=["WU-3"], candidate_ids=["C-C2"], source_references=[source(24, "70 30", "Financial")],
            source_categories=[RequirementCategory.FINANCIAL],
        ),
    ]
    contractual_items = [
        GroundedContractualRule(
            rule_id="COR-1", kind=ContractualRuleKind.TERMINATION_REMEDY, title="Termination",
            description="Client may terminate", responsible_party=ContractualParty.CLIENT,
            obligation_semantics=ObligationSemantics.RIGHT, mandatory=False,
            evidence_handles=["E7"], evidence_ids=["EVI-7"], source_pages=[37], source_section_ids=["S37"],
            source_work_unit_ids=["WU-4"], candidate_ids=["C-O1"], source_references=[source(37, "may terminate", "Termination")],
            source_categories=[RequirementCategory.CONTRACTUAL],
        ),
        GroundedContractualRule(
            rule_id="COR-2", kind=ContractualRuleKind.LIABILITY_INDEMNITY, title="Indemnity",
            description="Bidder should indemnify", responsible_party=ContractualParty.BIDDER,
            obligation_semantics=ObligationSemantics.SHOULD, mandatory=False,
            evidence_handles=["E8"], evidence_ids=["EVI-8"], source_pages=[35], source_section_ids=["S35"],
            source_work_unit_ids=["WU-4"], candidate_ids=["C-O2"], source_references=[source(35, "should indemnify", "Indemnity")],
            source_categories=[RequirementCategory.CONTRACTUAL], requires_review=True,
            review_reason="Advisory modality requires review",
        ),
        GroundedContractualRule(
            rule_id="COR-3", kind=ContractualRuleKind.CONTRACTUAL_OBLIGATION, title="Contract signing",
            description="Expected to be signed", responsible_party=None, obligation_semantics=None,
            evidence_handles=["E9"], evidence_ids=["EVI-9"], source_pages=[31], source_section_ids=["S31"],
            source_work_unit_ids=["WU-4"], candidate_ids=["C-O3"], source_references=[source(31, "expected to be signed", "Contract")],
            source_categories=[RequirementCategory.CONTRACTUAL],
        ),
    ]
    results = [
        SimpleNamespace(requirements=[qualification_item]), SimpleNamespace(requirements=technical_items),
        SimpleNamespace(rules=commercial_items), SimpleNamespace(rules=contractual_items),
    ]
    engines = [Engine(result) for result in results]
    categories = [
        "QUALIFICATION", "TECHNICAL", "COMMERCIAL_FINANCIAL", "CONTRACTUAL_OTHER",
    ]
    draft = SimpleNamespace(
        local_requirements=[CandidateRequirement(
            category=RequirementCategory.SECURITY, raw_text="Local security requirement", mandatory=True,
            source_references=[source(10, "Local security requirement")], confidence=.95,
        )],
        local_documents=[CandidateDocument(
            name="Registration certificate", mandatory=True, source_references=[source(20, "Registration certificate")],
            confidence=.9,
        )],
        unresolved_candidates=[
            candidate("C-Q"), candidate("C-OMIT"),
            candidate("C-DOC", RequirementCategory.DOCUMENT, CandidateType.DOCUMENT_EVIDENCE),
        ],
    )
    monkeypatch.setattr("app.services.aggregate_blueprint.build_local_draft", lambda _analysis: draft)
    monkeypatch.setattr("app.services.aggregate_blueprint.create_work_units", lambda _draft: [])
    service = AggregateBlueprintService(
        SimpleNamespace(analyze=lambda _document: object()), Packager(categories), *engines, FullLlm()
    )

    result = service.generate(document())
    response = AggregateBlueprintResponse(blueprint=result.blueprint, grounded_semantics=result.grounded_semantics)
    semantics = response.grounded_semantics
    assert semantics is not None
    assert semantics.qualification_requirements[0].review_reason == "Confirm the applicable financial-year period"
    assert [item.page_number for item in semantics.qualification_requirements[0].source_references] == [20, 21]
    assert semantics.technical_requirements[0].maximum_marks == 20
    assert semantics.technical_requirements[1].threshold_value == 65
    assert semantics.technical_requirements[2].expected_evidence == ["Methodology"]
    assert semantics.commercial_financial_rules[0].formula_multiplier == 100
    assert semantics.commercial_financial_rules[1].technical_weight_percent == 70
    assert semantics.commercial_financial_rules[1].financial_weight_percent == 30
    assert semantics.contractual_rules[0].obligation_semantics == ObligationSemantics.RIGHT
    assert semantics.contractual_rules[1].obligation_semantics == ObligationSemantics.SHOULD
    assert semantics.contractual_rules[1].review_reason == "Advisory modality requires review"
    assert semantics.contractual_rules[2].responsible_party is None
    assert semantics.contractual_rules[2].obligation_semantics is None
    assert all(engine.calls == 1 for engine in engines)
    assert len(response.blueprint.requirements) == 2
    assert any(item.raw_text == "Requirement C-OMIT" for item in response.blueprint.requirements)
    assert all(item.raw_text != "Requirement C-Q" for item in response.blueprint.requirements)
    assert len(response.blueprint.required_documents) == 2
    assert response.model_dump()["blueprint"]["source_filename"] == "tender.pdf"


def test_missing_semantic_categories_do_not_execute_or_crash(monkeypatch) -> None:
    engines = [Engine(SimpleNamespace(requirements=[])), Engine(SimpleNamespace(requirements=[])),
               Engine(SimpleNamespace(rules=[])), Engine(SimpleNamespace(rules=[]))]
    draft = SimpleNamespace(local_requirements=[], local_documents=[], unresolved_candidates=[])
    monkeypatch.setattr("app.services.aggregate_blueprint.build_local_draft", lambda _analysis: draft)
    monkeypatch.setattr("app.services.aggregate_blueprint.create_work_units", lambda _draft: [])
    service = AggregateBlueprintService(
        SimpleNamespace(analyze=lambda _document: object()), Packager([]), *engines, FullLlm()
    )
    result = service.generate(document())
    assert result.grounded_semantics is not None
    assert result.grounded_semantics.qualification_requirements == []
    assert all(engine.calls == 0 for engine in engines)


def test_full_llm_remains_backward_compatible_and_skips_semantic_engines() -> None:
    engines = [Engine(None) for _ in range(4)]
    service = AggregateBlueprintService(SimpleNamespace(), Packager([]), *engines, FullLlm())
    result = service.generate(document(), BlueprintMode.FULL_LLM)
    assert result.blueprint.source_filename == "tender.pdf"
    assert result.grounded_semantics is None
    assert all(engine.calls == 0 for engine in engines)
