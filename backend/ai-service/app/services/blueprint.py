import re
from collections.abc import Iterable

from app.models.blueprint import (
    CandidateDocument,
    CandidateEvaluationStage,
    CandidateMetadata,
    CandidateRequirement,
    ChunkCandidates,
    EvaluationCriterion,
    EvaluationStage,
    RequiredDocument,
    SourceReference,
    TenderBlueprint,
    TenderMetadata,
    TenderRequirement,
)
from app.models.extraction import ExtractedDocument
from app.services.chunking import TextChunk, create_page_aware_chunks
from app.services.gemini import CandidateProvider
from app.services.normalization import normalize_requirement_value, normalize_text

_CATEGORY_PREFIX = {
    "ELIGIBILITY": "ELIG",
    "TECHNICAL": "TECH",
    "FINANCIAL": "FIN",
    "DOCUMENT": "DOC",
    "COMMERCIAL": "COMM",
    "CONTRACTUAL": "CONT",
    "SECURITY": "SEC",
    "OTHER": "OTHER",
}


class BlueprintGenerationError(Exception):
    pass


class BlueprintService:
    def __init__(self, provider: CandidateProvider, max_chunk_characters: int) -> None:
        self._provider = provider
        self._max_chunk_characters = max_chunk_characters

    def generate(self, document: ExtractedDocument) -> TenderBlueprint:
        chunks = create_page_aware_chunks(document.pages, self._max_chunk_characters)
        candidates: list[ChunkCandidates] = []
        for chunk in chunks:
            result = self._provider.extract_chunk(chunk)
            _validate_grounding(result, chunk)
            candidates.append(result)
        return build_blueprint(document, candidates)


def _normalized_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _source_key(source: SourceReference) -> tuple[int, str, str, str]:
    return (source.page_number, source.section or "", source.clause or "", normalize_text(source.excerpt).casefold())


def _merge_sources(*groups: Iterable[SourceReference]) -> list[SourceReference]:
    merged: dict[tuple[int, str, str, str], SourceReference] = {}
    for source in (item for group in groups for item in group):
        merged.setdefault(_source_key(source), source)
    return sorted(merged.values(), key=lambda source: (source.page_number, source.section or "", source.clause or ""))


def _validate_sources(sources: list[SourceReference], chunk: TextChunk) -> None:
    page_text = {segment.page_number: segment.text for segment in chunk.segments}
    for source in sources:
        if source.page_number not in chunk.page_numbers:
            raise BlueprintGenerationError("AI output referenced a page outside its source chunk")
        excerpt = normalize_text(source.excerpt).casefold()
        source_text = normalize_text(page_text[source.page_number]).casefold()
        if excerpt not in source_text:
            raise BlueprintGenerationError("AI output included an excerpt not grounded in its source page")


def _validate_grounding(candidates: ChunkCandidates, chunk: TextChunk) -> None:
    for requirement in candidates.requirements:
        _validate_sources(requirement.source_references, chunk)
    for document in candidates.required_documents:
        _validate_sources(document.source_references, chunk)
    for stage in candidates.evaluation_stages:
        _validate_sources(stage.source_references, chunk)
        for criterion in stage.criteria:
            _validate_sources(criterion.source_references, chunk)


def _merge_metadata(items: list[CandidateMetadata]) -> TenderMetadata:
    fields = (
        "title", "reference_number", "issuing_organization", "tender_type", "contract_type", "submission_mode",
        "currency", "bid_validity", "bid_security", "tender_fee", "performance_security",
    )
    values = {field: next((getattr(item, field) for item in items if getattr(item, field)), None) for field in fields}
    dates = []
    seen_dates: set[tuple[str, str]] = set()
    for item in items:
        for date in item.important_dates:
            key = (_normalized_key(date.label), date.value)
            if key not in seen_dates:
                seen_dates.add(key)
                dates.append(date)
    return TenderMetadata(**values, important_dates=dates)


