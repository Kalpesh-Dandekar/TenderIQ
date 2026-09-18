import hashlib
import re

from app.models.blueprint import NormalizedRequirement, RequirementCategory, SourceReference
from app.models.document_intelligence import CandidateEvidence, CandidateType, LocalCandidate, ResolutionCapability
from app.models.blueprint_evidence import EvidenceOrigin
from app.models.extraction import ExtractedDocument, ExtractedPage, ExtractionAssessment, PdfMetadata
from app.models.hybrid_blueprint import GeminiWorkUnit, GroundedContext, WorkUnitReason
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.evidence_packager import BlueprintEvidencePackager, matching_evidence_pages
from app.services.hybrid_blueprint import build_local_draft, create_work_units


def document(*pages: str) -> ExtractedDocument:
    extracted = [
        ExtractedPage(page_number=index, text=text, character_count=len(text), word_count=len(text.split()))
        for index, text in enumerate(pages, start=1)
    ]
    data = "".join(pages).encode()
    return ExtractedDocument(
        filename="synthetic.pdf",
        sha256=hashlib.sha256(data).hexdigest(),
        page_count=len(pages),
        total_characters=sum(len(page) for page in pages),
        total_words=sum(len(page.split()) for page in pages),
        text_pages=len(pages),
        empty_pages=0,
        assessment=ExtractionAssessment.TEXT_EXTRACTABLE,
        metadata=PdfMetadata(),
        pages=extracted,
    )


def plan(*pages: str, ceiling: int = 24_000, request_ceiling: int = 80_000):
    source = document(*pages)
    analysis = LocalDocumentIntelligenceService().analyze(source)
    draft = build_local_draft(analysis)
    units = create_work_units(draft)
    return BlueprintEvidencePackager(ceiling, request_ceiling).package(draft, units, source.total_characters)


def manual_candidate(text: str, category: RequirementCategory = RequirementCategory.OTHER) -> LocalCandidate:
    source = SourceReference(page_number=1, section="PROCUREMENT NOTES", excerpt=text)
    return LocalCandidate(
        candidate_id="LOCAL-0001",
        candidate_type=CandidateType.SEMANTIC,
        category=category,
        raw_text=text,
        normalized=NormalizedRequirement(),
        evidence=[CandidateEvidence(source_reference=source, section_id="SECTION-0001")],
        confidence=0.5,
        ambiguous=True,
        ambiguity_reason="Semantic interpretation is required",
        resolution_capability=ResolutionCapability.LLM_REQUIRED,
    )


def manual_unit(text: str, candidate: LocalCandidate | None = None) -> GeminiWorkUnit:
    return GeminiWorkUnit(
        work_unit_id="WU-manual",
        prompt_version="hybrid-v2",
        document_sha256="a" * 64,
        reason=WorkUnitReason.UNRESOLVED_CANDIDATES if candidate else WorkUnitReason.COVERAGE_SAFEGUARD,
        section_ids=["SECTION-0001"],
        page_numbers=[1],
        context=[GroundedContext(page_number=1, section_id="SECTION-0001", heading="PROCUREMENT NOTES", text=text)],
        candidates=[candidate] if candidate else [],
    )


def package_manual(unit: GeminiWorkUnit):
    source = document(unit.context[0].text)
    draft = build_local_draft(LocalDocumentIntelligenceService().analyze(source))
    return BlueprintEvidencePackager().package(draft, [unit], source.total_characters)


def test_related_evidence_is_grouped_by_blueprint_purpose() -> None:
    result = plan(
        "ELIGIBILITY CRITERIA\nThe bidder should demonstrate profitable operations in prior years. "
        "The bidder should maintain membership in a recognized industry association."
    )
    assert len(result.packages) == 1
    assert result.packages[0].primary_purpose == "ELIGIBILITY"
    assert len(result.packages[0].evidence_items) == 2


def test_duplicate_evidence_retains_all_source_references() -> None:
    clause = "The bidder should maintain certification by a recognized standards body."
    result = plan(f"ELIGIBILITY\n{clause}", f"ELIGIBILITY\n{clause}")
    assert result.metrics.duplicate_evidence_consolidated == 1
    item = result.packages[0].evidence_items[0]
    assert item.source_pages == [1, 2]
    assert len(item.source_references) == 2
    assert len(item.source_work_unit_ids) == 2


def test_unrelated_domains_are_not_merged_to_reduce_package_count() -> None:
    result = plan(
        "ELIGIBILITY\nThe bidder should demonstrate profitable operations.",
        "SECURITY REQUIREMENTS\nThe bidder should provide an information security undertaking.",
    )
    purposes = {package.primary_purpose.value for package in result.packages}
    assert "ELIGIBILITY" in purposes
    assert "SECURITY" in purposes
    assert len(result.packages) == 2


def test_confidently_irrelevant_metadata_is_excluded() -> None:
    text = "REQUEST FOR PROPOSAL issued by Example Authority. Registered office postal address follows."
    result = package_manual(manual_unit(text))
    assert result.packages == []
    assert result.metrics.confidently_irrelevant_exclusions == 1


