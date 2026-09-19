import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from pydantic import ValidationError

from app.models.blueprint import SourceReference
from app.models.blueprint_evidence import BlueprintEvidenceItem, BlueprintEvidencePlan, BlueprintSemanticRequest, SemanticRequestCategory
from app.models.contractual_other_blueprint import (
    ContractualOtherBlueprintResponse, ContractualOtherExecutionResult, ContractualOtherUsage,
    ContractualParty, ContractualRuleResponse, DurationUnit, GroundedContractualRule, ObligationSemantics,
)

_WORD = re.compile(r"[a-z0-9]+", re.I)
_STOP = {"a", "an", "and", "as", "be", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with", "rule", "requirement"}
_DURATION = re.compile(r"\b(?:within|for(?:\s+a\s+period\s+of)?|valid\s+for|after)\s+(\d+(?:\.\d+)?)\s+(hours?|days?|weeks?|months?|years?)\b", re.I)
_DATE = re.compile(r"\b(?:on\s+or\s+before\s+)?(?:\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})\b", re.I)
_MONEY = re.compile(r"(?:\b(INR|USD|EUR)|₹)\s*([\d,]+(?:\.\d+)?)\s*(crores?|lakhs?)?", re.I)
_PERCENT = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%")


@dataclass(frozen=True)
class LocalContractFacts:
    responsible_party: ContractualParty | None = None
    obligation_semantics: ObligationSemantics | None = None
    percentage_value: Decimal | None = None
    money_value: Decimal | None = None
    currency: str | None = None
    duration_value: Decimal | None = None
    duration_unit: DurationUnit | None = None
    deadline_or_timing: str | None = None
    actor_ambiguous: bool = False
    semantics_ambiguous: bool = False


class ContractualOtherSmokeTestError(Exception):
    def __init__(self, message: str, request_count: int = 0) -> None:
        super().__init__(message)
        self.request_count = request_count


class ContractualOtherResponseProvider(Protocol):
    model: str
    def generate(self, prompt: str) -> tuple[str, dict[str, int | str | None]]: ...


def contractual_other_response_json_schema() -> dict[str, Any]:
    return ContractualOtherBlueprintResponse.model_json_schema()


def build_contractual_other_generation_config(types_module: Any) -> Any:
    return types_module.GenerateContentConfig(
        response_mime_type="application/json", response_json_schema=contractual_other_response_json_schema(), temperature=0,
        automatic_function_calling=types_module.AutomaticFunctionCallingConfig(disable=True),
        http_options=types_module.HttpOptions(retry_options=types_module.HttpRetryOptions(attempts=1)),
    )


class GoogleContractualOtherProvider:
    def __init__(self, api_key: str | None, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self.model = model
        self._client = client

    def generate(self, prompt: str) -> tuple[str, dict[str, int | str | None]]:
        if not self._api_key and self._client is None:
            raise ContractualOtherSmokeTestError("Gemini is not configured")
        try:
            from google import genai
            from google.genai import types
            client = self._client or genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self.model, contents=prompt, config=build_contractual_other_generation_config(types)
            )
        except Exception as error:
            raise ContractualOtherSmokeTestError("Gemini contractual-other request failed", 1) from error
        if not response.text:
            raise ContractualOtherSmokeTestError("Gemini returned an empty contractual-other response", 1)
        usage = response.usage_metadata
        return response.text, {
            "provider_request_id": getattr(response, "response_id", None),
            "input_tokens": getattr(usage, "prompt_token_count", None) if usage else None,
            "output_tokens": getattr(usage, "candidates_token_count", None) if usage else None,
            "total_tokens": getattr(usage, "total_token_count", None) if usage else None,
        }


def select_contractual_other_requests(plan: BlueprintEvidencePlan) -> list[BlueprintSemanticRequest]:
    selected = [request for request in plan.semantic_requests if request.category == SemanticRequestCategory.CONTRACTUAL_OTHER]
    if not selected:
        raise ContractualOtherSmokeTestError("Contractual-other-only mode requires at least one CONTRACTUAL_OTHER request")
    return selected


def serialize_contractual_other_request(request: BlueprintSemanticRequest) -> str:
    if request.category != SemanticRequestCategory.CONTRACTUAL_OTHER:
        raise ContractualOtherSmokeTestError("Contractual-other-only mode rejected another category")
    return (
        "Construct grounded contractual and other procurement rules using only supplied evidence. Return strict JSON matching "
        "the schema and cite evidence_ids for every rule. Preserve who must do what, obligation/prohibition/right semantics, "
        "conditions, timing, measurable values, and consequences only when grounded. Keep relative durations distinct from "
        "absolute dates. Do not pool nearby numbers or invent legal meaning, actors, documents, remedies, or mandatory status. "
        "Use null for absent structure and requires_review=true for genuine ambiguity.\n\n"
        f"SEMANTIC CATEGORY: {request.category.value}\nREQUEST ID: {request.request_id}\n\n{request.compact_context}"
    )


def parse_contractual_other_response(payload: str) -> ContractualOtherBlueprintResponse:
    try:
        return ContractualOtherBlueprintResponse.model_validate_json(payload)
    except (ValidationError, ValueError) as error:
        raise ContractualOtherSmokeTestError("Contractual-other response failed strict schema validation", 1) from error


def _words(text: str) -> set[str]:
    return {word.casefold() for word in _WORD.findall(text) if len(word) > 2 and word.casefold() not in _STOP}


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool): return None
    try: return Decimal(str(value).replace(",", ""))
    except InvalidOperation: return None


