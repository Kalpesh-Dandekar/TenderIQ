import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.models.blueprint import ComparisonOperator, RequirementCategory, SourceReference
from app.models.blueprint_evidence import (
    BlueprintEvidenceItem,
    BlueprintEvidencePlan,
    BlueprintSemanticRequest,
    SemanticRequestCategory,
)
from app.models.technical_blueprint import (
    GroundedTechnicalRequirement,
    TechnicalBlueprintResponse,
    TechnicalExecutionResult,
    TechnicalRequirementKind,
    TechnicalRequirementResponse,
    TechnicalUsage,
)
from app.services.normalization import normalize_operator

_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOP_WORDS = {
    "a", "an", "and", "as", "be", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with",
    "criterion", "criteria", "technical", "marks", "score", "maximum", "minimum", "qualifying",
}
_MAXIMUM = re.compile(r"\b(?:maximum|max\.?)(?:\s+(?:score|marks?))?\s*[:=-]?\s*(\d+(?:\.\d+)?)", re.I)
_MINIMUM = re.compile(r"\b(?:minimum|min\.?)(?:\s+qualifying)?(?:\s+(?:score|marks?))?\s*[:=-]?\s*(\d+(?:\.\d+)?)", re.I)
_OVERALL = re.compile(
    r"\b(?:overall\s+)?technical(?:\s+(?:qualification|qualifying))?\s+(?:score|threshold)[^\d]{0,30}(\d+(?:\.\d+)?)",
    re.I,
)
_ROW_TITLE = re.compile(r"^Criterion:\s*(.+)$", re.MULTILINE)
_ROW_DESCRIPTION = re.compile(r"^Description:\s*(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class LocalScoreFacts:
    maximum_marks: float | None = None
    minimum_qualifying_marks: float | None = None
    threshold_value: float | None = None
    threshold_operator: ComparisonOperator | None = None


class TechnicalSmokeTestError(Exception):
    def __init__(self, message: str, request_count: int = 0) -> None:
        super().__init__(message)
        self.request_count = request_count


class TechnicalResponseProvider(Protocol):
    model: str

    def generate(self, prompt: str) -> tuple[str, dict[str, int | str | None]]: ...


def technical_response_json_schema() -> dict[str, Any]:
    return TechnicalBlueprintResponse.model_json_schema()


def build_technical_generation_config(types_module: Any) -> Any:
    return types_module.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=technical_response_json_schema(),
        temperature=0,
        automatic_function_calling=types_module.AutomaticFunctionCallingConfig(disable=True),
        http_options=types_module.HttpOptions(retry_options=types_module.HttpRetryOptions(attempts=1)),
    )


class GoogleTechnicalProvider:
    def __init__(self, api_key: str | None, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self.model = model
        self._client = client

    def generate(self, prompt: str) -> tuple[str, dict[str, int | str | None]]:
        if not self._api_key and self._client is None:
            raise TechnicalSmokeTestError("Gemini is not configured")
        try:
            from google import genai
            from google.genai import types

            client = self._client or genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=build_technical_generation_config(types),
            )
        except Exception as error:
            raise TechnicalSmokeTestError("Gemini technical request failed", request_count=1) from error
        if not response.text:
            raise TechnicalSmokeTestError("Gemini returned an empty technical response", request_count=1)
        usage = response.usage_metadata
        return response.text, {
            "provider_request_id": getattr(response, "response_id", None),
            "input_tokens": getattr(usage, "prompt_token_count", None) if usage else None,
            "output_tokens": getattr(usage, "candidates_token_count", None) if usage else None,
            "total_tokens": getattr(usage, "total_token_count", None) if usage else None,
        }


def select_technical_request(plan: BlueprintEvidencePlan) -> BlueprintSemanticRequest:
    technical = [request for request in plan.semantic_requests if request.category == SemanticRequestCategory.TECHNICAL]
    if len(technical) != 1:
        raise TechnicalSmokeTestError(f"Technical-only mode requires exactly one TECHNICAL request; found {len(technical)}")
    return technical[0]


