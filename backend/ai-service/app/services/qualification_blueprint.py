import hashlib
import re
import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from pydantic import ValidationError

from app.models.blueprint import NormalizedRequirement, RequirementCategory, SourceReference
from app.models.blueprint_evidence import (
    BlueprintEvidenceItem,
    BlueprintEvidencePlan,
    BlueprintSemanticRequest,
    SemanticRequestCategory,
)
from app.models.qualification_blueprint import (
    GroundedQualificationRequirement,
    QualificationBlueprintResponse,
    QualificationExecutionResult,
    QualificationRequirementResponse,
    QualificationUsage,
)
from app.models.blueprint import RequirementType
from app.models.document_intelligence import CandidateType

_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_NON_CLAIM_WORDS = {
    "a", "an", "and", "as", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "the", "to", "with",
    "requirement", "required", "must", "shall", "should", "bidder", "vendor", "tenderer", "supplier",
}
_MEASURABLE_CANDIDATE_TYPES = {
    RequirementType.MONEY: CandidateType.MONEY,
    RequirementType.PERCENTAGE: CandidateType.PERCENTAGE,
    RequirementType.DURATION: CandidateType.DURATION,
    RequirementType.DATE: CandidateType.DATE,
    RequirementType.NUMERIC: CandidateType.QUANTITATIVE,
}
_MONEY_MAGNITUDE = re.compile(
    r"(?:\bINR\s*)?(\d+(?:\.\d+)?)\s*(crores?|lakhs?)(?:\s*INR\b)?",
    re.IGNORECASE,
)


class QualificationSmokeTestError(Exception):
    def __init__(self, message: str, request_count: int = 0) -> None:
        super().__init__(message)
        self.request_count = request_count


class QualificationResponseProvider(Protocol):
    model: str

    def generate(self, prompt: str) -> tuple[str, dict[str, int | str | None]]: ...


class GoogleQualificationProvider:
    def __init__(self, api_key: str | None, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self.model = model
        self._client = client

    def generate(self, prompt: str) -> tuple[str, dict[str, int | str | None]]:
        if not self._api_key and self._client is None:
            raise QualificationSmokeTestError("Gemini is not configured")
        try:
            from google import genai
            from google.genai import types

            client = self._client or genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=build_qualification_generation_config(types),
            )
        except Exception as error:
            raise QualificationSmokeTestError("Gemini qualification request failed", request_count=1) from error
        if not response.text:
            raise QualificationSmokeTestError("Gemini returned an empty qualification response", request_count=1)
        usage = response.usage_metadata
        return response.text, {
            "provider_request_id": getattr(response, "response_id", None),
            "input_tokens": getattr(usage, "prompt_token_count", None) if usage else None,
            "output_tokens": getattr(usage, "candidates_token_count", None) if usage else None,
            "total_tokens": getattr(usage, "total_token_count", None) if usage else None,
        }


def qualification_response_json_schema() -> dict[str, Any]:
    return QualificationBlueprintResponse.model_json_schema()


def build_qualification_generation_config(types_module: Any) -> Any:
    return types_module.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=qualification_response_json_schema(),
        temperature=0,
        automatic_function_calling=types_module.AutomaticFunctionCallingConfig(disable=True),
        http_options=types_module.HttpOptions(
            retry_options=types_module.HttpRetryOptions(attempts=1),
        ),
    )


def select_qualification_request(plan: BlueprintEvidencePlan) -> BlueprintSemanticRequest:
    qualification = [
        request for request in plan.semantic_requests if request.category == SemanticRequestCategory.QUALIFICATION
    ]
    if len(qualification) != 1:
        raise QualificationSmokeTestError(
            f"Qualification-only mode requires exactly one QUALIFICATION request; found {len(qualification)}"
        )
    return qualification[0]