def _actor(text: str) -> ContractualParty | None:
    patterns = (
        (ContractualParty.BOTH_PARTIES, r"\b(?:both|either)\s+part(?:y|ies)\b"),
        (ContractualParty.SELECTED_BIDDER, r"\bselected bidder\b"),
        (ContractualParty.SERVICE_PROVIDER, r"\bservice provider\b"),
        (ContractualParty.BIDDER, r"\bbidder(?:'s)?\b"),
        (ContractualParty.VENDOR, r"\bvendor\b"),
        (ContractualParty.PURCHASER, r"\bpurchaser\b"),
        (ContractualParty.CLIENT, r"\bclient\b"),
        (ContractualParty.AUTHORITY, r"\bauthority\b"),
    )
    modal = r"\s+(?:shall(?:\s+not)?|must(?:\s+not)?|may|should|will|is\s+expected\s+to)\b"
    for party, pattern in patterns:
        if re.search(pattern + modal, text, re.I): return party
    named_party = re.search(r"\b([A-Z][A-Z0-9]{2,})\s+(?:shall(?:\s+not)?|must(?:\s+not)?|may|should)\b", text)
    if named_party and named_party.group(1) not in {"RFP", "SLA", "EMD", "PBG"}:
        return ContractualParty.CLIENT
    return None


def _semantics(text: str, actor: ContractualParty | None) -> ObligationSemantics | None:
    lowered = text.casefold()
    if re.search(r"\bshall\s+be\s+entitled\s+to\b", lowered): return ObligationSemantics.RIGHT
    if re.search(r"\b(?:shall|must)\s+not\b", lowered): return ObligationSemantics.MUST_NOT
    if re.search(r"\b(?:shall|must)\b", lowered): return ObligationSemantics.MUST
    if re.search(r"\bmay\b", lowered):
        return ObligationSemantics.RIGHT if re.search(r"\bmay\s+(?:terminate|appeal|refer|raise|exercise|claim|elect)\b", lowered) else ObligationSemantics.MAY
    if re.search(r"\bshould\b", lowered): return ObligationSemantics.SHOULD
    if re.search(r"\bcan\s+(?:appeal|refer|raise|exercise|claim)\b", lowered): return ObligationSemantics.RIGHT
    if re.search(r"\bif\b|\bsubject to\b|\bin the event\b", lowered): return ObligationSemantics.CONDITIONAL
    return None


def _unique_match(pattern: re.Pattern, text: str, converter: Callable[[re.Match], tuple]) -> tuple | None:
    values = {converter(match) for match in pattern.finditer(text)}
    return next(iter(values)) if len(values) == 1 else None


def _relevant_clauses(text: str, claim: str) -> list[str]:
    clauses = [part.strip() for part in re.split(r"(?<=[.;!?])\s+|\n+", text) if part.strip()]
    claim_words = _words(claim)
    scored = [(len(claim_words & _words(clause)), clause) for clause in clauses]
    best = max((score for score, _clause in scored), default=0)
    return [clause for score, clause in scored if score == best] if best else clauses or [text]


