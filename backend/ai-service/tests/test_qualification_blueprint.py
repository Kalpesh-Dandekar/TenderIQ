import hashlib
import json

import pytest

from app.models.blueprint import NormalizedRequirement, RequirementCategory, SourceReference
from app.models.blueprint_evidence import SemanticRequestCategory
from app.models.document_intelligence import CandidateEvidence, CandidateType, LocalCandidate, ResolutionCapability
from app.models.extraction import ExtractedDocument, ExtractedPage, ExtractionAssessment, PdfMetadata
from app.models.hybrid_blueprint import GeminiWorkUnit, GroundedContext, WorkUnitReason
from app.services.evidence_packager import BlueprintEvidencePackager
from app.services.hybrid_blueprint import build_local_draft
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.qualification_blueprint import (
    GoogleQualificationProvider,
    QualificationBlueprintService,
    QualificationSmokeTestError,
    build_qualification_generation_config,
    parse_qualification_response,
    qualification_response_json_schema,
    select_qualification_request,
    serialize_qualification_request,
)


def document(text: str) -> ExtractedDocument:
    data = text.encode()
    return ExtractedDocument(
        filename="qualification.pdf",
        sha256=hashlib.sha256(data).hexdigest(),
        page_count=1,
        total_characters=len(text),
        total_words=len(text.split()),
        text_pages=1,
        empty_pages=0,
        assessment=ExtractionAssessment.TEXT_EXTRACTABLE,
        metadata=PdfMetadata(),
        pages=[ExtractedPage(page_number=1, text=text, character_count=len(text), word_count=len(text.split()))],
    )


def qualification_plan(
    text: str = "The bidder must have turnover of at least INR 40 crore.",
    *,
    mandatory: bool | None = True,
    review: bool = False,
    normalized: NormalizedRequirement | None = None,
    candidate_type: CandidateType | None = None,
):
    source = document(text)
    analysis = LocalDocumentIntelligenceService().analyze(source)
    draft = build_local_draft(analysis)
    evidence = CandidateEvidence(
        source_reference=SourceReference(page_number=1, section="ELIGIBILITY", excerpt=text),
        section_id="SECTION-0001",
    )
    candidate = LocalCandidate(
        candidate_id="LOCAL-QUAL-1",
        candidate_type=candidate_type or (CandidateType.MONEY if normalized else CandidateType.SEMANTIC),
        category=RequirementCategory.ELIGIBILITY,
        raw_text=text,
        normalized=normalized or NormalizedRequirement(),
        mandatory_signal=mandatory,
        evidence=[evidence],
        confidence=0.8,
        ambiguous=review,
        ambiguity_reason="Needs review" if review else None,
        resolution_capability=ResolutionCapability.REVIEW_REQUIRED if review else ResolutionCapability.LLM_REQUIRED,
    )
    unit = GeminiWorkUnit(
        work_unit_id="WU-QUAL-1",
        prompt_version="hybrid-v2",
        document_sha256=source.sha256,
        reason=WorkUnitReason.UNRESOLVED_CANDIDATES,
        section_ids=["SECTION-0001"],
        page_numbers=[1],
        context=[GroundedContext(page_number=1, section_id="SECTION-0001", heading="ELIGIBILITY", text=text)],
        candidates=[candidate],
    )
    return BlueprintEvidencePackager().package(draft, [unit], source.total_characters)


def response(handle: str = "E0001", **changes) -> str:
    requirement = {
        "requirement_type": "MONEY",
        "title": "Minimum turnover",
        "requirement_text": "The bidder must have turnover of at least INR 40 crore.",
        "mandatory": True,
        "value": 40,
        "operator": ">=",
        "unit": "INR_CRORE",
        "evidence_ids": [handle],
        "requires_review": False,
        "review_reason": None,
    }
    requirement.update(changes)
    return json.dumps({"requirements": [requirement]})


