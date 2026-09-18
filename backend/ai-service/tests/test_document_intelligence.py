import hashlib

from app.models.document_intelligence import CandidateType, ResolutionCapability
from app.models.extraction import ExtractedDocument, ExtractedPage, ExtractionAssessment, PdfMetadata
from app.services.document_intelligence import LocalDocumentIntelligenceService, detect_sections


def document(*pages: str) -> ExtractedDocument:
    extracted_pages = [
        ExtractedPage(page_number=index, text=text, character_count=len(text), word_count=len(text.split()))
        for index, text in enumerate(pages, start=1)
    ]
    content = "".join(pages).encode()
    return ExtractedDocument(
        filename="document.pdf",
        sha256=hashlib.sha256(content).hexdigest(),
        page_count=len(pages),
        total_characters=sum(len(page) for page in pages),
        total_words=sum(len(page.split()) for page in pages),
        text_pages=sum(bool(page.strip()) for page in pages),
        empty_pages=sum(not page.strip() for page in pages),
        assessment=ExtractionAssessment.TEXT_EXTRACTABLE,
        metadata=PdfMetadata(),
        pages=extracted_pages,
    )


def analyze(*pages: str):
    return LocalDocumentIntelligenceService().analyze(document(*pages))


def test_section_and_heading_detection_preserves_page_provenance() -> None:
    analysis = analyze("1. ELIGIBILITY CRITERIA\nThe bidder shall be registered.\nGeneral explanatory text.")
    assert analysis.sections[0].heading == "1. ELIGIBILITY CRITERIA"
    assert analysis.sections[0].page_numbers == [1]
    assert analysis.sections[0].category == "ELIGIBILITY"
    assert analysis.pages[0].text.endswith("General explanatory text.")


def test_unknown_content_remains_available() -> None:
    text = "Background narrative with no procurement classification."
    sections = detect_sections(document(text).pages)
    assert sections[0].category == "OTHER"
    assert text in sections[0].text


def test_financial_lakh_and_crore_candidates_are_normalized() -> None:
    analysis = analyze(
        "FINANCIAL QUALIFICATION\nThe bidder must have turnover of INR 40 crore.\nBid security shall be Rs. 5 lakh."
    )
    values = {candidate.normalized.value for candidate in analysis.candidates}
    assert "400000000" in values
    assert "500000" in values
    assert all(candidate.category == "FINANCIAL" for candidate in analysis.candidates)


def test_percentage_date_duration_and_operator_extraction() -> None:
    analysis = analyze(
        "QUALIFICATION CRITERIA\nMinimum 25 percent local content is required.\nSubmission shall be by 25-Oct-2026.\nThe bidder must have at least 5 years experience."
    )
    candidates = analysis.candidates
    assert any(item.candidate_type == CandidateType.PERCENTAGE and item.normalized.value == "25" for item in candidates)
    assert any(item.candidate_type == CandidateType.DATE and item.normalized.value == "2026-10-25" for item in candidates)
    duration = next(item for item in candidates if item.candidate_type == CandidateType.DURATION)
    assert duration.normalized.value == "5"
    assert duration.normalized.operator == ">="


def test_plain_quantitative_threshold_is_normalized() -> None:
    analysis = analyze("TECHNICAL REQUIREMENTS\nThe bidder shall complete at least 3 projects.")
    candidate = analysis.candidates[0]
    assert candidate.candidate_type == CandidateType.QUANTITATIVE
    assert candidate.normalized.value == "3"
    assert candidate.normalized.unit == "project"
    assert candidate.resolution_capability == ResolutionCapability.LOCAL_DETERMINISTIC


def test_mandatory_document_signal_is_grounded_and_local() -> None:
    analysis = analyze("MANDATORY DOCUMENTS\nThe bidder shall submit audited statements.")
    candidate = analysis.candidates[0]
    assert candidate.candidate_type == CandidateType.DOCUMENT_EVIDENCE
    assert candidate.mandatory_signal is True
    assert candidate.resolution_capability == ResolutionCapability.LOCAL_DETERMINISTIC
    assert candidate.evidence[0].source_reference.page_number == 1
    assert candidate.evidence[0].source_reference.excerpt == candidate.raw_text
    assert candidate.evidence[0].source_reference.section == "MANDATORY DOCUMENTS"


