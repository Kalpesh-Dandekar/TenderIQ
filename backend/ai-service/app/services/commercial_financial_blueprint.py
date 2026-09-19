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
from app.models.commercial_financial_blueprint import (
    CommercialFinancialBlueprintResponse,
    CommercialFinancialExecutionResult,
    CommercialFinancialRuleKind,
    CommercialFinancialRuleResponse,
    CommercialFinancialUsage,
    FormulaSemantics,
    FormulaVariableRole,
    GroundedCommercialFinancialRule,
)

_WORD = re.compile(r"[a-z0-9]+", re.I)
_STOP = {"a", "an", "and", "as", "be", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with", "score", "formula", "rule"}
_FINANCIAL_FORMULA = re.compile(
    r"financial\s+score\s*=\s*\(?\s*lowest\s+bid\s+value\s*/\s*bid\s+value\s+of\s+bidder\s*\)?\s*[*x×]\s*100",
    re.I,
)
_CONSOLIDATED_FORMULA = re.compile(
    r"consolidated\s+(?:bid\s+)?score\s*=\s*technical\s+score\s*[*x×]\s*(0?\.\d+|\d+(?:\.\d+)?)\s*\+\s*financial\s+score\s*[*x×]\s*(0?\.\d+|\d+(?:\.\d+)?)",
    re.I,
)
_MONEY = re.compile(r"\b(INR|USD|EUR)\s*(\d+(?:\.\d+)?)\s*(crores?|lakhs?)?\b", re.I)


@dataclass(frozen=True)
class LocalFinancialFacts:
    formula_expression: str | None = None
    formula_variables: tuple[FormulaVariableRole, ...] = ()
    formula_semantics: FormulaSemantics | None = None
    formula_multiplier: Decimal | None = None
    technical_weight_percent: Decimal | None = None
    financial_weight_percent: Decimal | None = None
    money_value: Decimal | None = None
    currency: str | None = None


class CommercialFinancialSmokeTestError(Exception):
    def __init__(self, message: str, request_count: int = 0) -> None:
        super().__init__(message)
        self.request_count = request_count


class CommercialFinancialResponseProvider(Protocol):
    model: str
    def generate(self, prompt: str) -> tuple[str, dict[str, int | str | None]]: ...


def commercial_financial_response_json_schema() -> dict[str, Any]:
    return CommercialFinancialBlueprintResponse.model_json_schema()


def build_commercial_financial_generation_config(types_module: Any) -> Any:
    return types_module.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=commercial_financial_response_json_schema(),
        temperature=0,
        automatic_function_calling=types_module.AutomaticFunctionCallingConfig(disable=True),
        http_options=types_module.HttpOptions(retry_options=types_module.HttpRetryOptions(attempts=1)),
    )


class GoogleCommercialFinancialProvider:
    def __init__(self, api_key: str | None, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self.model = model
        self._client = client

    def generate(self, prompt: str) -> tuple[str, dict[str, int | str | None]]:
        if not self._api_key and self._client is None:
            raise CommercialFinancialSmokeTestError("Gemini is not configured")
        try:
            from google import genai
            from google.genai import types
            client = self._client or genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self.model, contents=prompt, config=build_commercial_financial_generation_config(types)
            )
        except Exception as error:
            raise CommercialFinancialSmokeTestError("Gemini commercial-financial request failed", 1) from error
        if not response.text:
            raise CommercialFinancialSmokeTestError("Gemini returned an empty commercial-financial response", 1)
        usage = response.usage_metadata
        return response.text, {
            "provider_request_id": getattr(response, "response_id", None),
            "input_tokens": getattr(usage, "prompt_token_count", None) if usage else None,
            "output_tokens": getattr(usage, "candidates_token_count", None) if usage else None,
            "total_tokens": getattr(usage, "total_token_count", None) if usage else None,
        }


def select_commercial_financial_request(plan: BlueprintEvidencePlan) -> BlueprintSemanticRequest:
    selected = [request for request in plan.semantic_requests if request.category == SemanticRequestCategory.COMMERCIAL_FINANCIAL]
    if len(selected) != 1:
        raise CommercialFinancialSmokeTestError(
            f"Commercial-financial-only mode requires exactly one COMMERCIAL_FINANCIAL request; found {len(selected)}"
        )
    return selected[0]


