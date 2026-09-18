import hashlib
from collections.abc import Callable

from app.models.blueprint import (
    CandidateDocument,
    CandidateEvaluationStage,
    CandidateRequirement,
    ChunkCandidates,
    RequirementCategory,
    SourceReference,
    TenderBlueprint,
)
from app.models.extraction import ExtractedDocument, ExtractedPage, ExtractionAssessment, PdfMetadata
from app.models.hybrid_blueprint import BlueprintMode, GeminiUsage, GeminiWorkUnit, WorkUnitReason, WorkUnitResult
from app.services.blueprint import BlueprintService
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.gemini import GeminiServiceError
from app.services.hybrid_blueprint import HybridBlueprintService, create_work_units


def document(*pages: str) -> ExtractedDocument:
    models = [
        ExtractedPage(page_number=index, text=text, character_count=len(text), word_count=len(text.split()))
        for index, text in enumerate(pages, start=1)
    ]
    content = "".join(pages).encode()
    return ExtractedDocument(
        filename="synthetic-tender.pdf",
        sha256=hashlib.sha256(content).hexdigest(),
        page_count=len(pages),
        total_characters=sum(len(page) for page in pages),
        total_words=sum(len(page.split()) for page in pages),
        text_pages=len(pages),
        empty_pages=0,
        assessment=ExtractionAssessment.TEXT_EXTRACTABLE,
        metadata=PdfMetadata(),
        pages=models,
    )


class RecordingProvider:
    def __init__(self, resolver: Callable[[GeminiWorkUnit], ChunkCandidates] | None = None, usage: GeminiUsage | None = None) -> None:
        self.calls: list[GeminiWorkUnit] = []
        self.resolver = resolver or (lambda _unit: ChunkCandidates())
        self.usage = usage or GeminiUsage()

    def finalize_work_unit(self, work_unit: GeminiWorkUnit) -> WorkUnitResult:
        self.calls.append(work_unit)
        return WorkUnitResult(candidates=self.resolver(work_unit), usage=self.usage)


class RecordingLegacyService:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, source: ExtractedDocument) -> TenderBlueprint:
        self.calls += 1
        return TenderBlueprint(source_filename=source.filename, source_sha256=source.sha256)


def service(provider: RecordingProvider, legacy: RecordingLegacyService | None = None) -> HybridBlueprintService:
    return HybridBlueprintService(LocalDocumentIntelligenceService(), provider, legacy or RecordingLegacyService())  # type: ignore[arg-type]


def test_deterministic_candidates_bypass_gemini() -> None:
    provider = RecordingProvider()
    result = service(provider).generate_with_metrics(document("FINANCIAL QUALIFICATION\nThe bidder must have turnover of at least INR 2 crore."))
    assert provider.calls == []
    assert result.blueprint.requirements[0].normalized.value == "20000000"
    assert result.metrics.gemini_request_count == 0


def test_semantic_candidates_create_grounded_work_units() -> None:
    provider = RecordingProvider()
    result = service(provider).generate_with_metrics(
        document("TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a robust national-scale support approach.")
    )
    assert len(provider.calls) == 1
    unit = provider.calls[0]
    assert unit.candidates[0].raw_text in unit.context[0].text
    assert unit.page_numbers == [1]
    assert result.metrics.total_llm_work_units == 1
    assert result.blueprint.requirements[0].requires_review is True


def test_related_candidates_in_same_section_are_batched() -> None:
    provider = RecordingProvider()
    service(provider).generate_with_metrics(
        document(
            "TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a scalable architecture. "
            "The bidder should demonstrate an effective governance approach."
        )
    )
    assert len(provider.calls) == 1
    assert len(provider.calls[0].candidates) == 2


def test_unrelated_sections_are_not_batched() -> None:
    provider = RecordingProvider()
    service(provider).generate_with_metrics(
        document(
            "TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a scalable architecture.\n"
            "COMMERCIAL TERMS\nThe bidder should demonstrate a sustainable commercial approach."
        )
    )
    assert len(provider.calls) == 2
    assert provider.calls[0].work_unit_id != provider.calls[1].work_unit_id


def test_evaluation_signal_routes_as_unresolved_semantic_candidate() -> None:
    provider = RecordingProvider()
    result = service(provider).generate_with_metrics(
        document("EVALUATION CRITERIA\nApproach and methodology carries marks based on the stated scoring table.")
    )
    assert len(provider.calls) == 1
    assert provider.calls[0].reason == WorkUnitReason.UNRESOLVED_CANDIDATES
    assert provider.calls[0].candidates[0].resolution_capability == "LLM_REQUIRED"
    assert result.metrics.uncovered_safeguard_work_units == 0


def test_coverage_safeguard_routes_substantive_section_without_candidate() -> None:
    provider = RecordingProvider()
    result = service(provider).generate_with_metrics(
        document("ELIGIBILITY CRITERIA\nEligibility criteria are contained in the published schedules.")
    )
    assert len(provider.calls) == 1
    assert provider.calls[0].reason == WorkUnitReason.COVERAGE_SAFEGUARD
    assert result.metrics.uncovered_safeguard_work_units == 1