class FakeProvider:
    model = "fake-gemini"

    def __init__(self, payload: str, metadata: dict | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.metadata = metadata or {}
        self.error = error
        self.calls = 0
        self.prompts: list[str] = []

    def generate(self, prompt: str):
        self.calls += 1
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.payload, self.metadata


class FakeGeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.response_id = "mock-provider-request"
        self.usage_metadata = None


class RecordingModels:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return FakeGeminiResponse(self.text)


class RecordingClient:
    def __init__(self, text: str) -> None:
        self.models = RecordingModels(text)


def test_qualification_request_serialization_is_compact_and_scoped() -> None:
    request = select_qualification_request(qualification_plan())
    prompt = serialize_qualification_request(request)
    assert "SEMANTIC CATEGORY: QUALIFICATION" in prompt
    assert "E0001" in prompt
    assert "WU-QUAL-1" not in prompt
    assert "LOCAL-QUAL-1" not in prompt


def test_strict_structured_response_parsing() -> None:
    assert parse_qualification_response(response()).requirements[0].title == "Minimum turnover"


def test_provider_uses_standard_json_schema_without_restricted_schema_conversion() -> None:
    client = RecordingClient(response())
    provider = GoogleQualificationProvider(None, "fake-gemini", client=client)
    payload, _metadata = provider.generate("qualification prompt")
    assert payload == response()
    config = client.models.calls[0]["config"]
    assert config.response_schema is None
    assert config.response_json_schema == qualification_response_json_schema()


def test_standard_schema_preserves_additional_properties_naming() -> None:
    schema = qualification_response_json_schema()

    def keys(value):
        if isinstance(value, dict):
            return set(value) | {key for child in value.values() for key in keys(child)}
        if isinstance(value, list):
            return {key for child in value for key in keys(child)}
        return set()

    schema_keys = keys(schema)
    assert "additionalProperties" in schema_keys
    assert "additional_properties" not in schema_keys


def test_provider_config_disables_afc_tools_and_http_retries() -> None:
    from google.genai import types

    config = build_qualification_generation_config(types)
    assert config.tools is None
    assert config.automatic_function_calling.disable is True
    assert config.http_options.retry_options.attempts == 1


def test_local_schema_rejects_unexpected_top_level_field() -> None:
    payload = json.loads(response())
    payload["unexpected"] = True
    with pytest.raises(QualificationSmokeTestError):
        parse_qualification_response(json.dumps(payload))


def test_nested_requirement_schema_remains_strict() -> None:
    payload = json.loads(response())
    payload["requirements"][0]["unexpected"] = True
    with pytest.raises(QualificationSmokeTestError):
        parse_qualification_response(json.dumps(payload))


def test_invalid_schema_fails_without_second_provider_call() -> None:
    provider = FakeProvider('{"requirements":[{"title":"Incomplete"}]}')
    with pytest.raises(QualificationSmokeTestError):
        QualificationBlueprintService(provider).execute(qualification_plan())
    assert provider.calls == 1


def test_valid_evidence_handle_restores_full_provenance() -> None:
    result = QualificationBlueprintService(FakeProvider(response())).execute(qualification_plan())
    item = result.requirements[0]
    assert item.evidence_handles == ["E0001"]
    assert item.source_pages == [1]
    assert item.source_section_ids == ["SECTION-0001"]
    assert item.source_work_unit_ids == ["WU-QUAL-1"]
    assert item.candidate_ids == ["LOCAL-QUAL-1"]
    assert item.source_references[0].excerpt


def test_invented_evidence_handle_is_rejected() -> None:
    result = QualificationBlueprintService(FakeProvider(response("E9999"))).execute(qualification_plan())
    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert result.unsupported_evidence_handle_count == 1


def test_missing_evidence_handle_is_rejected_by_schema() -> None:
    with pytest.raises(QualificationSmokeTestError):
        parse_qualification_response(response(evidence_ids=[]))


def test_ungrounded_claim_is_rejected() -> None:
    payload = response(title="Local office", requirement_text="The supplier must maintain a Bangalore support office.")
    result = QualificationBlueprintService(FakeProvider(payload)).execute(qualification_plan())
    assert result.accepted_count == 0


def test_review_required_evidence_cannot_be_promoted_to_certainty() -> None:
    result = QualificationBlueprintService(FakeProvider(response())).execute(qualification_plan(review=True))
    assert result.requirements[0].requires_review is True
    assert "local evidence" in result.requirements[0].review_reason.lower()


def test_numeric_conflict_retains_local_value_and_marks_review() -> None:
    normalized = NormalizedRequirement(value=40, operator=">=", unit="INR_CRORE")
    result = QualificationBlueprintService(FakeProvider(response(value=4))).execute(
        qualification_plan(normalized=normalized)
    )
    item = result.requirements[0]
    assert item.normalized.value == 40
    assert item.requires_review is True


def test_mandatory_conflict_becomes_unknown_and_review_required() -> None:
    result = QualificationBlueprintService(FakeProvider(response(mandatory=False))).execute(qualification_plan())
    item = result.requirements[0]
    assert item.mandatory is None
    assert item.requires_review is True


def test_boolean_nasscom_membership_ignores_unrelated_numeric_hint() -> None:
    text = "The Bidder must have NASSCOM membership and five years of operation."
    plan = qualification_plan(
        text,
        normalized=NormalizedRequirement(value=5, operator=">=", unit="year"),
        candidate_type=CandidateType.DURATION,
    )
    payload = response(
        requirement_type="BOOLEAN",
        title="NASSCOM Membership",
        requirement_text="The Bidder must have NASSCOM membership.",
        value=True,
        operator=None,
        unit=None,
    )
    item = QualificationBlueprintService(FakeProvider(payload)).execute(plan).requirements[0]
    assert item.normalized.value is True
    assert item.requires_review is False


def test_iso_identifiers_do_not_become_numeric_thresholds() -> None:
    text = "The bidder must maintain ISO 9001 and ISO 27001 certifications."
    plan = qualification_plan(
        text,
        normalized=NormalizedRequirement(value=9001),
        candidate_type=CandidateType.QUANTITATIVE,
    )
    payload = response(
        requirement_type="BOOLEAN",
        title="ISO certifications",
        requirement_text=text,
        value=True,
        operator=None,
        unit=None,
    )
    item = QualificationBlueprintService(FakeProvider(payload)).execute(plan).requirements[0]
    assert item.normalized.value is True
    assert item.normalized.operator is None
    assert item.requires_review is False


def test_blacklisting_boolean_ignores_unrelated_number() -> None:
    text = "The bidder must not be blacklisted during the previous five years."
    plan = qualification_plan(
        text,
        normalized=NormalizedRequirement(value=5, unit="year"),
        candidate_type=CandidateType.DURATION,
    )
    payload = response(
        requirement_type="BOOLEAN",
        title="No blacklisting",
        requirement_text="The bidder must not be blacklisted.",
        value=False,
        operator=None,
        unit=None,
    )
    item = QualificationBlueprintService(FakeProvider(payload)).execute(plan).requirements[0]
    assert item.normalized.value is False
    assert item.requires_review is False


def test_real_smoke_turnover_shape_recovers_grounded_crore_magnitude() -> None:
    text = (
        "The Bidder should have a minimum turnover of INR 40 crores per annum "
        "in two of the last three financial years."
    )
    local = NormalizedRequirement(value="400000000", operator=">=", currency="INR")
    payload = response(
        title="Minimum Annual Turnover",
        requirement_text=text,
        value="40",
        operator=">=",
        unit=None,
        currency="INR",
    )
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.MONEY)
    ).requirements[0]
    assert item.normalized.value == "400000000"
    assert item.normalized.operator == ">="
    assert item.normalized.currency == "INR"
    assert item.requires_review is False


