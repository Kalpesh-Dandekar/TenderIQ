import hashlib
import re
from collections.abc import Iterable
from typing import Protocol

from app.models.blueprint import (
    CandidateDocument,
    CandidateRequirement,
    ChunkCandidates,
    RequirementType,
    SourceReference,
    TenderBlueprint,
)
from app.models.document_intelligence import CandidateType, LocalCandidate, LocalDocumentAnalysis, ProcessingMetrics, ResolutionCapability
from app.models.extraction import ExtractedDocument
from app.models.hybrid_blueprint import (
    BlueprintMode,
    GeminiUsage,
    GeminiWorkUnit,
    GroundedContext,
    HybridBlueprintResult,
    LocalBlueprintDraft,
    WorkUnitReason,
    WorkUnitResult,
)
from app.services.blueprint import BlueprintGenerationError, BlueprintService, _validate_grounding, build_blueprint
from app.services.chunking import PageSegment, TextChunk
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.gemini import GeminiServiceError

PROMPT_VERSION = "hybrid-v2"
DEFAULT_CONTEXT_BUDGET_RATIO = 0.8
_COVERAGE_TERMS = re.compile(
    r"\b(eligibility|qualification|evaluation|score|marks|turnover|supporting document|documentary evidence|information security|data security|commercial terms?|contract conditions?|liquidated damages)\b",
    re.IGNORECASE,
)


class HybridCandidateProvider(Protocol):
    def finalize_work_unit(self, work_unit: GeminiWorkUnit) -> WorkUnitResult: ...


class HybridBlueprintError(Exception):
    pass


def _sources(candidate: LocalCandidate) -> list[SourceReference]:
    return [evidence.source_reference for evidence in candidate.evidence]


def _requirement_type(candidate: LocalCandidate) -> RequirementType:
    mapping = {
        CandidateType.MONEY: RequirementType.MONEY,
        CandidateType.PERCENTAGE: RequirementType.PERCENTAGE,
        CandidateType.DATE: RequirementType.DATE,
        CandidateType.DURATION: RequirementType.DURATION,
        CandidateType.QUANTITATIVE: RequirementType.NUMERIC,
        CandidateType.MANDATORY_SIGNAL: RequirementType.BOOLEAN,
    }
    return mapping.get(candidate.candidate_type, RequirementType.TEXT)


def _as_requirement(candidate: LocalCandidate, requires_review: bool | None = None) -> CandidateRequirement:
    return CandidateRequirement(
        category=candidate.category,
        raw_text=candidate.raw_text,
        requirement_type=_requirement_type(candidate),
        mandatory=candidate.mandatory_signal,
        source_references=_sources(candidate),
        confidence=candidate.confidence,
        requires_review=candidate.ambiguous if requires_review is None else requires_review,
    )


def _as_document(candidate: LocalCandidate, requires_review: bool | None = None) -> CandidateDocument:
    return CandidateDocument(
        name=candidate.raw_text,
        document_type="SUPPORTING_DOCUMENT",
        mandatory=candidate.mandatory_signal,
        purpose="Evidence explicitly referenced by the source clause",
        source_references=_sources(candidate),
        confidence=candidate.confidence,
        requires_review=candidate.ambiguous if requires_review is None else requires_review,
    )


def build_local_draft(analysis: LocalDocumentAnalysis) -> LocalBlueprintDraft:
    local_requirements: list[CandidateRequirement] = []
    local_documents: list[CandidateDocument] = []
    unresolved: list[LocalCandidate] = []
    for candidate in analysis.candidates:
        if candidate.resolution_capability != ResolutionCapability.LOCAL_DETERMINISTIC:
            unresolved.append(candidate)
        elif candidate.candidate_type == CandidateType.DOCUMENT_EVIDENCE:
            local_documents.append(_as_document(candidate, False))
        else:
            local_requirements.append(_as_requirement(candidate, False))
    return LocalBlueprintDraft(
        analysis=analysis,
        local_requirements=local_requirements,
        local_documents=local_documents,
        unresolved_candidates=unresolved,
    )


def _context_for_section(analysis: LocalDocumentAnalysis, section_id: str) -> list[GroundedContext]:
    target = next(section for section in analysis.sections if section.section_id == section_id)
    return [GroundedContext(page_number=target.page_numbers[0], section_id=target.section_id, heading=target.heading, text=target.text)] if target.text else []


def _work_unit_id(document_sha256: str, reason: WorkUnitReason, section_ids: list[str], candidate_ids: list[str], context: list[GroundedContext]) -> str:
    identity = "|".join(
        [document_sha256, PROMPT_VERSION, reason.value, *section_ids, *candidate_ids]
        + [f"{item.page_number}:{item.section_id}:{hashlib.sha256(item.text.encode()).hexdigest()}" for item in context]
    )
    return f"WU-{hashlib.sha256(identity.encode()).hexdigest()[:20]}"