def test_procurement_metadata_page_does_not_create_low_value_safeguard() -> None:
    provider = RecordingProvider()
    service(provider).generate_with_metrics(document("REQUEST FOR PROPOSAL\nReference ABC-2026 issued by Example Authority."))
    assert provider.calls == []


def test_irrelevant_unclassified_text_does_not_trigger_gemini() -> None:
    provider = RecordingProvider()
    service(provider).generate_with_metrics(document("GENERAL BACKGROUND\nWelcome to the project introduction and office location."))
    assert provider.calls == []


def test_deterministic_fact_conflict_becomes_review_required() -> None:
    raw = "The bidder must have turnover of INR 2 crore."

    def conflict(unit: GeminiWorkUnit) -> ChunkCandidates:
        return ChunkCandidates(
            requirements=[
                CandidateRequirement(
                    category=RequirementCategory.FINANCIAL,
                    raw_text=raw,
                    mandatory=False,
                    source_references=[SourceReference(page_number=1, excerpt=raw)],
                    confidence=0.7,
                )
            ]
        )

    provider = RecordingProvider(conflict)
    result = service(provider).generate_with_metrics(
        document(
            "FINANCIAL QUALIFICATION\nThe bidder must have turnover of INR 2 crore.\n"
            "The bidder should demonstrate sustainable financial capacity."
        )
    )
    requirement = next(item for item in result.blueprint.requirements if item.raw_text == raw)
    assert requirement.mandatory is None
    assert requirement.requires_review is True


def test_invented_gemini_reference_is_rejected_and_local_candidate_preserved() -> None:
    def invented(_unit: GeminiWorkUnit) -> ChunkCandidates:
        return ChunkCandidates(
            requirements=[
                CandidateRequirement(
                    category=RequirementCategory.TECHNICAL,
                    raw_text="Invented rule",
                    source_references=[SourceReference(page_number=99, excerpt="Invented rule")],
                    confidence=0.9,
                )
            ]
        )

    result = service(RecordingProvider(invented)).generate_with_metrics(
        document("TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a scalable architecture.")
    )
    assert all(item.raw_text != "Invented rule" for item in result.blueprint.requirements)
    assert result.blueprint.requirements[0].requires_review is True


def test_required_document_finalization() -> None:
    excerpt = "The bidder should provide suitable proof of its security controls."

    def finalize(_unit: GeminiWorkUnit) -> ChunkCandidates:
        return ChunkCandidates(
            required_documents=[
                CandidateDocument(
                    name="Security controls proof",
                    document_type="SECURITY_EVIDENCE",
                    mandatory=None,
                    purpose="Support the security-control claim",
                    source_references=[SourceReference(page_number=1, excerpt=excerpt)],
                    confidence=0.7,
                    requires_review=True,
                )
            ]
        )

    result = service(RecordingProvider(finalize)).generate_with_metrics(document(f"SECURITY REQUIREMENTS\n{excerpt}"))
    assert result.blueprint.required_documents[0].name == "Security controls proof"
    assert result.blueprint.required_documents[0].requires_review is True


def test_evaluation_rule_finalization() -> None:
    excerpt = "Technical approach carries up to 20 marks."

    def finalize(_unit: GeminiWorkUnit) -> ChunkCandidates:
        return ChunkCandidates(
            evaluation_stages=[
                CandidateEvaluationStage(
                    name="Technical evaluation",
                    stage_type="TECHNICAL",
                    source_references=[SourceReference(page_number=1, excerpt=excerpt)],
                    confidence=0.9,
                    raw_rule=excerpt,
                )
            ]
        )

    result = service(RecordingProvider(finalize)).generate_with_metrics(document(f"EVALUATION CRITERIA\n{excerpt}"))
    assert result.blueprint.evaluation_stages[0].raw_rule == excerpt


def test_work_unit_ids_are_deterministic_and_unique() -> None:
    source = document("TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a scalable architecture.")
    local = LocalDocumentIntelligenceService().analyze(source)
    hybrid = service(RecordingProvider())
    first = hybrid.generate_with_metrics(source).work_units
    second = create_work_units(hybrid.generate_with_metrics(source).draft)
    assert [unit.work_unit_id for unit in first] == [unit.work_unit_id for unit in second]
    assert len({unit.work_unit_id for unit in first}) == len(first)


def test_usage_metadata_is_recorded_only_when_supplied() -> None:
    source = document("TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a scalable architecture.")
    supplied = service(RecordingProvider(usage=GeminiUsage(request_count=2, retry_count=1, input_tokens=120, output_tokens=30))).generate_with_metrics(source)
    assert supplied.metrics.gemini_request_count == 2
    assert supplied.metrics.gemini_retry_count == 1
    assert supplied.metrics.gemini_input_tokens == 120
    assert supplied.metrics.gemini_output_tokens == 30
    absent = service(RecordingProvider()).generate_with_metrics(source)
    assert absent.metrics.gemini_input_tokens is None
    assert absent.metrics.gemini_output_tokens is None