def serialize_technical_request(request: BlueprintSemanticRequest) -> str:
    if request.category != SemanticRequestCategory.TECHNICAL:
        raise TechnicalSmokeTestError("Technical-only mode rejected a non-TECHNICAL request")
    return (
        "Construct TenderIQ technical evaluation requirements using only the supplied evidence. Return strict JSON matching "
        "the response schema. Every requirement must cite supplied evidence_ids. Preserve criterion maximum marks and minimum "
        "qualifying marks as separate fields. Represent an overall technical threshold separately with kind=OVERALL_THRESHOLD. "
        "Do not pool numbers across criteria, invent values, or infer unsupported mandatory status. Use null for absent values "
        "and requires_review=true for genuine ambiguity. Merge only equivalent repeated requirements.\n\n"
        f"SEMANTIC CATEGORY: {request.category.value}\nREQUEST ID: {request.request_id}\n\n{request.compact_context}"
    )


def parse_technical_response(payload: str) -> TechnicalBlueprintResponse:
    try:
        return TechnicalBlueprintResponse.model_validate_json(payload)
    except (ValidationError, ValueError) as error:
        raise TechnicalSmokeTestError("Gemini technical response failed strict schema validation", 1) from error


def _words(text: str) -> set[str]:
    return {word.casefold() for word in _WORD.findall(text) if len(word) > 2 and word.casefold() not in _STOP_WORDS}


def _claim_supported(response: TechnicalRequirementResponse, items: list[BlueprintEvidenceItem]) -> bool:
    claim = _words(f"{response.title} {response.description}")
    evidence = {word for item in items for word in _words(item.text)}
    return bool(claim & evidence)


def _table_facts(text: str, title_words: set[str]) -> LocalScoreFacts | None:
    lines = [line.strip() for line in text.splitlines() if "|" in line]
    if len(lines) < 2:
        return None
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
    header_index = next(
        (index for index, row in enumerate(rows) if any("max" in cell.casefold() for cell in row) and any("min" in cell.casefold() for cell in row)),
        None,
    )
    if header_index is None:
        return None
    header = rows[header_index]
    max_index = next(index for index, cell in enumerate(header) if "max" in cell.casefold())
    min_index = next(index for index, cell in enumerate(header) if "min" in cell.casefold())
    candidates: list[tuple[int, list[str]]] = []
    for row in rows[header_index + 1 :]:
        if max(max_index, min_index) >= len(row):
            continue
        candidates.append((len(title_words & _words(" ".join(row))), row))
    if not candidates or max(score for score, _row in candidates) == 0:
        return None
    _score, row = max(candidates, key=lambda pair: pair[0])
    try:
        return LocalScoreFacts(maximum_marks=float(row[max_index]), minimum_qualifying_marks=float(row[min_index]))
    except ValueError:
        return None


def _score_facts(response: TechnicalRequirementResponse, items: list[BlueprintEvidenceItem]) -> LocalScoreFacts:
    title_words = _words(response.title)
    ranked = sorted(items, key=lambda item: len(title_words & _words(item.text)), reverse=True)
    if not ranked:
        return LocalScoreFacts()
    best_score = len(title_words & _words(ranked[0].text))
    relevant = [item for item in ranked if len(title_words & _words(item.text)) == best_score]
    if response.kind == TechnicalRequirementKind.OVERALL_THRESHOLD:
        for item in relevant:
            if match := _OVERALL.search(item.text):
                return LocalScoreFacts(
                    threshold_value=float(match.group(1)),
                    threshold_operator=normalize_operator(item.text),
                )
        return LocalScoreFacts()
    for item in relevant:
        if table := _table_facts(item.text, title_words):
            return table
        maximum = _MAXIMUM.search(item.text)
        minimum = _MINIMUM.search(item.text)
        if maximum or minimum:
            return LocalScoreFacts(
                maximum_marks=float(maximum.group(1)) if maximum else None,
                minimum_qualifying_marks=float(minimum.group(1)) if minimum else None,
            )
    return LocalScoreFacts()


def _associated_score_record(
    response: TechnicalRequirementResponse,
    request: BlueprintSemanticRequest,
    item_index: dict[str, BlueprintEvidenceItem],
):
    if response.kind != TechnicalRequirementKind.SCORED_CRITERION:
        return None
    title_words = _words(response.title)
    ranked = []
    for record in request.records:
        item = item_index.get(record.evidence_id)
        if item is None or "[TECHNICAL SCORE ROW]" not in item.text:
            continue
        score = len(title_words & _words(item.text.split("Maximum Marks:", 1)[0]))
        if score:
            ranked.append((score, record, item))
    if not ranked:
        return None
    ranked.sort(key=lambda value: value[0], reverse=True)
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1], ranked[0][2]


