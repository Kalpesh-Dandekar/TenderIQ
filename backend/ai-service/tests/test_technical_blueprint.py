import hashlib
import json

import pytest

from app.models.blueprint import NormalizedRequirement, RequirementCategory, SourceReference
from app.models.blueprint_evidence import SemanticRequestCategory
from app.models.document_intelligence import CandidateEvidence, CandidateType, LocalCandidate, ResolutionCapability
from app.models.extraction import ExtractedDocument, ExtractedPage, ExtractionAssessment, PdfMetadata
from app.models.hybrid_blueprint import GeminiWorkUnit, GroundedContext, WorkUnitReason
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.evidence_packager import BlueprintEvidencePackager
from app.services.hybrid_blueprint import build_local_draft, create_work_units
from app.services.technical_blueprint import (
    GoogleTechnicalProvider,
    TechnicalBlueprintService,
    TechnicalSmokeTestError,
    build_technical_generation_config,
    parse_technical_response,
    select_technical_request,
    serialize_technical_request,
    technical_response_json_schema,
)


def document(*texts: str) -> ExtractedDocument:
    pages = [
        ExtractedPage(page_number=index, text=text, character_count=len(text), word_count=len(text.split()))
        for index, text in enumerate(texts, start=1)
    ]
    raw = "".join(texts).encode()
    return ExtractedDocument(
        filename="technical.pdf",
        sha256=hashlib.sha256(raw).hexdigest(),
        page_count=len(pages),
        total_characters=sum(len(text) for text in texts),
        total_words=sum(len(text.split()) for text in texts),
        text_pages=len(pages),
        empty_pages=0,
        assessment=ExtractionAssessment.TEXT_EXTRACTABLE,
        metadata=PdfMetadata(),
        pages=pages,
    )


def technical_plan(*texts: str, review_indexes: set[int] | None = None):
    review_indexes = review_indexes or set()
    source = document(*texts)
    draft = build_local_draft(LocalDocumentIntelligenceService().analyze(source))
    units = []
    for index, text in enumerate(texts, start=1):
        section_id = f"TECH-SECTION-{index}"
        candidate = LocalCandidate(
            candidate_id=f"TECH-LOCAL-{index}",
            candidate_type=CandidateType.SEMANTIC,
            category=RequirementCategory.TECHNICAL,
            raw_text=text,
            normalized=NormalizedRequirement(),
            evidence=[CandidateEvidence(
                source_reference=SourceReference(page_number=index, section="TECHNICAL EVALUATION", excerpt=text[:600]),
                section_id=section_id,
            )],
            confidence=0.6,
            ambiguous=index in review_indexes,
            ambiguity_reason="Needs local review" if index in review_indexes else "Semantic construction required",
            resolution_capability=ResolutionCapability.REVIEW_REQUIRED if index in review_indexes else ResolutionCapability.LLM_REQUIRED,
        )
        units.append(GeminiWorkUnit(
            work_unit_id=f"TECH-WU-{index}",
            prompt_version="hybrid-v2",
            document_sha256=source.sha256,
            reason=WorkUnitReason.UNRESOLVED_CANDIDATES,
            section_ids=[section_id],
            page_numbers=[index],
            context=[GroundedContext(page_number=index, section_id=section_id, heading="TECHNICAL EVALUATION", text=text)],
            candidates=[candidate],
        ))
    return BlueprintEvidencePackager().package(draft, units, source.total_characters)


def production_plan(text: str):
    source = document(text)
    draft = build_local_draft(LocalDocumentIntelligenceService().analyze(source))
    return BlueprintEvidencePackager().package(draft, create_work_units(draft), source.total_characters)


def handle_for(plan, phrase: str) -> str:
    request = select_technical_request(plan)
    return next(record.handle for record in request.records if phrase.casefold() in record.text.casefold())


def requirement(handle: str, **changes) -> dict:
    value = {
        "kind": "SCORED_CRITERION",
        "title": "Relevant Experience",
        "description": "Relevant Experience is evaluated for technical scoring.",
        "mandatory": None,
        "maximum_marks": 20,
        "minimum_qualifying_marks": 12,
        "threshold_value": None,
        "threshold_operator": None,
        "weight_percent": None,
        "expected_evidence": [],
        "evidence_ids": [handle],
        "requires_review": False,
        "review_reason": None,
    }
    value.update(changes)
    return value