def _facts(text: str, claim: str = "") -> LocalContractFacts:
    clauses = _relevant_clauses(text, claim)
    actors = {_actor(clause) for clause in clauses} - {None}
    semantics = {_semantics(clause, _actor(clause)) for clause in clauses} - {None}
    selected = "\n".join(clauses)
    duration = _unique_match(_DURATION, selected, lambda m: (
        Decimal(m.group(1)), DurationUnit(m.group(2).casefold().rstrip("s").upper())
    ))
    money = _unique_match(_MONEY, selected, lambda m: (
        Decimal(m.group(2).replace(",", "")) * (Decimal(10_000_000) if (m.group(3) or "").casefold().startswith("crore") else Decimal(100_000) if (m.group(3) or "").casefold().startswith("lakh") else Decimal(1)),
        (m.group(1) or "INR").upper(),
    ))
    percentage = _unique_match(_PERCENT, selected, lambda m: (Decimal(m.group(1)),))
    dates = {match.group(0).strip() for match in _DATE.finditer(selected)}
    return LocalContractFacts(
        responsible_party=next(iter(actors)) if len(actors) == 1 else None,
        obligation_semantics=next(iter(semantics)) if len(semantics) == 1 else None,
        percentage_value=percentage[0] if percentage else None,
        money_value=money[0] if money else None, currency=money[1] if money else None,
        duration_value=duration[0] if duration else None, duration_unit=duration[1] if duration else None,
        deadline_or_timing=next(iter(dates)) if len(dates) == 1 else None,
        actor_ambiguous=len(actors) > 1, semantics_ambiguous=len(semantics) > 1,
    )


def _evidence_index(plan: BlueprintEvidencePlan) -> dict[str, BlueprintEvidenceItem]:
    return {item.evidence_id: item for package in plan.packages for item in package.evidence_items}


def _unique_sources(items: list[BlueprintEvidenceItem]) -> list[SourceReference]:
    unique = {(s.page_number, s.section or "", s.clause or "", s.excerpt.casefold()): s for item in items for s in item.source_references}
    return [unique[key] for key in sorted(unique)]


def _restore(response: ContractualRuleResponse, request: BlueprintSemanticRequest, index: dict[str, BlueprintEvidenceItem]) -> GroundedContractualRule | None:
    records_by_handle = {record.handle: record for record in request.records}
    if any(handle not in records_by_handle for handle in response.evidence_ids): return None
    records = [records_by_handle[handle] for handle in dict.fromkeys(response.evidence_ids)]
    items = [index[record.evidence_id] for record in records if record.evidence_id in index]
    claim = _words(f"{response.title} {response.description} {response.action_or_obligation or ''}")
    evidence = {word for item in items for word in _words(item.text)}
    if len(items) != len(records) or not claim & evidence: return None
    grounded_text = "\n".join(item.text for item in items)
    claim_text = f"{response.title} {response.description} {response.action_or_obligation or ''} {response.condition or ''}"
    local = _facts(grounded_text, claim_text)
    conflicts: list[str] = []

    def authority(label: str, proposed, grounded):
        if grounded is None: return proposed
        if proposed is not None and proposed != grounded: conflicts.append(f"Gemini {label} conflicted with grounded local evidence")
        return grounded

    actor = authority("responsible party", response.responsible_party, local.responsible_party)
    semantics = authority("obligation semantics", response.obligation_semantics, local.obligation_semantics)
    percentage = authority("percentage", _decimal(response.percentage_value), local.percentage_value)
    money = authority("money value", _decimal(response.money_value), local.money_value)
    currency = authority("currency", response.currency.upper() if response.currency else None, local.currency)
    duration = authority("duration value", _decimal(response.duration_value), local.duration_value)
    duration_unit = authority("duration unit", response.duration_unit, local.duration_unit)
    deadline = authority("absolute deadline", response.deadline_or_timing, local.deadline_or_timing)
    evidence_review = any(item.requires_review for item in items)
    reasons = ([response.review_reason] if response.review_reason else []) + conflicts
    if local.actor_ambiguous: reasons.append("Grounded clauses contain multiple potentially responsible parties")
    if local.semantics_ambiguous: reasons.append("Grounded clauses contain multiple obligation modalities")
    if evidence_review: reasons.append("Grounded local evidence requires review")
    identity = "|".join([
        response.kind.value, " ".join(response.description.casefold().split()), str(actor), str(semantics),
        str(percentage), str(money), str(duration), str(duration_unit), response.consequence_or_remedy or "",
        *sorted(record.evidence_id for record in records),
    ])
    return GroundedContractualRule(
        **response.model_dump(exclude={"evidence_ids", "responsible_party", "obligation_semantics", "percentage_value", "money_value", "currency", "duration_value", "duration_unit", "deadline_or_timing", "requires_review", "review_reason"}),
        rule_id=f"COR-{hashlib.sha256(identity.encode()).hexdigest()[:20]}", responsible_party=actor,
        obligation_semantics=semantics, percentage_value=float(percentage) if percentage is not None else None,
        money_value=format(money, "f") if money is not None else response.money_value, currency=currency,
        duration_value=float(duration) if duration is not None else None, duration_unit=duration_unit,
        deadline_or_timing=deadline, evidence_handles=[record.handle for record in records],
        evidence_ids=[record.evidence_id for record in records], source_pages=sorted({p for item in items for p in item.source_pages}),
        source_section_ids=sorted({v for item in items for v in item.source_section_ids}),
        source_work_unit_ids=sorted({v for item in items for v in item.source_work_unit_ids}),
        candidate_ids=sorted({v for item in items for v in item.candidate_ids}), source_references=_unique_sources(items),
        source_categories=sorted({v for item in items for v in item.categories}, key=lambda v: v.value),
        requires_review=response.requires_review or evidence_review or local.actor_ambiguous or local.semantics_ambiguous or bool(conflicts),
        review_reason="; ".join(dict.fromkeys(reasons)) or None,
    )