def serialize_commercial_financial_request(request: BlueprintSemanticRequest) -> str:
    if request.category != SemanticRequestCategory.COMMERCIAL_FINANCIAL:
        raise CommercialFinancialSmokeTestError("Commercial-financial-only mode rejected another category")
    return (
        "Construct TenderIQ commercial and financial rules using only supplied evidence. Return strict JSON matching the schema. "
        "Every rule must cite supplied evidence_ids. Keep financial-score formulas, weighted consolidation formulas, and simple "
        "commercial rules distinct. Preserve variables, formula semantics, multipliers, technical and financial weights separately. "
        "Do not treat formula multipliers or weights as thresholds. Use null for absent values and requires_review=true for genuine "
        "ambiguity. Do not invent requirements, values, currencies, formulas, or handles.\n\n"
        f"SEMANTIC CATEGORY: {request.category.value}\nREQUEST ID: {request.request_id}\n\n{request.compact_context}"
    )


def parse_commercial_financial_response(payload: str) -> CommercialFinancialBlueprintResponse:
    try:
        return CommercialFinancialBlueprintResponse.model_validate_json(payload)
    except (ValidationError, ValueError) as error:
        raise CommercialFinancialSmokeTestError("Commercial-financial response failed strict schema validation", 1) from error


def _words(text: str) -> set[str]:
    return {word.casefold() for word in _WORD.findall(text) if len(word) > 2 and word.casefold() not in _STOP}


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def _percent(value: object) -> Decimal | None:
    parsed = _decimal(value)
    if parsed is None:
        return None
    return parsed * 100 if 0 <= parsed <= 1 else parsed


_VARIABLE_ALIASES = {
    "lowest bid": FormulaVariableRole.LOWEST_VALID_BID,
    "lowest bid value": FormulaVariableRole.LOWEST_VALID_BID,
    "lowest valid bid": FormulaVariableRole.LOWEST_VALID_BID,
    "bid value": FormulaVariableRole.BIDDER_BID_VALUE,
    "bid value of bidder": FormulaVariableRole.BIDDER_BID_VALUE,
    "bidder bid value": FormulaVariableRole.BIDDER_BID_VALUE,
    "technical score": FormulaVariableRole.TECHNICAL_SCORE,
    "financial score": FormulaVariableRole.FINANCIAL_SCORE,
    "consolidated bid score": FormulaVariableRole.CONSOLIDATED_SCORE,
    "consolidated score": FormulaVariableRole.CONSOLIDATED_SCORE,
    "technical weight": FormulaVariableRole.TECHNICAL_WEIGHT,
    "financial weight": FormulaVariableRole.FINANCIAL_WEIGHT,
}


def _canonical_variable_role(value: FormulaVariableRole | str) -> FormulaVariableRole | None:
    if isinstance(value, FormulaVariableRole):
        return value
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())
    return _VARIABLE_ALIASES.get(normalized)


def _formula_variables_conflict(
    proposed: list[FormulaVariableRole], local: LocalFinancialFacts
) -> bool:
    roles = {_canonical_variable_role(value) for value in proposed}
    if None in roles:
        return True
    if local.formula_semantics == FormulaSemantics.RATIO_PERCENT:
        required = {FormulaVariableRole.LOWEST_VALID_BID, FormulaVariableRole.BIDDER_BID_VALUE}
        allowed = required | {FormulaVariableRole.FINANCIAL_SCORE}
    elif local.formula_semantics == FormulaSemantics.WEIGHTED_SUM:
        required = {FormulaVariableRole.TECHNICAL_SCORE, FormulaVariableRole.FINANCIAL_SCORE}
        allowed = required | {FormulaVariableRole.CONSOLIDATED_SCORE}
        if local.technical_weight_percent is not None:
            allowed.add(FormulaVariableRole.TECHNICAL_WEIGHT)
        if local.financial_weight_percent is not None:
            allowed.add(FormulaVariableRole.FINANCIAL_WEIGHT)
    else:
        return set(proposed) != set(local.formula_variables)
    return not required.issubset(roles) or not roles.issubset(allowed)


def _money(text: str) -> tuple[Decimal | None, str | None]:
    match = _MONEY.search(text)
    if not match:
        return None, None
    value = Decimal(match.group(2))
    magnitude = (match.group(3) or "").casefold()
    if magnitude.startswith("crore"):
        value *= Decimal(10_000_000)
    elif magnitude.startswith("lakh"):
        value *= Decimal(100_000)
    return value, match.group(1).upper()