def test_other_category_procurement_candidate_is_not_excluded() -> None:
    text = "The supplier should coordinate all transition obligations with the incumbent."
    result = package_manual(manual_unit(text, manual_candidate(text)))
    assert result.metrics.package_count == 1
    assert result.packages[0].evidence_items[0].categories == [RequirementCategory.OTHER]


def test_review_required_evidence_is_preserved() -> None:
    result = plan("ELIGIBILITY\nThe bidder shall provide accreditation unless a statutory exemption applies.")
    assert result.metrics.review_evidence_preserved == 1
    assert result.metrics.preserved_uncertain_evidence == 1
    assert result.packages[0].review_flags


def test_package_splitting_uses_evidence_boundaries_without_truncation() -> None:
    first = "The bidder should demonstrate " + "relevant technical experience " * 10 + "."
    second = "The bidder should demonstrate " + "a comprehensive delivery methodology " * 10 + "."
    result = plan(f"TECHNICAL REQUIREMENTS\n{first} {second}", ceiling=350)
    assert len(result.packages) == 2
    packaged_text = "\n".join(item.text for package in result.packages for item in package.evidence_items)
    assert first in packaged_text
    assert second in packaged_text


def test_every_item_retains_page_section_work_unit_candidate_and_excerpt() -> None:
    result = plan("TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a resilient support methodology.")
    item = result.packages[0].evidence_items[0]
    assert item.source_pages == [1]
    assert item.source_section_ids
    assert item.source_work_unit_ids
    assert item.candidate_ids
    assert item.source_references[0].excerpt in item.text


def test_package_ids_are_deterministic_without_provider_dependency() -> None:
    pages = ("TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a resilient support methodology.",)
    first = plan(*pages)
    second = plan(*pages)
    assert [package.package_id for package in first.packages] == [package.package_id for package in second.packages]
    assert [request.request_id for request in first.semantic_requests] == [request.request_id for request in second.semantic_requests]
    assert first.metrics.estimated_future_requests == len(first.semantic_requests)


def test_representative_blueprint_evidence_survives_packaging() -> None:
    result = plan(
        "ELIGIBILITY\nThe bidder should have at least five years of operation; should show profitability in prior years; "
        "and should demonstrate turnover of INR 40 crore. The bidder should not be blacklisted and should maintain "
        "ISO certification and industry membership.",
        "SECURITY REQUIREMENTS\nThe bidder should provide a data security undertaking.",
        "TECHNICAL EVALUATION\nTechnical approach carries marks with category minimum thresholds and an overall qualifying score.",
        "FINANCIAL EVALUATION\nFinancial Score follows the Lowest Bid Value divided by Bid Value formula. "
        "The consolidated score combines Technical Score and Financial Score using published weightage.",
        "MANDATORY DOCUMENTS\nThe bidder should submit supporting documentary evidence.",
        "ELIGIBILITY EXCEPTION\nThe bidder shall provide accreditation unless a statutory exemption applies.",
    )
    packaged = "\n".join(package.context for package in result.packages).casefold()
    for phrase in (
        "five years", "profitability", "40 crore", "blacklisted", "iso certification", "industry membership",
        "data security undertaking", "category minimum thresholds", "overall qualifying score", "lowest bid value",
        "consolidated score", "supporting documentary evidence", "unless a statutory exemption",
    ):
        assert phrase in packaged


def test_candidate_free_procurement_context_becomes_residual_evidence() -> None:
    text = "Evaluation methodology uses a published qualifying threshold for the technical stage."
    result = package_manual(manual_unit(text))
    item = result.packages[0].evidence_items[0]
    assert item.origin == EvidenceOrigin.RESIDUAL_CONTEXT
    assert item.text == text
    assert item.candidate_ids == []


def test_candidate_and_additional_requirement_in_same_work_unit_both_survive() -> None:
    candidate_text = "The bidder should demonstrate relevant experience."
    additional = "The bidder shall also maintain ISO 27001 certification."
    unit = manual_unit(f"{candidate_text} {additional}", manual_candidate(candidate_text, RequirementCategory.ELIGIBILITY))
    result = package_manual(unit)
    items = [item for package in result.packages for item in package.evidence_items]
    assert any(item.origin == EvidenceOrigin.CANDIDATE and item.text == candidate_text for item in items)
    assert any(item.origin == EvidenceOrigin.RESIDUAL_CONTEXT and additional in item.text for item in items)


def test_candidate_free_financial_formula_survives_packaging() -> None:
    formula = "Financial Score = (Lowest Bid Value / Bid Value of Bidder) * 100"
    result = package_manual(manual_unit(formula))
    assert formula in result.packages[0].context
    assert result.packages[0].primary_purpose == "FINANCIAL_COMMERCIAL_EVALUATION"