@pytest.mark.parametrize(
    ("source_amount", "gemini_value", "local_value"),
    [
        ("INR 40 crore", "40", "400000000"),
        ("INR 40 crores", "40", "400000000"),
        ("5 crore INR", "5", "50000000"),
        ("INR 25 lakh", "25", "2500000"),
    ],
)
def test_grounded_indian_money_magnitudes_compare_in_base_units(
    source_amount: str, gemini_value: str, local_value: str
) -> None:
    text = f"The bidder must have minimum turnover of {source_amount}."
    local = NormalizedRequirement(value=local_value, operator=">=", currency="INR")
    payload = response(
        requirement_text=text,
        value=gemini_value,
        operator=">=",
        unit=None,
        currency="INR",
    )
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.MONEY)
    ).requirements[0]
    assert item.normalized.value == local_value
    assert item.requires_review is False


def test_plain_inr_value_without_grounded_magnitude_is_not_multiplied() -> None:
    text = "The bidder must pay INR 40."
    local = NormalizedRequirement(value="40", operator="=", currency="INR")
    payload = response(
        requirement_text=text,
        value="40",
        operator="=",
        unit=None,
        currency="INR",
    )
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.MONEY)
    ).requirements[0]
    assert item.normalized.value == "40"
    assert item.requires_review is False