def test_semantic_requirement_routes_to_llm() -> None:
    analysis = analyze(
        "TECHNICAL REQUIREMENTS\nThe bidder should demonstrate substantial experience implementing comparable national-scale platforms."
    )
    candidate = analysis.candidates[0]
    assert candidate.candidate_type == CandidateType.SEMANTIC
    assert candidate.resolution_capability == ResolutionCapability.LLM_REQUIRED
    assert candidate.ambiguous is True


def test_negated_requirement_is_not_marked_mandatory() -> None:
    analysis = analyze("DOCUMENTS\nThe bidder is not required to submit a registration certificate.")
    candidate = analysis.candidates[0]
    assert candidate.mandatory_signal is False
    assert candidate.resolution_capability == ResolutionCapability.REVIEW_REQUIRED
    assert candidate.ambiguous is True


def test_historical_amount_is_not_a_bidder_threshold() -> None:
    analysis = analyze("BACKGROUND\nThe previous supplier had five years of experience and a contract value of INR 8 crore.")
    candidate = analysis.candidates[0]
    assert candidate.normalized.value == "80000000"
    assert candidate.resolution_capability == ResolutionCapability.REVIEW_REQUIRED
    assert candidate.mandatory_signal is None


def test_estimated_project_value_is_not_turnover_requirement() -> None:
    analysis = analyze("PROJECT OVERVIEW\nThe estimated project cost is INR 40 crore.")
    candidate = analysis.candidates[0]
    assert candidate.category == "FINANCIAL"
    assert candidate.resolution_capability == ResolutionCapability.REVIEW_REQUIRED
    assert candidate.ambiguous is True
    assert candidate.mandatory_signal is None


def test_preference_language_is_not_mandatory() -> None:
    analysis = analyze("ELIGIBILITY\nPreference may be given to bidders with prior public-sector work.")
    candidate = analysis.candidates[0]
    assert candidate.mandatory_signal is False
    assert candidate.resolution_capability == ResolutionCapability.REVIEW_REQUIRED


def test_processing_metrics_and_zero_gemini_usage() -> None:
    analysis = analyze(
        "FINANCIAL QUALIFICATION\nThe bidder must have turnover of at least INR 2 crore.",
        "TECHNICAL REQUIREMENTS\nThe bidder should demonstrate a robust support approach.",
    )
    metrics = analysis.metrics
    assert metrics.total_pages == 2
    assert metrics.total_candidates == 2
    assert metrics.locally_deterministic_candidates == 1
    assert metrics.llm_required_candidates == 1
    assert metrics.review_required_candidates == 0
    assert metrics.relevant_source_characters > 0
    assert metrics.potential_llm_context_characters > 0
    assert metrics.gemini_request_count == 0
    assert metrics.gemini_retry_count == 0
    assert metrics.gemini_input_tokens is None
    assert metrics.gemini_output_tokens is None


def test_analysis_is_deterministic_and_reusable() -> None:
    source = document("ELIGIBILITY\nThe bidder shall provide a registration certificate.")
    service = LocalDocumentIntelligenceService()
    first = service.analyze(source)
    second = service.analyze(source)
    assert first == second
    assert first.pages == source.pages
    assert first.candidates[0].candidate_id == "LOCAL-0001"


def test_multiple_iso_standards_are_preserved_in_one_semantic_clause() -> None:
    analysis = analyze("ELIGIBILITY CRITERIA\nThe bidder should have obtained ISO 9001 and ISO 27001 certifications.")
    matches = [candidate for candidate in analysis.candidates if "ISO 9001" in candidate.raw_text]
    assert len(matches) == 1
    assert "ISO 27001" in matches[0].raw_text
    assert matches[0].resolution_capability == ResolutionCapability.LLM_REQUIRED