def serialize_qualification_request(request: BlueprintSemanticRequest) -> str:
    if request.category != SemanticRequestCategory.QUALIFICATION:
        raise QualificationSmokeTestError("Qualification-only mode rejected a non-QUALIFICATION request")
    return (
        "You construct TenderIQ qualification requirements using only the supplied evidence. "
        "Return strict JSON matching the response schema. Every requirement must cite one or more supplied evidence_ids. "
        "Do not invent requirements, handles, thresholds, mandatory status, or procurement assumptions. "
        "Use mandatory=null and requires_review=true when obligation status is ambiguous. Preserve review-marked evidence as review. "
        "Keep distinct obligations separate; merge only equivalent repeated clauses. Numeric values must agree with supplied evidence.\n\n"
        f"SEMANTIC CATEGORY: {request.category.value}\nREQUEST ID: {request.request_id}\n\n{request.compact_context}"
    )


def parse_qualification_response(payload: str) -> QualificationBlueprintResponse:
    try:
        return QualificationBlueprintResponse.model_validate_json(payload)
    except (ValidationError, ValueError) as error:
        raise QualificationSmokeTestError("Gemini qualification response failed strict schema validation", 1) from error


def _evidence_index(plan: BlueprintEvidencePlan) -> dict[str, BlueprintEvidenceItem]:
    return {
        item.evidence_id: item
        for package in plan.packages
        for item in package.evidence_items
    }


def _unique_sources(items: list[BlueprintEvidenceItem]) -> list[SourceReference]:
    unique: dict[tuple[int, str, str, str], SourceReference] = {}
    for item in items:
        for source in item.source_references:
            key = (source.page_number, source.section or "", source.clause or "", source.excerpt.casefold())
            unique[key] = source
    return [unique[key] for key in sorted(unique)]


def _claim_is_supported(requirement: QualificationRequirementResponse, evidence: list[BlueprintEvidenceItem]) -> bool:
    claim_words = {
        word.casefold() for word in _WORD.findall(f"{requirement.title} {requirement.requirement_text}")
        if len(word) > 2 and word.casefold() not in _NON_CLAIM_WORDS
    }
    evidence_words = {word.casefold() for item in evidence for word in _WORD.findall(item.text)}
    return bool(claim_words & evidence_words)


def _semantic_words(text: str) -> set[str]:
    return {
        word.casefold() for word in _WORD.findall(text)
        if len(word) > 2 and word.casefold() not in _NON_CLAIM_WORDS
    }


def _matching_local_normalizations(
    response: QualificationRequirementResponse,
    items: list[BlueprintEvidenceItem],
) -> list[NormalizedRequirement]:
    expected = _MEASURABLE_CANDIDATE_TYPES.get(response.requirement_type)
    if expected is None:
        return []
    claim_words = _semantic_words(f"{response.title} {response.requirement_text}")
    matches: list[tuple[int, NormalizedRequirement]] = []
    for item in items:
        relevance = len(claim_words & _semantic_words(item.text))
        for hint in item.local_hints:
            value = hint.normalized.value
            if hint.candidate_type == expected and value is not None and not isinstance(value, bool):
                matches.append((relevance, hint.normalized))
    if not matches:
        return []
    best_relevance = max(score for score, _normalized in matches)
    return [normalized for score, normalized in matches if score == best_relevance]


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def _grounded_money_multiplier(value: Decimal, grounded_text: str) -> Decimal:
    for match in _MONEY_MAGNITUDE.finditer(grounded_text):
        if _decimal(match.group(1)) != value:
            continue
        magnitude = match.group(2).casefold()
        return Decimal(10_000_000) if magnitude.startswith("crore") else Decimal(100_000)
    return Decimal(1)


def _money_value(normalized: NormalizedRequirement, grounded_text: str = "") -> Decimal | None:
    value = _decimal(normalized.value)
    if value is None:
        return None
    unit = (normalized.unit or "").casefold().replace("-", "_")
    if unit in {"inr_crore", "crore", "crores"}:
        return value * Decimal(10_000_000)
    if unit in {"inr_lakh", "lakh", "lakhs"}:
        return value * Decimal(100_000)
    return value * _grounded_money_multiplier(value, grounded_text)


def _normalized_unit(value: str | None) -> str | None:
    return value.casefold().rstrip("s") if value else None