def test_grounded_crore_vs_different_base_amount_requires_review() -> None:
    text = "The bidder must have minimum turnover of INR 40 crore."
    local = NormalizedRequirement(value="500000000", operator=">=", currency="INR")
    payload = response(requirement_text=text, value="40", operator=">=", unit=None, currency="INR")
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.MONEY)
    ).requirements[0]
    assert item.requires_review is True


def test_grounded_40_crore_vs_gemini_50_crore_requires_review() -> None:
    text = "The bidder must have minimum turnover of INR 40 crore."
    local = NormalizedRequirement(value="400000000", operator=">=", currency="INR")
    payload = response(requirement_text=text, value="50", operator=">=", unit="INR_CRORE", currency="INR")
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.MONEY)
    ).requirements[0]
    assert item.requires_review is True


def test_equivalent_money_magnitude_with_currency_mismatch_requires_review() -> None:
    text = "The bidder must have minimum turnover of INR 40 crore."
    local = NormalizedRequirement(value="400000000", operator=">=", currency="USD")
    payload = response(requirement_text=text, value="40", operator=">=", unit=None, currency="INR")
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.MONEY)
    ).requirements[0]
    assert item.requires_review is True


def test_equivalent_money_still_preserves_grounded_review_state() -> None:
    text = "The bidder should have minimum turnover of INR 40 crore unless exempted."
    local = NormalizedRequirement(value="400000000", operator=">=", currency="INR")
    payload = response(requirement_text=text, value="40", operator=">=", unit=None, currency="INR")
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.MONEY, review=True)
    ).requirements[0]
    assert item.normalized.value == "400000000"
    assert item.requires_review is True
    assert "local evidence" in item.review_reason.lower()


def test_years_in_operation_retains_duration_value_and_operator() -> None:
    text = "The bidder must have operated for at least 5 years."
    local = NormalizedRequirement(value="5", operator=">=", unit="year", period="5 years")
    payload = response(
        requirement_type="DURATION",
        title="Years in operation",
        requirement_text=text,
        value=5,
        operator=">=",
        unit="years",
    )
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.DURATION)
    ).requirements[0]
    assert (item.normalized.value, item.normalized.operator, item.normalized.unit) == ("5", ">=", "year")
    assert item.requires_review is False