def payload(*requirements: dict) -> str:
    return json.dumps({"requirements": list(requirements)})


class FakeProvider:
    model = "fake-gemini"

    def __init__(self, response: str, metadata: dict | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.metadata = metadata or {}
        self.error = error
        self.calls = 0
        self.prompts: list[str] = []

    def generate(self, prompt: str):
        self.calls += 1
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.response, self.metadata


class RecordingModels:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return type("Response", (), {"text": self.response_text, "response_id": "mock-id", "usage_metadata": None})()


class RecordingClient:
    def __init__(self, response_text: str) -> None:
        self.models = RecordingModels(response_text)


SIX_ROW_TABLE = """Technical Evaluation
Evaluation Criteria
Description
Maximum
Marks
Minimum
Passing
Marks
1
Relevant Experience
Evaluation of credentials and case studies
20
12
2
Completeness of Solution Proposed
Evaluation of the proposed solution
15
9
3
Proposed Support Methodology
Evaluation of capabilities and proposed process
20
12
4
Presentation of proposal and solution walkthrough
Presentation of proposal to the authority
10
6
5
Quality Assurance Plan
Evaluation of the proposed quality assurance process
15
9
6
Staffing capabilities
Capability of the vendor to staff the project
20
12"""


def test_selects_only_technical_request() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    assert select_technical_request(plan).category == SemanticRequestCategory.TECHNICAL


def test_non_technical_request_cannot_execute() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    plan.semantic_requests[0] = plan.semantic_requests[0].model_copy(update={"category": SemanticRequestCategory.QUALIFICATION})
    provider = FakeProvider(payload())
    with pytest.raises(TechnicalSmokeTestError):
        TechnicalBlueprintService(provider).execute(plan)
    assert provider.calls == 0


def test_unsupported_evidence_handle_is_rejected() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    result = TechnicalBlueprintService(FakeProvider(payload(requirement("E9999")))).execute(plan)
    assert result.accepted_count == 0
    assert result.unsupported_evidence_handle_count == 1


def test_provenance_is_fully_restored() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    item = TechnicalBlueprintService(FakeProvider(payload(requirement(handle_for(plan, "Relevant"))))).execute(plan).requirements[0]
    assert item.source_pages == [1]
    assert item.source_section_ids == ["TECH-SECTION-1"]
    assert item.source_work_unit_ids == ["TECH-WU-1"]
    assert item.candidate_ids == ["TECH-LOCAL-1"]
    assert item.source_references


def test_stable_ids_are_deterministic() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    provider = lambda: FakeProvider(payload(requirement(handle_for(plan, "Relevant"))))
    first = TechnicalBlueprintService(provider()).execute(plan).requirements[0].requirement_id
    second = TechnicalBlueprintService(provider()).execute(plan).requirements[0].requirement_id
    assert first == second


@pytest.mark.parametrize(
    ("title", "maximum", "minimum"),
    [
        ("Relevant Experience", 20, 12),
        ("Completeness of Proposed Solution", 15, 9),
        ("Support Methodology", 20, 12),
        ("Presentation", 10, 6),
        ("Quality Assurance", 15, 9),
        ("Staffing / Team", 20, 12),
    ],
)
def test_known_criterion_scores_remain_separate(title: str, maximum: float, minimum: float) -> None:
    text = f"{title}. Maximum marks: {maximum}. Minimum qualifying marks: {minimum}."
    plan = technical_plan(text)
    item = requirement(handle_for(plan, title), title=title, description=f"{title} technical criterion.", maximum_marks=maximum, minimum_qualifying_marks=minimum)
    result = TechnicalBlueprintService(FakeProvider(payload(item))).execute(plan).requirements[0]
    assert result.maximum_marks == maximum
    assert result.minimum_qualifying_marks == minimum


def test_overall_threshold_is_distinct_from_criterion_minimum() -> None:
    plan = technical_plan(
        "Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.",
        "Overall technical qualification score must be at least 65.",
    )
    criterion = requirement(handle_for(plan, "Relevant"))
    overall = requirement(
        handle_for(plan, "Overall"), kind="OVERALL_THRESHOLD", title="Overall Technical Qualification",
        description="Overall technical qualification score must be at least 65.", maximum_marks=None,
        minimum_qualifying_marks=None, threshold_value=65, threshold_operator=">=",
    )
    result = TechnicalBlueprintService(FakeProvider(payload(criterion, overall))).execute(plan)
    assert result.requirements[0].minimum_qualifying_marks == 12
    assert result.requirements[1].threshold_value == 65


def test_table_columns_associate_maximum_and_minimum_correctly() -> None:
    text = "Criterion | Maximum Marks | Minimum Marks\nRelevant Experience | 20 | 12\nPresentation | 10 | 6"
    plan = technical_plan(text)
    item = requirement(handle_for(plan, "Relevant"), maximum_marks=12, minimum_qualifying_marks=20)
    result = TechnicalBlueprintService(FakeProvider(payload(item))).execute(plan).requirements[0]
    assert (result.maximum_marks, result.minimum_qualifying_marks) == (20, 12)
    assert result.requires_review is True


def test_adjacent_criterion_numbers_do_not_leak() -> None:
    plan = technical_plan(
        "Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.",
        "Presentation. Maximum marks: 10. Minimum qualifying marks: 6.",
    )
    item = requirement(handle_for(plan, "Presentation"), title="Presentation", description="Presentation technical criterion.", maximum_marks=10, minimum_qualifying_marks=6)
    result = TechnicalBlueprintService(FakeProvider(payload(item))).execute(plan).requirements[0]
    assert (result.maximum_marks, result.minimum_qualifying_marks) == (10, 6)


def test_matching_local_scores_do_not_create_review() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    result = TechnicalBlueprintService(FakeProvider(payload(requirement(handle_for(plan, "Relevant"))))).execute(plan)
    assert result.review_required_count == 0


def test_genuine_maximum_score_conflict_requires_review() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    result = TechnicalBlueprintService(FakeProvider(payload(requirement(handle_for(plan, "Relevant"), maximum_marks=25)))).execute(plan)
    assert result.requirements[0].maximum_marks == 20
    assert "maximum marks" in result.requirements[0].review_reason


def test_genuine_minimum_score_conflict_requires_review() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    result = TechnicalBlueprintService(FakeProvider(payload(requirement(handle_for(plan, "Relevant"), minimum_qualifying_marks=10)))).execute(plan)
    assert result.requirements[0].minimum_qualifying_marks == 12
    assert "minimum qualifying marks" in result.requirements[0].review_reason


def test_genuine_overall_threshold_conflict_requires_review() -> None:
    text = "Overall technical qualification score must be at least 65."
    plan = technical_plan(text)
    item = requirement(handle_for(plan, "Overall"), kind="OVERALL_THRESHOLD", title="Overall Technical Qualification", description=text, maximum_marks=None, minimum_qualifying_marks=None, threshold_value=60, threshold_operator=">=")
    result = TechnicalBlueprintService(FakeProvider(payload(item))).execute(plan).requirements[0]
    assert result.threshold_value == 65
    assert result.requires_review is True


def test_local_review_required_state_propagates() -> None:
    text = "Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12."
    plan = technical_plan(text, review_indexes={1})
    result = TechnicalBlueprintService(FakeProvider(payload(requirement(handle_for(plan, "Relevant"))))).execute(plan).requirements[0]
    assert result.requires_review is True
    assert "local evidence" in result.review_reason.lower()


def test_safe_duplicates_merge_without_losing_provenance() -> None:
    text = "Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12."
    plan = technical_plan(text)
    item = requirement(handle_for(plan, "Relevant"))
    result = TechnicalBlueprintService(FakeProvider(payload(item, item))).execute(plan)
    assert result.generated_count == 2
    assert result.accepted_count == 1
    assert result.requirements[0].source_pages == [1]


def test_distinct_criteria_are_not_deduplicated() -> None:
    plan = technical_plan(
        "Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.",
        "Support Methodology. Maximum marks: 20. Minimum qualifying marks: 12.",
    )
    first = requirement(handle_for(plan, "Relevant"))
    second = requirement(handle_for(plan, "Support"), title="Support Methodology", description="Support Methodology technical criterion.")
    assert TechnicalBlueprintService(FakeProvider(payload(first, second))).execute(plan).accepted_count == 2


def test_missing_optional_numbers_remain_null() -> None:
    text = "The proposed solution must support secure integration."
    plan = technical_plan(text)
    item = requirement(handle_for(plan, "secure"), kind="TECHNICAL_REQUIREMENT", title="Secure Integration", description=text, maximum_marks=None, minimum_qualifying_marks=None)
    result = TechnicalBlueprintService(FakeProvider(payload(item))).execute(plan).requirements[0]
    assert result.maximum_marks is None
    assert result.minimum_qualifying_marks is None


def test_boolean_technical_requirement_has_no_numeric_conflict() -> None:
    text = "The solution must support ISO 27001 aligned security controls."
    plan = production_plan(text)
    item = requirement(handle_for(plan, "ISO"), kind="TECHNICAL_REQUIREMENT", title="Security Controls", description=text, mandatory=True, maximum_marks=None, minimum_qualifying_marks=None)
    result = TechnicalBlueprintService(FakeProvider(payload(item))).execute(plan).requirements[0]
    assert result.requires_review is False


def test_bidder_iso_certification_remains_qualification_routed() -> None:
    plan = production_plan("The Bidder must possess ISO 27001 certification.")
    assert {request.category for request in plan.semantic_requests} == {SemanticRequestCategory.QUALIFICATION}


def test_usage_metadata_and_zero_retry_are_reported() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    metadata = {"provider_request_id": "request-1", "input_tokens": 100, "output_tokens": 40, "total_tokens": 140}
    result = TechnicalBlueprintService(FakeProvider(payload(requirement(handle_for(plan, "Relevant"))), metadata)).execute(plan)
    assert result.usage.request_id == "request-1"
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens) == (100, 40, 140)
    assert (result.usage.request_count, result.usage.retry_count) == (1, 0)