def create_work_units(draft: LocalBlueprintDraft) -> list[GeminiWorkUnit]:
    section_map = {section.section_id: section for section in draft.analysis.sections}
    by_region: dict[tuple[int, str], list[LocalCandidate]] = {}
    for candidate in draft.unresolved_candidates:
        section_id = candidate.evidence[0].section_id
        section = section_map[section_id]
        by_region.setdefault((section.page_numbers[0], section.category.value), []).append(candidate)

    units: dict[str, GeminiWorkUnit] = {}
    claimed_sections: set[str] = set()
    for _region, candidates in by_region.items():
        candidate_sections = list(dict.fromkeys(candidate.evidence[0].section_id for candidate in candidates))
        context = [item for section_id in candidate_sections for item in _context_for_section(draft.analysis, section_id) if section_id not in claimed_sections]
        claimed_sections.update(candidate_sections)
        if not context:
            continue
        section_ids = list(dict.fromkeys(item.section_id for item in context))
        pages = sorted(set(item.page_number for item in context))
        unit_id = _work_unit_id(
            draft.analysis.source_sha256, WorkUnitReason.UNRESOLVED_CANDIDATES, section_ids,
            [candidate.candidate_id for candidate in candidates], context,
        )
        units.setdefault(
            unit_id,
            GeminiWorkUnit(
                work_unit_id=unit_id,
                prompt_version=PROMPT_VERSION,
                document_sha256=draft.analysis.source_sha256,
                reason=WorkUnitReason.UNRESOLVED_CANDIDATES,
                section_ids=section_ids,
                page_numbers=pages,
                context=context,
                candidates=candidates,
            ),
        )

    represented_sections = {section_id for unit in units.values() for section_id in unit.section_ids}
    for section in draft.analysis.sections:
        substantive = len(section.text.split()) >= 8 and re.search(r"\b(shall|must|required|criteria|score|marks|submit|provide|minimum|maximum)\b", section.text, re.IGNORECASE)
        coverage_relevant = not section.is_table_of_contents and substantive and (section.relevance_confidence >= 0.75 or _COVERAGE_TERMS.search(section.text) is not None)
        if section.section_id in represented_sections or not coverage_relevant or not section.text.strip():
            continue
        has_candidate = any(evidence.section_id == section.section_id for candidate in draft.analysis.candidates for evidence in candidate.evidence)
        if has_candidate:
            continue
        context = _context_for_section(draft.analysis, section.section_id)
        section_ids = list(dict.fromkeys(item.section_id for item in context))
        pages = sorted(set(item.page_number for item in context))
        unit_id = _work_unit_id(draft.analysis.source_sha256, WorkUnitReason.COVERAGE_SAFEGUARD, section_ids, [], context)
        units.setdefault(
            unit_id,
            GeminiWorkUnit(
                work_unit_id=unit_id,
                prompt_version=PROMPT_VERSION,
                document_sha256=draft.analysis.source_sha256,
                reason=WorkUnitReason.COVERAGE_SAFEGUARD,
                section_ids=section_ids,
                page_numbers=pages,
                context=context,
            ),
        )
    return list(units.values())


def _grounding_chunk(work_unit: GeminiWorkUnit) -> TextChunk:
    by_page: dict[int, list[str]] = {}
    for context in work_unit.context:
        by_page.setdefault(context.page_number, []).append(context.text)
    segments = tuple(PageSegment(page_number=page, text="\n".join(texts)) for page, texts in sorted(by_page.items()))
    return TextChunk(chunk_id=work_unit.work_unit_id, segments=segments)


def _fallback_candidates(candidates: Iterable[LocalCandidate]) -> ChunkCandidates:
    requirements: list[CandidateRequirement] = []
    documents: list[CandidateDocument] = []
    for candidate in candidates:
        if candidate.candidate_type == CandidateType.DOCUMENT_EVIDENCE:
            documents.append(_as_document(candidate, True))
        else:
            requirements.append(_as_requirement(candidate, True))
    return ChunkCandidates(requirements=requirements, required_documents=documents)


def _source_identity(source: SourceReference) -> tuple[int, str]:
    return source.page_number, " ".join(source.excerpt.casefold().split())