def _measurable_conflict(
    requirement_type: RequirementType,
    proposed: NormalizedRequirement,
    local: NormalizedRequirement,
    grounded_text: str,
) -> bool:
    proposed_value = _money_value(proposed, grounded_text) if requirement_type == RequirementType.MONEY else _decimal(proposed.value)
    local_value = _money_value(local, grounded_text) if requirement_type == RequirementType.MONEY else _decimal(local.value)
    if proposed_value is not None and local_value is not None and proposed_value != local_value:
        return True
    if proposed.operator is not None and local.operator is not None and proposed.operator != local.operator:
        return True
    if requirement_type in {RequirementType.DURATION, RequirementType.NUMERIC}:
        proposed_unit = _normalized_unit(proposed.unit)
        local_unit = _normalized_unit(local.unit)
        if proposed_unit and local_unit and proposed_unit != local_unit:
            return True
    if requirement_type == RequirementType.MONEY:
        proposed_currency = (proposed.currency or "INR" if (proposed.unit or "").upper().startswith("INR") else proposed.currency)
        if proposed_currency and local.currency and proposed_currency.casefold() != local.currency.casefold():
            return True
    return False


def _normalize_with_local_authority(
    response: QualificationRequirementResponse, items: list[BlueprintEvidenceItem]
) -> tuple[NormalizedRequirement, bool, str | None]:
    proposed = NormalizedRequirement(
        value=response.value,
        operator=response.operator,
        unit=response.unit,
        currency=response.currency,
        period=response.period,
    )
    local_matches = _matching_local_normalizations(response, items)
    if not local_matches:
        return proposed, False, None
    distinct = {
        (item.value, item.operator, _normalized_unit(item.unit), item.currency, item.period)
        for item in local_matches
    }
    authoritative = local_matches[0]
    if len(distinct) > 1:
        return authoritative, True, "Multiple equally relevant grounded local normalizations conflict"
    grounded_text = "\n".join(item.text for item in items)
    conflict = _measurable_conflict(response.requirement_type, proposed, authoritative, grounded_text)
    if conflict:
        return authoritative, True, f"Gemini {response.requirement_type.value.lower()} normalization conflicted with grounded local normalization"
    return authoritative, False, None


def _restore_requirement(
    response: QualificationRequirementResponse,
    request: BlueprintSemanticRequest,
    item_index: dict[str, BlueprintEvidenceItem],
) -> GroundedQualificationRequirement | None:
    record_index = {record.handle: record for record in request.records}
    if any(handle not in record_index for handle in response.evidence_ids):
        return None
    records = [record_index[handle] for handle in dict.fromkeys(response.evidence_ids)]
    items = [item_index[record.evidence_id] for record in records if record.evidence_id in item_index]
    if len(items) != len(records) or not _claim_is_supported(response, items):
        return None

    local_mandatory = {hint.mandatory_signal for item in items for hint in item.local_hints if hint.mandatory_signal is not None}
    mandatory_conflict = bool(local_mandatory and response.mandatory is not None and response.mandatory not in local_mandatory)
    normalized, numeric_conflict, numeric_reason = _normalize_with_local_authority(response, items)
    evidence_review = any(item.requires_review for item in items)
    requires_review = response.requires_review or evidence_review or mandatory_conflict or numeric_conflict
    reasons = [response.review_reason] if response.review_reason else []
    if evidence_review:
        reasons.append("Grounded local evidence requires review")
    if mandatory_conflict:
        reasons.append("Gemini mandatory status conflicted with grounded local evidence")
    if numeric_reason:
        reasons.append(numeric_reason)
    identity = "|".join([response.title, response.requirement_text, *sorted(record.evidence_id for record in records)])
    return GroundedQualificationRequirement(
        requirement_id=f"QREQ-{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
        category=next((category for item in items for category in item.categories), RequirementCategory.ELIGIBILITY),
        requirement_type=response.requirement_type,
        title=response.title,
        requirement_text=response.requirement_text,
        mandatory=None if mandatory_conflict else response.mandatory,
        normalized=normalized,
        evidence_handles=[record.handle for record in records],
        evidence_ids=[record.evidence_id for record in records],
        source_pages=sorted({page for item in items for page in item.source_pages}),
        source_section_ids=sorted({value for item in items for value in item.source_section_ids}),
        source_work_unit_ids=sorted({value for item in items for value in item.source_work_unit_ids}),
        candidate_ids=sorted({value for item in items for value in item.candidate_ids}),
        source_references=_unique_sources(items),
        source_categories=sorted({category for item in items for category in item.categories}, key=lambda value: value.value),
        requires_review=requires_review,
        review_reason="; ".join(dict.fromkeys(reasons)) or None,
    )