def _deduplicate(rules: list[GroundedContractualRule]) -> list[GroundedContractualRule]:
    result = {}
    for rule in rules:
        key = (" ".join(rule.description.casefold().split()), rule.kind, rule.responsible_party, rule.obligation_semantics,
               rule.percentage_value, rule.money_value, rule.duration_value, rule.duration_unit,
               " ".join((rule.consequence_or_remedy or "").casefold().split()))
        existing = result.get(key)
        if existing is None: result[key] = rule; continue
        result[key] = existing.model_copy(update={
            "evidence_handles": sorted(set(existing.evidence_handles + rule.evidence_handles)),
            "evidence_ids": sorted(set(existing.evidence_ids + rule.evidence_ids)),
            "source_pages": sorted(set(existing.source_pages + rule.source_pages)),
            "source_section_ids": sorted(set(existing.source_section_ids + rule.source_section_ids)),
            "source_work_unit_ids": sorted(set(existing.source_work_unit_ids + rule.source_work_unit_ids)),
            "candidate_ids": sorted(set(existing.candidate_ids + rule.candidate_ids)),
            "source_references": existing.source_references + [s for s in rule.source_references if s not in existing.source_references],
            "requires_review": existing.requires_review or rule.requires_review,
            "review_reason": existing.review_reason or rule.review_reason,
        })
    return list(result.values())


class ContractualOtherBlueprintService:
    def __init__(self, provider: ContractualOtherResponseProvider, clock: Callable[[], float] = time.perf_counter) -> None:
        self._provider = provider
        self._clock = clock

    def execute(self, plan: BlueprintEvidencePlan) -> ContractualOtherExecutionResult:
        requests = select_contractual_other_requests(plan)
        index = _evidence_index(plan)
        restored: list[GroundedContractualRule] = []
        generated = unsupported = rejected = 0
        input_tokens = output_tokens = total_tokens = 0
        token_fields_present = {"input": False, "output": False, "total": False}
        started = self._clock()
        for request in requests:
            try: payload, metadata = self._provider.generate(serialize_contractual_other_request(request))
            except ContractualOtherSmokeTestError: raise
            except Exception as error: raise ContractualOtherSmokeTestError("Contractual-other provider failed", len(requests)) from error
            parsed = parse_contractual_other_response(payload)
            generated += len(parsed.rules)
            known = {record.handle for record in request.records}
            unsupported += sum(handle not in known for rule in parsed.rules for handle in rule.evidence_ids)
            batch = [item for response in parsed.rules if (item := _restore(response, request, index)) is not None]
            restored.extend(batch); rejected += len(parsed.rules) - len(batch)
            for field, target in (("input_tokens", "input"), ("output_tokens", "output"), ("total_tokens", "total")):
                value = metadata.get(field)
                if isinstance(value, int):
                    token_fields_present[target] = True
                    if target == "input": input_tokens += value
                    elif target == "output": output_tokens += value
                    else: total_tokens += value
        accepted = _deduplicate(restored)
        return ContractualOtherExecutionResult(
            rules=accepted, generated_count=generated, accepted_count=len(accepted),
            review_required_count=sum(rule.requires_review for rule in accepted), rejected_count=rejected,
            unsupported_evidence_handle_count=unsupported,
            usage=ContractualOtherUsage(
                model=self._provider.model, request_ids=[request.request_id for request in requests],
                evidence_record_count=sum(len(request.records) for request in requests),
                input_characters=sum(request.character_count for request in requests),
                input_tokens=input_tokens if token_fields_present["input"] else None,
                output_tokens=output_tokens if token_fields_present["output"] else None,
                total_tokens=total_tokens if token_fields_present["total"] else None,
                latency_ms=(self._clock() - started) * 1000, request_count=len(requests), retry_count=0, success=True,
            ),
        )