def test_provider_failure_has_no_application_retry() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    provider = FakeProvider("", error=RuntimeError("offline"))
    with pytest.raises(TechnicalSmokeTestError):
        TechnicalBlueprintService(provider).execute(plan)
    assert provider.calls == 1


def test_standard_json_schema_path_preserves_local_strictness() -> None:
    schema = technical_response_json_schema()
    assert schema["additionalProperties"] is False
    with pytest.raises(TechnicalSmokeTestError):
        parse_technical_response('{"requirements":[],"unexpected":true}')


def test_invalid_structured_response_fails_safely() -> None:
    with pytest.raises(TechnicalSmokeTestError):
        parse_technical_response('{"requirements":[{"title":"missing fields"}]}')


def test_prompt_is_technical_scoped_and_uses_compact_handles() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    prompt = serialize_technical_request(select_technical_request(plan))
    assert "SEMANTIC CATEGORY: TECHNICAL" in prompt
    assert "E0001" in prompt
    assert "TECH-WU" not in prompt


def test_provider_adapter_uses_json_schema_disables_afc_and_limits_attempts() -> None:
    from google.genai import types

    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    response_text = payload(requirement(handle_for(plan, "Relevant")))
    client = RecordingClient(response_text)
    GoogleTechnicalProvider(None, "fake-gemini", client=client).generate("prompt")
    config = client.models.calls[0]["config"]
    assert config.response_schema is None
    assert config.response_json_schema == technical_response_json_schema()
    assert config.tools is None
    assert config.automatic_function_calling.disable is True
    assert config.http_options.retry_options.attempts == 1