def test_copyright_license_is_not_document_evidence() -> None:
    analysis = analyze("INTELLECTUAL PROPERTY\nNothing herein grants any license under copyright.")
    assert all(candidate.candidate_type != CandidateType.DOCUMENT_EVIDENCE for candidate in analysis.candidates)


def test_not_exceed_percentage_normalizes_lte() -> None:
    analysis = analyze("CONTRACT TERMS\nLiquidated damages shall not exceed 3%.")
    candidate = next(item for item in analysis.candidates if item.normalized.unit == "percent")
    assert candidate.normalized.value == "3"
    assert candidate.normalized.operator == "<="


def test_bidder_duration_preserves_applicability_and_operator() -> None:
    analysis = analyze("ELIGIBILITY\nThe bidder must have been in operation for at least 5 years.")
    candidate = analysis.candidates[0]
    assert candidate.normalized.value == "5"
    assert candidate.normalized.operator == ">="
    assert candidate.resolution_capability == ResolutionCapability.LOCAL_DETERMINISTIC


def test_turnover_threshold_normalizes_crore_and_operator() -> None:
    analysis = analyze("FINANCIAL QUALIFICATION\nAverage turnover shall not be less than INR 40 crore for the bidder.")
    candidate = analysis.candidates[0]
    assert candidate.normalized.value == "400000000"
    assert candidate.normalized.operator == ">="


def test_specific_comparison_phrases_take_precedence_over_shorter_ones() -> None:
    less = analyze("FINANCIAL\nTurnover shall be less than INR 10 crore.").candidates[0]
    more = analyze("ELIGIBILITY\nThe bidder must have more than 5 years experience.").candidates[0]
    assert less.normalized.operator == "<"
    assert less.normalized.value == "100000000"
    assert more.normalized.operator == ">"
    assert more.normalized.value == "5"


def test_exception_heavy_clause_routes_to_review() -> None:
    analysis = analyze("ELIGIBILITY\nThe bidder shall provide the certificate unless an exemption applies.")
    assert analysis.candidates[0].resolution_capability == ResolutionCapability.REVIEW_REQUIRED


def test_toc_page_does_not_create_candidates() -> None:
    analysis = analyze("TABLE OF CONTENTS\n1 Eligibility ........ 5\n2 Technical ........ 8\n3 Evaluation ........ 12\n4 Forms ........ 20\n5 Contract ........ 30")
    assert analysis.sections[0].is_table_of_contents is True
    assert analysis.candidates == []


def test_structured_eligibility_table_is_not_suppressed_as_toc() -> None:
    analysis = analyze(
        "ELIGIBILITY CRITERIA\n"
        "1 Bidder experience 5\n2 Financial capacity 6\n3 Certifications 7\n"
        "The bidder must have been in operation for at least 5 years.\n"
        "The bidder shall provide supporting documents."
    )
    assert all(section.is_table_of_contents is False for section in analysis.sections)
    assert any("at least 5 years" in candidate.raw_text for candidate in analysis.candidates)


def test_mixed_toc_like_region_preserves_substantive_requirement() -> None:
    analysis = analyze(
        "CONTENTS AND ELIGIBILITY\n"
        "1 Introduction ........ 2\n2 Scope ........ 3\n3 Eligibility ........ 5\n4 Forms ........ 8\n"
        "The bidder shall have minimum turnover of INR 2 crore."
    )
    assert any(section.is_table_of_contents is False for section in analysis.sections)
    assert any(candidate.normalized.value == "20000000" for candidate in analysis.candidates)


def test_mandatory_boolean_does_not_inherit_comparison_operator() -> None:
    analysis = analyze("TECHNICAL REQUIREMENTS\nThe bidder shall provide more than adequate technical support.")
    candidate = analysis.candidates[0]
    assert candidate.normalized.value is True
    assert candidate.normalized.operator is None