def _preserve_unrepresented(work_unit: GeminiWorkUnit, result: ChunkCandidates) -> ChunkCandidates:
    returned_sources = {
        _source_identity(source)
        for item in [*result.requirements, *result.required_documents, *result.evaluation_stages]
        for source in item.source_references
    }
    for stage in result.evaluation_stages:
        returned_sources.update(_source_identity(source) for criterion in stage.criteria for source in criterion.source_references)
    unrepresented = [
        candidate
        for candidate in work_unit.candidates
        if not any(_source_identity(source) in returned_sources for source in _sources(candidate))
    ]
    conflicts: list[LocalCandidate] = []
    for candidate in work_unit.candidates:
        if candidate.mandatory_signal is None:
            continue
        candidate_sources = {_source_identity(source) for source in _sources(candidate)}
        matching = [
            item
            for item in result.requirements
            if candidate.category == item.category
            and candidate_sources & {_source_identity(source) for source in item.source_references}
        ]
        if any(item.mandatory is not None and item.mandatory != candidate.mandatory_signal for item in matching):
            conflicts.append(candidate)
    preserved = _fallback_candidates(unrepresented)
    preserved.requirements.extend(_as_requirement(candidate, True) for candidate in conflicts)
    return preserved


def _merge_usage(metrics: ProcessingMetrics, usage: GeminiUsage) -> ProcessingMetrics:
    input_tokens = metrics.gemini_input_tokens
    output_tokens = metrics.gemini_output_tokens
    if usage.input_tokens is not None:
        input_tokens = (input_tokens or 0) + usage.input_tokens
    if usage.output_tokens is not None:
        output_tokens = (output_tokens or 0) + usage.output_tokens
    return metrics.model_copy(
        update={
            "gemini_request_count": metrics.gemini_request_count + usage.request_count,
            "gemini_retry_count": metrics.gemini_retry_count + usage.retry_count,
            "gemini_input_tokens": input_tokens,
            "gemini_output_tokens": output_tokens,
        }
    )


class HybridBlueprintService:
    def __init__(
        self,
        local_service: LocalDocumentIntelligenceService,
        provider: HybridCandidateProvider,
        full_llm_service: BlueprintService,
        context_budget_ratio: float = DEFAULT_CONTEXT_BUDGET_RATIO,
    ) -> None:
        if not 0 < context_budget_ratio <= 1:
            raise ValueError("context_budget_ratio must be greater than 0 and no more than 1")
        self._local_service = local_service
        self._provider = provider
        self._full_llm_service = full_llm_service
        self._context_budget_ratio = context_budget_ratio

    def generate(self, document: ExtractedDocument, mode: BlueprintMode = BlueprintMode.HYBRID) -> TenderBlueprint:
        if mode == BlueprintMode.FULL_LLM:
            return self._full_llm_service.generate(document)
        return self.generate_with_metrics(document).blueprint

    def generate_with_metrics(self, document: ExtractedDocument) -> HybridBlueprintResult:
        try:
            analysis = self._local_service.analyze(document)
        except Exception as error:
            raise HybridBlueprintError("Local document intelligence failed") from error
        draft = build_local_draft(analysis)
        work_units = create_work_units(draft)
        unique_context = {
            (context.section_id, hashlib.sha256(context.text.encode()).hexdigest()): len(context.text)
            for unit in work_units
            for context in unit.context
        }
        context_budget = int(document.total_characters * self._context_budget_ratio)
        planned_characters = sum(unit.context_characters for unit in work_units)
        outputs: list[ChunkCandidates] = []
        metrics = analysis.metrics.model_copy(
            update={
                "uncovered_safeguard_work_units": sum(unit.reason == WorkUnitReason.COVERAGE_SAFEGUARD for unit in work_units),
                "total_llm_work_units": len(work_units),
                "llm_context_characters": planned_characters,
                "unique_llm_context_characters": sum(unique_context.values()),
                "context_budget_characters": context_budget,
                "context_budget_exceeded": planned_characters > context_budget,
            }
        )
        submitted: set[str] = set()
        for unit in work_units:
            if unit.work_unit_id in submitted:
                continue
            submitted.add(unit.work_unit_id)
            result: WorkUnitResult | None = None
            try:
                result = self._provider.finalize_work_unit(unit)
                _validate_grounding(result.candidates, _grounding_chunk(unit))
                preserved = _preserve_unrepresented(unit, result.candidates)
                outputs.append(result.candidates)
                if preserved.requirements or preserved.required_documents:
                    outputs.append(preserved)
                metrics = _merge_usage(metrics, result.usage)
            except (GeminiServiceError, BlueprintGenerationError) as error:
                outputs.append(_fallback_candidates(unit.candidates))
                failure_usage = result.usage if result is not None else GeminiUsage(
                    request_count=getattr(error, "request_count", 1),
                    retry_count=getattr(error, "retry_count", 0),
                )
                metrics = _merge_usage(
                    metrics,
                    failure_usage,
                )

        local = ChunkCandidates(requirements=draft.local_requirements, required_documents=draft.local_documents)
        blueprint = build_blueprint(document, [local, *outputs])
        return HybridBlueprintResult(blueprint=blueprint, draft=draft, work_units=work_units, metrics=metrics)