def _evidence_index(plan: BlueprintEvidencePlan) -> dict[str, BlueprintEvidenceItem]:
    return {item.evidence_id: item for package in plan.packages for item in package.evidence_items}


def _unique_sources(items: list[BlueprintEvidenceItem]) -> list[SourceReference]:
    unique: dict[tuple[int, str, str, str], SourceReference] = {}
    for item in items:
        for source in item.source_references:
            unique[(source.page_number, source.section or "", source.clause or "", source.excerpt.casefold())] = source
    return [unique[key] for key in sorted(unique)]


def _restore(
    response: TechnicalRequirementResponse,
    request: BlueprintSemanticRequest,
    item_index: dict[str, BlueprintEvidenceItem],
) -> GroundedTechnicalRequirement | None:
    records_by_handle = {record.handle: record for record in request.records}
    if any(handle not in records_by_handle for handle in response.evidence_ids):
        return None
    records = [records_by_handle[handle] for handle in dict.fromkeys(response.evidence_ids)]
    items = [item_index[record.evidence_id] for record in records if record.evidence_id in item_index]
    if len(items) != len(records) or not _claim_supported(response, items):
        return None
    associated = _associated_score_record(response, request, item_index)
    if associated is not None:
        score_record, score_item = associated
        if score_record.handle not in {record.handle for record in records}:
            records.append(score_record)
            items.append(score_item)
    facts = _score_facts(response, items)
    conflicts: list[str] = []

    def authoritative(name: str, proposed: float | None, local: float | None) -> float | None:
        if local is None:
            return proposed
        if proposed is not None and proposed != local:
            conflicts.append(f"Gemini {name} conflicted with grounded local evidence")
        return local

    maximum = authoritative("maximum marks", response.maximum_marks, facts.maximum_marks)
    minimum = authoritative("minimum qualifying marks", response.minimum_qualifying_marks, facts.minimum_qualifying_marks)
    threshold = authoritative("overall threshold", response.threshold_value, facts.threshold_value)
    operator = response.threshold_operator
    if facts.threshold_operator is not None:
        if operator is not None and operator != facts.threshold_operator:
            conflicts.append("Gemini threshold operator conflicted with grounded local evidence")
        operator = facts.threshold_operator
    evidence_review = any(item.requires_review for item in items)
    reasons = [response.review_reason] if response.review_reason else []
    if evidence_review:
        reasons.append("Grounded local evidence requires review")
    reasons.extend(conflicts)
    requires_review = response.requires_review or evidence_review or bool(conflicts)
    identity = "|".join([
        response.kind.value,
        response.title.casefold(),
        response.description.casefold(),
        str(maximum), str(minimum), str(threshold), str(operator),
        *sorted(record.evidence_id for record in records),
    ])
    return GroundedTechnicalRequirement(
        requirement_id=f"TREQ-{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
        kind=response.kind,
        title=response.title,
        description=response.description,
        mandatory=response.mandatory,
        maximum_marks=maximum,
        minimum_qualifying_marks=minimum,
        threshold_value=threshold,
        threshold_operator=operator,
        weight_percent=response.weight_percent,
        expected_evidence=response.expected_evidence,
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


def _deduplicate(requirements: list[GroundedTechnicalRequirement]) -> list[GroundedTechnicalRequirement]:
    results: dict[tuple[object, ...], GroundedTechnicalRequirement] = {}
    for requirement in requirements:
        key = (
            requirement.kind,
            " ".join(requirement.title.casefold().split()),
            requirement.maximum_marks,
            requirement.minimum_qualifying_marks,
            requirement.threshold_value,
            requirement.threshold_operator,
        )
        existing = results.get(key)
        if existing is None:
            results[key] = requirement
            continue
        results[key] = existing.model_copy(update={
            "evidence_handles": sorted(set(existing.evidence_handles + requirement.evidence_handles)),
            "evidence_ids": sorted(set(existing.evidence_ids + requirement.evidence_ids)),
            "source_pages": sorted(set(existing.source_pages + requirement.source_pages)),
            "source_section_ids": sorted(set(existing.source_section_ids + requirement.source_section_ids)),
            "source_work_unit_ids": sorted(set(existing.source_work_unit_ids + requirement.source_work_unit_ids)),
            "candidate_ids": sorted(set(existing.candidate_ids + requirement.candidate_ids)),
            "source_references": existing.source_references + [source for source in requirement.source_references if source not in existing.source_references],
            "requires_review": existing.requires_review or requirement.requires_review,
            "review_reason": existing.review_reason or requirement.review_reason,
        })
    return list(results.values())


def _local_scored_requirements(
    request: BlueprintSemanticRequest,
    item_index: dict[str, BlueprintEvidenceItem],
    represented: list[GroundedTechnicalRequirement],
) -> list[GroundedTechnicalRequirement]:
    represented_evidence = {
        evidence_id
        for requirement in represented
        if requirement.kind == TechnicalRequirementKind.SCORED_CRITERION
        for evidence_id in requirement.evidence_ids
    }
    local: list[GroundedTechnicalRequirement] = []
    for record in request.records:
        item = item_index.get(record.evidence_id)
        if item is None or item.evidence_id in represented_evidence or "[TECHNICAL SCORE ROW]" not in item.text:
            continue
        title_match = _ROW_TITLE.search(item.text)
        maximum = _MAXIMUM.search(item.text)
        minimum = _MINIMUM.search(item.text)
        if title_match is None or maximum is None or minimum is None:
            continue
        title = title_match.group(1).strip()
        description_match = _ROW_DESCRIPTION.search(item.text)
        description = description_match.group(1).strip() if description_match else title
        identity = "|".join([
            TechnicalRequirementKind.SCORED_CRITERION.value,
            title.casefold(),
            maximum.group(1),
            minimum.group(1),
            item.evidence_id,
        ])
        local.append(GroundedTechnicalRequirement(
            requirement_id=f"TREQ-{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
            kind=TechnicalRequirementKind.SCORED_CRITERION,
            title=title,
            description=description or title,
            maximum_marks=float(maximum.group(1)),
            minimum_qualifying_marks=float(minimum.group(1)),
            evidence_handles=[record.handle],
            evidence_ids=[item.evidence_id],
            source_pages=item.source_pages,
            source_section_ids=item.source_section_ids,
            source_work_unit_ids=item.source_work_unit_ids,
            candidate_ids=item.candidate_ids,
            source_references=item.source_references,
            source_categories=item.categories,
            requires_review=item.requires_review,
            review_reason="Grounded local evidence requires review" if item.requires_review else None,
        ))
    return local


class TechnicalBlueprintService:
    def __init__(self, provider: TechnicalResponseProvider, clock: Callable[[], float] = time.perf_counter) -> None:
        self._provider = provider
        self._clock = clock

    def execute(self, plan: BlueprintEvidencePlan) -> TechnicalExecutionResult:
        request = select_technical_request(plan)
        started = self._clock()
        try:
            payload, metadata = self._provider.generate(serialize_technical_request(request))
        except TechnicalSmokeTestError:
            raise
        except Exception as error:
            raise TechnicalSmokeTestError("Technical provider failed", request_count=1) from error
        latency_ms = (self._clock() - started) * 1000
        parsed = parse_technical_response(payload)
        known_handles = {record.handle for record in request.records}
        unsupported = sum(handle not in known_handles for item in parsed.requirements for handle in item.evidence_ids)
        item_index = _evidence_index(plan)
        restored = [item for response in parsed.requirements if (item := _restore(response, request, item_index)) is not None]
        local_scored = _local_scored_requirements(request, item_index, restored)
        accepted = _deduplicate([*restored, *local_scored])
        return TechnicalExecutionResult(
            requirements=accepted,
            generated_count=len(parsed.requirements),
            accepted_count=len(accepted),
            review_required_count=sum(item.requires_review for item in accepted),
            rejected_count=len(parsed.requirements) - len(restored),
            unsupported_evidence_handle_count=unsupported,
            usage=TechnicalUsage(
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