def test_candidate_free_certification_clause_survives_packaging() -> None:
    clause = "The bidder shall maintain ISO 9001 and ISO 27001 certifications."
    result = package_manual(manual_unit(clause))
    assert clause in result.packages[0].context
    assert result.metrics.residual_context_evidence == 1


def test_multiline_table_residual_preserves_complete_requirement_context() -> None:
    candidate_text = "The bidder should demonstrate relevant experience."
    table = (
        "ELIGIBILITY CRITERIA\n"
        f"{candidate_text}\n"
        "Minimum turnover\n"
        "INR 40 crore per annum\n"
        "in two of the last three financial years"
    )
    result = package_manual(manual_unit(table, manual_candidate(candidate_text, RequirementCategory.ELIGIBILITY)))
    residual = next(
        item
        for package in result.packages
        for item in package.evidence_items
        if item.origin == EvidenceOrigin.RESIDUAL_CONTEXT
    )
    assert "Minimum turnover\nINR 40 crore per annum\nin two of the last three financial years" in residual.text
    assert residual.source_pages == [1]
    assert residual.source_section_ids == ["SECTION-0001"]
    assert residual.source_work_unit_ids == ["WU-manual"]
    assert residual.candidate_ids == []


def test_fully_represented_candidate_does_not_create_residual_duplicate() -> None:
    text = "The bidder should demonstrate relevant experience."
    result = package_manual(manual_unit(text, manual_candidate(text, RequirementCategory.ELIGIBILITY)))
    items = [item for package in result.packages for item in package.evidence_items]
    assert len(items) == 1
    assert items[0].origin == EvidenceOrigin.CANDIDATE
    assert result.metrics.residual_context_evidence == 0


def test_matching_evidence_pages_do_not_inherit_unrelated_package_pages() -> None:
    result = plan(
        "ELIGIBILITY\nThe bidder should demonstrate five years of operation.",
        "ELIGIBILITY\nThe bidder should demonstrate profitable operations.",
    )
    pages = matching_evidence_pages(result.packages, lambda text: "five years" in text.casefold())
    assert pages == [1]


def test_organization_address_alone_does_not_match_bangalore_condition() -> None:
    result = package_manual(manual_unit("Example Institute, registered office, Bangalore 560001."))
    applicability = re.compile(r"\b(?:bidder|vendor|tenderer|supplier|selected|successful|shall|must|required)\b", re.I)
    location = re.compile(r"\b(?:bangalore|bengaluru)\b", re.I)
    condition = re.compile(r"\b(?:based|located|location|delivery|facility|support|presence|onsite|deployed|stationed)\b", re.I)
    pages = matching_evidence_pages(
        result.packages,
        lambda text: all(pattern.search(text) is not None for pattern in (applicability, location, condition)),
    )
    assert pages == []


def test_semantic_request_batching_uses_four_major_categories() -> None:
    result = plan(
        "ELIGIBILITY\nThe bidder should maintain recognized certification.",
        "TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a resilient architecture.",
        "FINANCIAL EVALUATION\nFinancial Score uses the Lowest Bid Value and Bid Value of the bidder.",
        "CONTRACT CONDITIONS\nThe supplier shall comply with contractual indemnity obligations.",
    )
    assert {request.category.value for request in result.semantic_requests} == {
        "QUALIFICATION", "TECHNICAL", "COMMERCIAL_FINANCIAL", "CONTRACTUAL_OTHER",
    }
    assert result.gemini_facing_metrics.future_request_count == 4


def test_compact_records_hide_verbose_audit_identifiers_but_keep_local_mapping() -> None:
    result = plan("ELIGIBILITY\nThe bidder should maintain recognized certification.")
    request = result.semantic_requests[0]
    record = request.records[0]
    assert record.evidence_id
    assert record.handle in request.compact_context
    assert record.evidence_id not in request.compact_context
    assert "SECTION-" not in request.compact_context
    assert "WU-" not in request.compact_context
    assert "LOCAL-" not in request.compact_context


def test_each_evidence_item_is_transmitted_once() -> None:
    result = plan(
        "ELIGIBILITY\nThe bidder should maintain recognized certification.",
        "SECURITY REQUIREMENTS\nThe bidder should provide an information security undertaking.",
    )
    evidence_ids = [record.evidence_id for request in result.semantic_requests for record in request.records]
    internal_ids = [item.evidence_id for package in result.packages for item in package.evidence_items]
    assert sorted(evidence_ids) == sorted(internal_ids)
    assert len(evidence_ids) == len(set(evidence_ids))


def test_semantic_request_splitting_never_truncates_records() -> None:
    first = "The bidder should demonstrate " + "relevant technical experience " * 10 + "."
    second = "The bidder should demonstrate " + "a comprehensive delivery methodology " * 10 + "."
    result = plan(f"TECHNICAL REQUIREMENTS\n{first} {second}", request_ceiling=350)
    technical = [request for request in result.semantic_requests if request.category.value == "TECHNICAL"]
    assert len(technical) == 2
    transmitted = "\n".join(record.text for request in technical for record in request.records)
    assert first in transmitted
    assert second in transmitted