def test_nested_requirement_rejects_unexpected_fields() -> None:
    plan = technical_plan("Relevant Experience. Maximum marks: 20. Minimum qualifying marks: 12.")
    item = requirement(handle_for(plan, "Relevant"), unexpected=True)
    with pytest.raises(TechnicalSmokeTestError):
        parse_technical_response(payload(item))


def test_generation_config_uses_only_response_json_schema() -> None:
    from google.genai import types

    config = build_technical_generation_config(types)
    assert config.response_json_schema
    assert config.response_schema is None


def test_six_row_linear_scoring_table_becomes_six_structured_evidence_records() -> None:
    request = select_technical_request(technical_plan(SIX_ROW_TABLE))
    rows = [record for record in request.records if "[TECHNICAL SCORE ROW]" in record.text]
    assert len(rows) == 6
    actual = sorted(
        (record.text.split("Criterion: ", 1)[1].splitlines()[0], record.text.split("Maximum Marks: ", 1)[1].splitlines()[0], record.text.split("Minimum Qualifying Marks: ", 1)[1])
        for record in rows
    )
    assert actual == sorted([
        ("Completeness of Solution Proposed", "15", "9"),
        ("Staffing capabilities", "20", "12"),
        ("Quality Assurance Plan", "15", "9"),
        ("Relevant Experience", "20", "12"),
        ("Presentation of proposal and solution walkthrough", "10", "6"),
        ("Proposed Support Methodology", "20", "12"),
    ])