def _facts(text: str) -> LocalFinancialFacts:
    if _FINANCIAL_FORMULA.search(text):
        return LocalFinancialFacts(
            formula_expression="FINANCIAL_SCORE=(LOWEST_VALID_BID/BIDDER_BID_VALUE)*100",
            formula_variables=(FormulaVariableRole.FINANCIAL_SCORE, FormulaVariableRole.LOWEST_VALID_BID, FormulaVariableRole.BIDDER_BID_VALUE),
            formula_semantics=FormulaSemantics.RATIO_PERCENT,
            formula_multiplier=Decimal(100),
        )
    if match := _CONSOLIDATED_FORMULA.search(text):
        technical = _percent(match.group(1))
        financial = _percent(match.group(2))
        return LocalFinancialFacts(
            formula_expression="CONSOLIDATED_SCORE=TECHNICAL_SCORE*TECHNICAL_WEIGHT+FINANCIAL_SCORE*FINANCIAL_WEIGHT",
            formula_variables=(FormulaVariableRole.CONSOLIDATED_SCORE, FormulaVariableRole.TECHNICAL_SCORE, FormulaVariableRole.FINANCIAL_SCORE),
            formula_semantics=FormulaSemantics.WEIGHTED_SUM,
            technical_weight_percent=technical,
            financial_weight_percent=financial,
        )
    money_value, currency = _money(text)
    return LocalFinancialFacts(money_value=money_value, currency=currency)


def _item_index(plan: BlueprintEvidencePlan) -> dict[str, BlueprintEvidenceItem]:
    return {item.evidence_id: item for package in plan.packages for item in package.evidence_items}


def _unique_sources(items: list[BlueprintEvidenceItem]) -> list[SourceReference]:
    unique = {}
    for item in items:
        for source in item.source_references:
            unique[(source.page_number, source.section or "", source.clause or "", source.excerpt.casefold())] = source
    return [unique[key] for key in sorted(unique)]


def _matching_formula_record(response, request, index):
    expected = _FINANCIAL_FORMULA if response.kind == CommercialFinancialRuleKind.FINANCIAL_SCORE_FORMULA else (
        _CONSOLIDATED_FORMULA if response.kind == CommercialFinancialRuleKind.WEIGHTED_SCORE_FORMULA else None
    )
    if expected is None:
        return None
    matches = [(record, index.get(record.evidence_id)) for record in request.records if index.get(record.evidence_id) and expected.search(index[record.evidence_id].text)]
    return matches[0] if len(matches) == 1 else None


def _restore(response, request, index):
    records_by_handle = {record.handle: record for record in request.records}
    if any(handle not in records_by_handle for handle in response.evidence_ids):
        return None
    records = [records_by_handle[handle] for handle in dict.fromkeys(response.evidence_ids)]
    items = [index[record.evidence_id] for record in records if record.evidence_id in index]
    if len(items) != len(records) or not (_words(f"{response.title} {response.description}") & {word for item in items for word in _words(item.text)}):
        return None
    associated = _matching_formula_record(response, request, index)
    if associated and associated[0].handle not in {record.handle for record in records}:
        records.append(associated[0]); items.append(associated[1])
    local = next((facts for item in items if (facts := _facts(item.text)).formula_expression), None)
    if local is None:
        combined = "\n".join(item.text for item in items)
        local = _facts(combined)
    conflicts = []
    formula_expression = response.formula_expression
    variables = response.formula_variables
    semantics = response.formula_semantics
    multiplier = _decimal(response.formula_multiplier)
    technical_weight = _percent(response.technical_weight_percent)
    financial_weight = _percent(response.financial_weight_percent)
    money_value = _decimal(response.money_value)
    currency = response.currency.upper() if response.currency else None
    if local.formula_expression:
        if response.formula_semantics and response.formula_semantics != local.formula_semantics:
            conflicts.append("Gemini formula semantics conflicted with grounded local evidence")
        if response.formula_variables and _formula_variables_conflict(response.formula_variables, local):
            conflicts.append("Gemini formula variables conflicted with grounded local evidence")
        formula_expression = local.formula_expression
        variables = list(local.formula_variables)
        semantics = local.formula_semantics
    if local.formula_multiplier is not None:
        if multiplier is not None and multiplier != local.formula_multiplier:
            conflicts.append("Gemini formula multiplier conflicted with grounded local evidence")
        multiplier = local.formula_multiplier
    for label, proposed, grounded in (
        ("technical weight", technical_weight, local.technical_weight_percent),
        ("financial weight", financial_weight, local.financial_weight_percent),
    ):
        if grounded is not None:
            if proposed is not None and proposed != grounded:
                conflicts.append(f"Gemini {label} conflicted with grounded local evidence")
            if label == "technical weight": technical_weight = grounded
            else: financial_weight = grounded
    if local.money_value is not None:
        if money_value is not None and money_value != local.money_value:
            conflicts.append("Gemini money value conflicted with grounded local evidence")
        if currency and local.currency and currency != local.currency:
            conflicts.append("Gemini currency conflicted with grounded local evidence")
        money_value, currency = local.money_value, local.currency
    evidence_review = any(item.requires_review for item in items)
    reasons = ([response.review_reason] if response.review_reason else []) + conflicts
    if evidence_review: reasons.append("Grounded local evidence requires review")
    identity = "|".join([response.kind.value, response.title.casefold(), formula_expression or "", str(technical_weight), str(financial_weight), str(money_value), *sorted(record.evidence_id for record in records)])
    return GroundedCommercialFinancialRule(
        rule_id=f"CFR-{hashlib.sha256(identity.encode()).hexdigest()[:20]}", kind=response.kind,
        title=response.title, description=response.description, mandatory=response.mandatory,
        formula_expression=formula_expression, formula_variables=variables, formula_semantics=semantics,
        formula_multiplier=float(multiplier) if multiplier is not None else None,
        technical_weight_percent=float(technical_weight) if technical_weight is not None else None,
        financial_weight_percent=float(financial_weight) if financial_weight is not None else None,
        percentage_value=response.percentage_value, money_value=format(money_value, "f") if money_value is not None else response.money_value,
        currency=currency, operator=response.operator, unit=response.unit, expected_evidence=response.expected_evidence,
        evidence_handles=[record.handle for record in records], evidence_ids=[record.evidence_id for record in records],
        source_pages=sorted({page for item in items for page in item.source_pages}),
        source_section_ids=sorted({value for item in items for value in item.source_section_ids}),
        source_work_unit_ids=sorted({value for item in items for value in item.source_work_unit_ids}),
        candidate_ids=sorted({value for item in items for value in item.candidate_ids}),
        source_references=_unique_sources(items),
        source_categories=sorted({value for item in items for value in item.categories}, key=lambda value: value.value),
        requires_review=response.requires_review or evidence_review or bool(conflicts),
        review_reason="; ".join(dict.fromkeys(reasons)) or None,
    )


