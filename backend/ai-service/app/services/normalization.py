import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.models.blueprint import ComparisonOperator, NormalizedRequirement

_OPERATOR_PATTERNS = (
    (r"\b(?:shall\s+not\s+exceed|not\s+exceed|no\s+more\s+than|at\s+most|maximum(?:\s+of)?|not\s+more\s+than|up\s+to)\b", ComparisonOperator.LTE),
    (r"\b(?:shall\s+not\s+(?:be\s+)?less\s+than|not\s+(?:be\s+)?less\s+than|at\s+least|minimum(?:\s+of)?)\b", ComparisonOperator.GTE),
    (r"\b(?:greater\s+than|more\s+than|above)\b", ComparisonOperator.GT),
    (r"\b(?:less\s+than|below)\b", ComparisonOperator.LT),
    (r"\b(?:exactly|equal\s+to)\b", ComparisonOperator.EQ),
)
_AMOUNT_PATTERN = re.compile(r"(?:₹|\bINR\b|\bRs\.?)(?:\s*)([\d,]+(?:\.\d+)?)\s*(lakh|lakhs|crore|crores)?", re.IGNORECASE)
_PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b|percentage\b)", re.IGNORECASE)
_DURATION_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(day|days|week|weeks|month|months|year|years)\b", re.IGNORECASE)


def normalize_operator(text: str) -> ComparisonOperator | None:
    lowered = text.casefold()
    for pattern, operator in _OPERATOR_PATTERNS:
        if re.search(pattern, lowered):
            return operator
    return None


def _decimal_string(value: Decimal) -> str:
    return format(value.normalize(), "f")


def normalize_requirement_value(text: str) -> NormalizedRequirement:
    operator = normalize_operator(text)
    amount = _AMOUNT_PATTERN.search(text)
    if amount:
        try:
            value = Decimal(amount.group(1).replace(",", ""))
        except InvalidOperation:
            return NormalizedRequirement(operator=operator)
        magnitude = (amount.group(2) or "").casefold()
        if magnitude.startswith("lakh"):
            value *= Decimal(100000)
        elif magnitude.startswith("crore"):
            value *= Decimal(10000000)
        return NormalizedRequirement(value=_decimal_string(value), operator=operator, currency="INR")

    percentage = _PERCENT_PATTERN.search(text)
    if percentage:
        return NormalizedRequirement(value=_decimal_string(Decimal(percentage.group(1))), operator=operator, unit="percent")

    duration = _DURATION_PATTERN.search(text)
    if duration:
        return NormalizedRequirement(
            value=_decimal_string(Decimal(duration.group(1))),
            operator=operator,
            unit=duration.group(2).lower().rstrip("s"),
            period=duration.group(0),
        )

    date_value = _normalize_date(text)
    if date_value:
        return NormalizedRequirement(value=date_value, operator=operator, unit="date")

    lowered = text.casefold()
    if any(term in lowered for term in ("must", "shall", "is required", "mandatory")):
        return NormalizedRequirement(value=True)
    return NormalizedRequirement(operator=operator)


def _normalize_date(text: str) -> str | None:
    match = re.search(r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{1,2}[- ][A-Za-z]{3,9}[- ]\d{4})\b", text)
    if not match:
        return None
    candidate = match.group(1)
    for date_format in ("%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y"):
        try:
            return datetime.strptime(candidate, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_text(text: str) -> str:
    return " ".join(text.split())