def test_gemini_null_scores_are_enriched_from_matching_local_row() -> None:
    plan = technical_plan(SIX_ROW_TABLE)
    handle = handle_for(plan, "Criterion: Relevant Experience")
    item = requirement(handle, maximum_marks=None, minimum_qualifying_marks=None)
    result = TechnicalBlueprintService(FakeProvider(payload(item))).execute(plan).requirements
    relevant = next(value for value in result if value.title == "Relevant Experience")
    assert (relevant.maximum_marks, relevant.minimum_qualifying_marks) == (20, 12)
    assert relevant.requires_review is False


def test_local_score_enrichment_preserves_row_provenance() -> None:
    plan = technical_plan(SIX_ROW_TABLE)
    handle = handle_for(plan, "Criterion: Relevant Experience")
    item = requirement(handle, maximum_marks=None, minimum_qualifying_marks=None)
    relevant = next(
        value for value in TechnicalBlueprintService(FakeProvider(payload(item))).execute(plan).requirements
        if value.title == "Relevant Experience"
    )
    assert relevant.source_pages == [1]
    assert relevant.source_section_ids == ["TECH-SECTION-1"]
    assert relevant.source_work_unit_ids == ["TECH-WU-1"]


def test_general_quality_obligation_remains_distinct_from_scored_quality_criterion() -> None:
    general = "The solution must maintain a documented quality assurance process."
    plan = technical_plan(SIX_ROW_TABLE, general)
    generic = requirement(
        handle_for(plan, "documented quality"),
        kind="TECHNICAL_REQUIREMENT",
        title="Quality Assurance",
        description=general,
        mandatory=True,
        maximum_marks=None,
        minimum_qualifying_marks=None,
    )
    result = TechnicalBlueprintService(FakeProvider(payload(generic))).execute(plan).requirements
    quality = [item for item in result if "quality assurance" in item.title.casefold()]
    assert {item.kind.value for item in quality} == {"TECHNICAL_REQUIREMENT", "SCORED_CRITERION"}
    scored = next(item for item in quality if item.kind.value == "SCORED_CRITERION")
    assert (scored.maximum_marks, scored.minimum_qualifying_marks) == (15, 9)


def test_missing_table_score_cell_is_not_guessed() -> None:
    text = SIX_ROW_TABLE.replace("20\n12\n2\nCompleteness", "20\n2\nCompleteness", 1)
    request = select_technical_request(technical_plan(text))
    relevant_rows = [record for record in request.records if "Criterion: Relevant Experience" in record.text]
    assert relevant_rows == []


def test_ambiguous_unlabelled_number_sequence_does_not_create_score_rows() -> None:
    text = "Technical criteria\nRelevant Experience\n20\n12\nPresentation\n10\n6"
    request = select_technical_request(technical_plan(text))
    assert all("[TECHNICAL SCORE ROW]" not in record.text for record in request.records)


def test_enriched_local_score_conflict_still_requires_review() -> None:
    plan = technical_plan(SIX_ROW_TABLE)
    item = requirement(handle_for(plan, "Criterion: Relevant Experience"), maximum_marks=25, minimum_qualifying_marks=10)
    relevant = next(
        value for value in TechnicalBlueprintService(FakeProvider(payload(item))).execute(plan).requirements
        if value.title == "Relevant Experience"
    )
    assert (relevant.maximum_marks, relevant.minimum_qualifying_marks) == (20, 12)
    assert relevant.requires_review is True
    assert "maximum marks" in relevant.review_reason
    assert "minimum qualifying marks" in relevant.review_reason