def _deduplicate(rules):
    result = {}
    for rule in rules:
        key = (rule.kind, rule.formula_expression, rule.title.casefold(), rule.money_value, rule.percentage_value)
        existing = result.get(key)
        if existing is None: result[key] = rule; continue
        result[key] = existing.model_copy(update={
            "evidence_handles": sorted(set(existing.evidence_handles + rule.evidence_handles)),
            "evidence_ids": sorted(set(existing.evidence_ids + rule.evidence_ids)),
            "source_pages": sorted(set(existing.source_pages + rule.source_pages)),
            "source_section_ids": sorted(set(existing.source_section_ids + rule.source_section_ids)),
            "source_work_unit_ids": sorted(set(existing.source_work_unit_ids + rule.source_work_unit_ids)),
            "candidate_ids": sorted(set(existing.candidate_ids + rule.candidate_ids)),
            "source_references": existing.source_references + [source for source in rule.source_references if source not in existing.source_references],
            "requires_review": existing.requires_review or rule.requires_review,
            "review_reason": existing.review_reason or rule.review_reason,
        })
    return list(result.values())


class CommercialFinancialBlueprintService:
    def __init__(self, provider: CommercialFinancialResponseProvider, clock: Callable[[], float] = time.perf_counter) -> None:
        self._provider = provider; self._clock = clock

    def execute(self, plan: BlueprintEvidencePlan) -> CommercialFinancialExecutionResult:
        request = select_commercial_financial_request(plan); started = self._clock()
        try: payload, metadata = self._provider.generate(serialize_commercial_financial_request(request))
        except CommercialFinancialSmokeTestError: raise
        except Exception as error: raise CommercialFinancialSmokeTestError("Commercial-financial provider failed", 1) from error
        latency_ms = (self._clock() - started) * 1000; parsed = parse_commercial_financial_response(payload)
        known = {record.handle for record in request.records}
        unsupported = sum(handle not in known for rule in parsed.rules for handle in rule.evidence_ids)
        index = _item_index(plan)
        restored = [item for response in parsed.rules if (item := _restore(response, request, index)) is not None]
        accepted = _deduplicate(restored)
        return CommercialFinancialExecutionResult(
            rules=accepted, generated_count=len(parsed.rules), accepted_count=len(accepted),
            review_required_count=sum(item.requires_review for item in accepted), rejected_count=len(parsed.rules) - len(restored),
            unsupported_evidence_handle_count=unsupported,
            usage=CommercialFinancialUsage(
                model=self._provider.model, request_id=str(metadata.get("provider_request_id") or request.request_id),
                evidence_record_count=len(request.records), input_characters=request.character_count,
                input_tokens=metadata.get("input_tokens") if isinstance(metadata.get("input_tokens"), int) else None,
                output_tokens=metadata.get("output_tokens") if isinstance(metadata.get("output_tokens"), int) else None,
                total_tokens=metadata.get("total_tokens") if isinstance(metadata.get("total_tokens"), int) else None,
                latency_ms=latency_ms, request_count=1, retry_count=0, success=True,
            ),
        )