def _merge_requirements(items: list[CandidateRequirement]) -> list[TenderRequirement]:
    grouped: dict[tuple[str, str], CandidateRequirement] = {}
    for item in items:
        key = (item.category.value, _normalized_key(item.raw_text))
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = item
            continue
        raw_text = max((existing.raw_text, item.raw_text), key=len)
        mandatory = existing.mandatory if existing.mandatory == item.mandatory else None
        grouped[key] = existing.model_copy(
            update={
                "raw_text": raw_text,
                "mandatory": mandatory,
                "expected_evidence": list(dict.fromkeys(existing.expected_evidence + item.expected_evidence)),
                "source_references": _merge_sources(existing.source_references, item.source_references),
                "confidence": max(existing.confidence, item.confidence),
                "requires_review": existing.requires_review or item.requires_review or mandatory is None,
            }
        )

    counters: dict[str, int] = {}
    requirements: list[TenderRequirement] = []
    for candidate in grouped.values():
        prefix = _CATEGORY_PREFIX[candidate.category.value]
        counters[prefix] = counters.get(prefix, 0) + 1
        requirements.append(
            TenderRequirement(
                requirement_id=f"{prefix}-{counters[prefix]:03d}",
                category=candidate.category,
                raw_text=candidate.raw_text,
                normalized_text=normalize_text(candidate.raw_text),
                requirement_type=candidate.requirement_type,
                mandatory=candidate.mandatory,
                normalized=normalize_requirement_value(candidate.raw_text),
                expected_evidence=candidate.expected_evidence,
                source_references=candidate.source_references,
                confidence=candidate.confidence,
                requires_review=candidate.requires_review,
            )
        )
    return requirements


def _merge_documents(items: list[CandidateDocument]) -> list[RequiredDocument]:
    grouped: dict[str, CandidateDocument] = {}
    for item in items:
        key = _normalized_key(item.name)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = item
            continue
        mandatory = existing.mandatory if existing.mandatory == item.mandatory else None
        grouped[key] = existing.model_copy(
            update={
                "name": max((existing.name, item.name), key=len),
                "mandatory": mandatory,
                "purpose": existing.purpose or item.purpose,
                "source_references": _merge_sources(existing.source_references, item.source_references),
                "confidence": max(existing.confidence, item.confidence),
                "requires_review": existing.requires_review or item.requires_review or mandatory is None,
            }
        )
    return [
        RequiredDocument(
            document_id=f"DOC-{index:03d}",
            name=item.name,
            document_type=item.document_type,
            mandatory=item.mandatory,
            purpose=item.purpose,
            source_references=item.source_references,
            confidence=item.confidence,
            requires_review=item.requires_review,
        )
        for index, item in enumerate(grouped.values(), start=1)
    ]


def _build_evaluation(items: list[CandidateEvaluationStage]) -> list[EvaluationStage]:
    stages: list[EvaluationStage] = []
    for stage_index, item in enumerate(items, start=1):
        criteria = [
            EvaluationCriterion(
                criterion_id=f"EVAL-{stage_index:03d}-{criterion_index:03d}",
                **criterion.model_dump(),
            )
            for criterion_index, criterion in enumerate(item.criteria, start=1)
        ]
        stage_data = item.model_dump(exclude={"criteria"})
        stages.append(EvaluationStage(stage_id=f"EVAL-{stage_index:03d}", sequence=stage_index, criteria=criteria, **stage_data))
    return stages


def build_blueprint(document: ExtractedDocument, candidates: list[ChunkCandidates]) -> TenderBlueprint:
    return TenderBlueprint(
        source_filename=document.filename,
        source_sha256=document.sha256,
        metadata=_merge_metadata([candidate.metadata for candidate in candidates]),
        requirements=_merge_requirements([item for candidate in candidates for item in candidate.requirements]),
        required_documents=_merge_documents([item for candidate in candidates for item in candidate.required_documents]),
        evaluation_stages=_build_evaluation([item for candidate in candidates for item in candidate.evaluation_stages]),
    )