def _deduplicate(requirements: list[GroundedQualificationRequirement]) -> list[GroundedQualificationRequirement]:
    deduplicated: dict[tuple[str, str, object, object, object], GroundedQualificationRequirement] = {}
    for requirement in requirements:
        key = (
            " ".join(requirement.requirement_text.casefold().split()),
            requirement.requirement_type.value,
            requirement.normalized.value,
            requirement.normalized.operator,
            requirement.normalized.unit,
        )
        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = requirement
            continue
        deduplicated[key] = existing.model_copy(update={
            "evidence_handles": sorted(set(existing.evidence_handles + requirement.evidence_handles)),
            "evidence_ids": sorted(set(existing.evidence_ids + requirement.evidence_ids)),
            "source_pages": sorted(set(existing.source_pages + requirement.source_pages)),
            "source_section_ids": sorted(set(existing.source_section_ids + requirement.source_section_ids)),
            "source_work_unit_ids": sorted(set(existing.source_work_unit_ids + requirement.source_work_unit_ids)),
            "candidate_ids": sorted(set(existing.candidate_ids + requirement.candidate_ids)),
            "source_references": existing.source_references + [
                source for source in requirement.source_references if source not in existing.source_references
            ],
            "requires_review": existing.requires_review or requirement.requires_review,
            "review_reason": existing.review_reason or requirement.review_reason,
        })
    return list(deduplicated.values())


class QualificationBlueprintService:
    def __init__(self, provider: QualificationResponseProvider, clock: Callable[[], float] = time.perf_counter) -> None:
        self._provider = provider
        self._clock = clock

    def execute(self, plan: BlueprintEvidencePlan) -> QualificationExecutionResult:
        request = select_qualification_request(plan)
        prompt = serialize_qualification_request(request)
        started = self._clock()
        try:
            payload, metadata = self._provider.generate(prompt)
        except QualificationSmokeTestError:
            raise
        except Exception as error:
            raise QualificationSmokeTestError("Qualification provider failed", request_count=1) from error
        latency_ms = (self._clock() - started) * 1000
        parsed = parse_qualification_response(payload)
        known_handles = {record.handle for record in request.records}
        unsupported = sum(
            handle not in known_handles for requirement in parsed.requirements for handle in requirement.evidence_ids
        )
        item_index = _evidence_index(plan)
        restored = [
            grounded for response in parsed.requirements
            if (grounded := _restore_requirement(response, request, item_index)) is not None
        ]
        accepted = _deduplicate(restored)
        return QualificationExecutionResult(
            requirements=accepted,
            generated_count=len(parsed.requirements),
            accepted_count=len(accepted),
            review_required_count=sum(item.requires_review for item in accepted),
            rejected_count=len(parsed.requirements) - len(restored),
            unsupported_evidence_handle_count=unsupported,
            usage=QualificationUsage(
                model=self._provider.model,
                request_id=str(metadata.get("provider_request_id") or request.request_id),
                evidence_record_count=len(request.records),
                input_characters=request.character_count,
                input_tokens=metadata.get("input_tokens") if isinstance(metadata.get("input_tokens"), int) else None,
                output_tokens=metadata.get("output_tokens") if isinstance(metadata.get("output_tokens"), int) else None,
                total_tokens=metadata.get("total_tokens") if isinstance(metadata.get("total_tokens"), int) else None,
                latency_ms=latency_ms,
                request_count=1,
                retry_count=0,
                success=True,
            ),
        )