def test_hybrid_failure_never_activates_full_llm() -> None:
    class FailingProvider(RecordingProvider):
        def finalize_work_unit(self, work_unit: GeminiWorkUnit) -> WorkUnitResult:
            self.calls.append(work_unit)
            raise GeminiServiceError("mocked failure", request_count=2, retry_count=1)

    legacy = RecordingLegacyService()
    result = service(FailingProvider(), legacy).generate_with_metrics(
        document("TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a scalable architecture.")
    )
    assert legacy.calls == 0
    assert result.blueprint.requirements[0].requires_review is True
    assert result.metrics.gemini_request_count == 2
    assert result.metrics.gemini_retry_count == 1


def test_explicit_full_llm_mode_remains_available() -> None:
    provider = RecordingProvider()
    legacy = RecordingLegacyService()
    source = document("TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a scalable architecture.")
    result = service(provider, legacy).generate(source, BlueprintMode.FULL_LLM)
    assert result.source_sha256 == source.sha256
    assert legacy.calls == 1
    assert provider.calls == []


def test_token_efficiency_without_quality_loss_on_synthetic_tender() -> None:
    financial = "The bidder must have turnover of at least INR 40 crore."
    mandatory_document = "The bidder shall submit audited statements."
    semantic = "The bidder should demonstrate an architecture suitable for national-scale healthcare delivery."
    evaluation = "Technical methodology carries up to 25 marks under the published scoring table."
    irrelevant = "This introductory page describes the office campus, welcome message, and general background."
    source = document(
        f"FINANCIAL QUALIFICATION\n{financial}",
        f"MANDATORY DOCUMENTS\n{mandatory_document}",
        f"TECHNICAL REQUIREMENTS\n{semantic}",
        f"EVALUATION CRITERIA\n{evaluation}",
        f"GENERAL BACKGROUND\n{irrelevant}",
    )

    def finalize(unit: GeminiWorkUnit) -> ChunkCandidates:
        context = "\n".join(item.text for item in unit.context)
        return ChunkCandidates(
            requirements=[
                CandidateRequirement(
                    category=RequirementCategory.TECHNICAL,
                    raw_text=semantic,
                    mandatory=None,
                    source_references=[SourceReference(page_number=3, excerpt=semantic)],
                    confidence=0.8,
                    requires_review=True,
                )
            ] if semantic in context else [],
            evaluation_stages=[
                CandidateEvaluationStage(
                    name="Technical evaluation",
                    stage_type="TECHNICAL",
                    raw_rule=evaluation,
                    source_references=[SourceReference(page_number=4, excerpt=evaluation)],
                    confidence=0.8,
                )
            ] if evaluation in context else [],
        )

    provider = RecordingProvider(finalize)
    result = service(provider).generate_with_metrics(source)
    assert any(item.raw_text == financial for item in result.blueprint.requirements)
    assert any(item.raw_text == semantic for item in result.blueprint.requirements)
    assert any(mandatory_document in item.name for item in result.blueprint.required_documents)
    assert result.blueprint.evaluation_stages[0].raw_rule == evaluation
    sent_context = "\n".join(item.text for unit in provider.calls for item in unit.context)
    assert irrelevant not in sent_context
    assert result.metrics.llm_context_characters < source.total_characters
    assert result.blueprint.source_sha256 == source.sha256


def test_same_region_candidates_share_one_context_work_unit() -> None:
    provider = RecordingProvider()
    result = service(provider).generate_with_metrics(document(
        "ELIGIBILITY CRITERIA\nThe bidder should demonstrate relevant experience. "
        "The bidder should maintain recognized security certifications."
    ))
    assert len(result.work_units) == 1
    assert len(result.work_units[0].candidates) == 2
    assert result.metrics.llm_context_characters == result.metrics.unique_llm_context_characters


def test_toc_occurrence_does_not_drive_semantic_work() -> None:
    provider = RecordingProvider()
    result = service(provider).generate_with_metrics(document(
        "TABLE OF CONTENTS\n1 Eligibility ........ 5\n2 Technical ........ 8\n3 Evaluation ........ 12\n4 Forms ........ 20\n5 Contract ........ 30",
        "ELIGIBILITY CRITERIA\nThe bidder should demonstrate relevant experience.",
    ))
    assert len(result.work_units) == 1
    assert result.work_units[0].page_numbers == [2]


def test_evaluation_formula_region_is_one_semantic_work_unit() -> None:
    provider = RecordingProvider()
    result = service(provider).generate_with_metrics(document(
        "FINAL EVALUATION\nFinancial Score = Lowest Bid Value / Bid Value of Bidder * 100. "
        "The consolidated score shall combine technical score and financial score using the published weightage."
    ))
    assert len(result.work_units) == 1
    assert "Financial Score" in result.work_units[0].context[0].text
