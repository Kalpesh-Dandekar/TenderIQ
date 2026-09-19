from typing import Protocol

from app.models.aggregate_blueprint import AggregateBlueprintResult, GroundedSemanticBlueprint
from app.models.blueprint import CandidateDocument, CandidateRequirement, ChunkCandidates, TenderBlueprint
from app.models.blueprint_evidence import BlueprintEvidencePlan, SemanticRequestCategory
from app.models.commercial_financial_blueprint import CommercialFinancialExecutionResult
from app.models.contractual_other_blueprint import ContractualOtherExecutionResult
from app.models.document_intelligence import CandidateType
from app.models.extraction import ExtractedDocument
from app.models.hybrid_blueprint import BlueprintMode, LocalBlueprintDraft
from app.models.qualification_blueprint import QualificationExecutionResult
from app.models.technical_blueprint import TechnicalExecutionResult
from app.services.blueprint import BlueprintService, build_blueprint
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.evidence_packager import BlueprintEvidencePackager
from app.services.hybrid_blueprint import _as_document, _as_requirement, build_local_draft, create_work_units


class QualificationEngine(Protocol):
    def execute(self, plan: BlueprintEvidencePlan) -> QualificationExecutionResult: ...


class TechnicalEngine(Protocol):
    def execute(self, plan: BlueprintEvidencePlan) -> TechnicalExecutionResult: ...


class CommercialFinancialEngine(Protocol):
    def execute(self, plan: BlueprintEvidencePlan) -> CommercialFinancialExecutionResult: ...


class ContractualEngine(Protocol):
    def execute(self, plan: BlueprintEvidencePlan) -> ContractualOtherExecutionResult: ...


class AggregateBlueprintService:
    def __init__(
        self,
        local_service: LocalDocumentIntelligenceService,
        packager: BlueprintEvidencePackager,
        qualification: QualificationEngine,
        technical: TechnicalEngine,
        commercial_financial: CommercialFinancialEngine,
        contractual: ContractualEngine,
        full_llm_service: BlueprintService,
    ) -> None:
        self._local_service = local_service
        self._packager = packager
        self._qualification = qualification
        self._technical = technical
        self._commercial_financial = commercial_financial
        self._contractual = contractual
        self._full_llm_service = full_llm_service

    def generate(
        self, document: ExtractedDocument, mode: BlueprintMode = BlueprintMode.HYBRID
    ) -> AggregateBlueprintResult:
        if mode == BlueprintMode.FULL_LLM:
            return AggregateBlueprintResult(blueprint=self._full_llm_service.generate(document))

        analysis = self._local_service.analyze(document)
        draft = build_local_draft(analysis)
        work_units = create_work_units(draft)
        plan = self._packager.package(draft, work_units, document.total_characters)
        categories = {request.category for request in plan.semantic_requests}

        qualification = self._execute_if_present(
            SemanticRequestCategory.QUALIFICATION, categories, self._qualification, plan
        )
        technical = self._execute_if_present(SemanticRequestCategory.TECHNICAL, categories, self._technical, plan)
        commercial = self._execute_if_present(
            SemanticRequestCategory.COMMERCIAL_FINANCIAL, categories, self._commercial_financial, plan
        )
        contractual = self._execute_if_present(
            SemanticRequestCategory.CONTRACTUAL_OTHER, categories, self._contractual, plan
        )

        semantics = GroundedSemanticBlueprint(
            qualification_requirements=qualification.requirements if qualification else [],
            technical_requirements=technical.requirements if technical else [],
            commercial_financial_rules=commercial.rules if commercial else [],
            contractual_rules=contractual.rules if contractual else [],
        )
        represented_candidates = {
            candidate_id
            for collection in (
                semantics.qualification_requirements,
                semantics.technical_requirements,
                semantics.commercial_financial_rules,
                semantics.contractual_rules,
            )
            for item in collection
            for candidate_id in item.candidate_ids
        }
        baseline = self._build_baseline(document, draft, represented_candidates)
        return AggregateBlueprintResult(blueprint=baseline, grounded_semantics=semantics)

    @staticmethod
    def _execute_if_present(category, categories, engine, plan):
        return engine.execute(plan) if category in categories else None

    @staticmethod
    def _build_baseline(
        document: ExtractedDocument, draft: LocalBlueprintDraft, represented_candidates: set[str]
    ) -> TenderBlueprint:
        requirements: list[CandidateRequirement] = list(draft.local_requirements)
        documents: list[CandidateDocument] = list(draft.local_documents)
        for candidate in draft.unresolved_candidates:
            if candidate.candidate_type == CandidateType.DOCUMENT_EVIDENCE:
                documents.append(_as_document(candidate, True))
            elif candidate.candidate_id not in represented_candidates:
                requirements.append(_as_requirement(candidate, True))
        return build_blueprint(document, [ChunkCandidates(requirements=requirements, required_documents=documents)])