def test_performance_security_selects_percentage_from_mixed_quantity_clause() -> None:
    text = (
        "Within 15 days after receipt of award, the Bidder shall submit Performance Security "
        "for an amount of 3% of Contract Value."
    )
    local = NormalizedRequirement(value="3", unit="percent")
    payload = response(
        requirement_type="PERCENTAGE",
        title="Performance Security",
        requirement_text=text,
        value=3,
        operator=None,
        unit="percent",
    )
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.PERCENTAGE)
    ).requirements[0]
    assert item.normalized.value == "3"
    assert item.normalized.unit == "percent"
    assert item.requires_review is False


def test_genuine_percentage_disagreement_requires_review() -> None:
    text = "The bidder shall submit Performance Security of 3% of Contract Value."
    local = NormalizedRequirement(value="3", unit="percent")
    payload = response(
        requirement_type="PERCENTAGE",
        title="Performance Security",
        requirement_text=text,
        value=5,
        unit="percent",
        operator=None,
    )
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.PERCENTAGE)
    ).requirements[0]
    assert item.normalized.value == "3"
    assert item.requires_review is True
    assert "percentage normalization" in item.review_reason


def test_genuine_money_disagreement_requires_review() -> None:
    local = NormalizedRequirement(value="400000000", operator=">=", currency="INR")
    item = QualificationBlueprintService(FakeProvider(response(value=4, unit="INR_CRORE"))).execute(
        qualification_plan(normalized=local, candidate_type=CandidateType.MONEY)
    ).requirements[0]
    assert item.normalized.value == "400000000"
    assert item.requires_review is True
    assert "money normalization" in item.review_reason


def test_genuine_duration_disagreement_requires_review() -> None:
    text = "The bidder must have operated for at least 5 years."
    local = NormalizedRequirement(value="5", operator=">=", unit="year")
    payload = response(
        requirement_type="DURATION",
        title="Years in operation",
        requirement_text=text,
        value=4,
        operator=">=",
        unit="year",
    )
    item = QualificationBlueprintService(FakeProvider(payload)).execute(
        qualification_plan(text, normalized=local, candidate_type=CandidateType.DURATION)
    ).requirements[0]
    assert item.normalized.value == "5"
    assert item.requires_review is True
    assert "duration normalization" in item.review_reason


def test_provider_failure_is_safe_and_never_retried() -> None:
    provider = FakeProvider("", error=RuntimeError("offline"))
    with pytest.raises(QualificationSmokeTestError):
        QualificationBlueprintService(provider).execute(qualification_plan())
    assert provider.calls == 1


def test_smoke_usage_retry_count_is_always_zero() -> None:
    result = QualificationBlueprintService(FakeProvider(response())).execute(qualification_plan())
    assert result.usage.request_count == 1
    assert result.usage.retry_count == 0


def test_non_qualification_category_cannot_execute() -> None:
    plan = qualification_plan()
    plan.semantic_requests[0] = plan.semantic_requests[0].model_copy(
        update={"category": SemanticRequestCategory.TECHNICAL}
    )
    provider = FakeProvider(response())
    with pytest.raises(QualificationSmokeTestError):
        QualificationBlueprintService(provider).execute(plan)
    assert provider.calls == 0


def test_usage_metadata_is_captured_when_available() -> None:
    metadata = {"provider_request_id": "provider-1", "input_tokens": 500, "output_tokens": 80, "total_tokens": 580}
    result = QualificationBlueprintService(FakeProvider(response(), metadata)).execute(qualification_plan())
    assert result.usage.request_id == "provider-1"
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens) == (500, 80, 580)


def test_missing_usage_metadata_remains_unavailable() -> None:
    result = QualificationBlueprintService(FakeProvider(response())).execute(qualification_plan())
    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None
    assert result.usage.total_tokens is None


def test_equivalent_duplicate_requirements_merge_provenance() -> None:
    payload = json.dumps({"requirements": json.loads(response())["requirements"] * 2})
    result = QualificationBlueprintService(FakeProvider(payload)).execute(qualification_plan())
    assert result.generated_count == 2
    assert result.accepted_count == 1
