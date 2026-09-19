import hashlib
import re
import statistics
from collections import defaultdict
from collections.abc import Callable
from difflib import SequenceMatcher

from app.models.blueprint import RequirementCategory, SourceReference
from app.models.blueprint_evidence import (
    BlueprintEvidenceItem,
    BlueprintEvidencePackage,
    BlueprintEvidencePlan,
    BlueprintPurpose,
    BlueprintSemanticRequest,
    CompactEvidenceRecord,
    EvidenceOrigin,
    EvidencePackagingMetrics,
    GeminiFacingMetrics,
    LocalEvidenceHint,
    SemanticRequestCategory,
)
from app.models.document_intelligence import LocalCandidate, ResolutionCapability
from app.models.hybrid_blueprint import GeminiWorkUnit, LocalBlueprintDraft, WorkUnitReason
from app.services.normalization import normalize_text

DEFAULT_PACKAGE_MAX_CHARACTERS = 24_000
DEFAULT_REQUEST_MAX_CHARACTERS = 80_000
PACKAGER_VERSION = "evidence-v1"

_EVALUATION = re.compile(
    r"\b(score|marks?|weight(?:age)?|qualifying|threshold|formula|lowest bid|combined score|consolidated score)\b",
    re.IGNORECASE,
)
_ELIGIBILITY = re.compile(
    r"\b(eligibility|qualification|turnover|profitability|blacklist|years? of (?:operation|experience)|nasscom|certification|membership)\b",
    re.IGNORECASE,
)
_SECURITY = re.compile(r"\b(information security|data security|cyber security|iso\s*27001|security undertaking)\b", re.IGNORECASE)
_SOLUTION_TECHNICAL_CONTROL = re.compile(
    r"\b(?:solution|system|platform|application|architecture)\b.{0,100}"
    r"\b(?:implement|support|provide|maintain|enforce|security controls?|technical controls?|capabilit(?:y|ies))\b",
    re.IGNORECASE,
)
_DOCUMENT = re.compile(
    r"\b(submit|provide|attach|enclose|furnish|supporting documents?|documentary evidence|certificate|undertaking|declaration|proof)\b",
    re.IGNORECASE,
)
_SCOPE = re.compile(r"\b(scope of work|deliverables?|implementation scope|services to be provided)\b", re.IGNORECASE)
_OBLIGATION = re.compile(
    r"\b(bidder|vendor|tenderer|supplier|must|shall|should|required|mandatory|minimum|maximum|at least|not less than|not exceed)\b",
    re.IGNORECASE,
)
_CONFIDENT_METADATA = re.compile(
    r"\b(request for proposal|rfp reference|issued by|registered office|corporate office|postal address|table of contents|background)\b",
    re.IGNORECASE,
)
_COPYRIGHT_BOILERPLATE = re.compile(r"\b(copyright|intellectual property|right or licen[cs]e)\b", re.IGNORECASE)
_RESIDUAL_SIGNAL = re.compile(
    r"\b(bidder|vendor|tenderer|supplier|shall|must|should|required|mandatory|minimum|maximum|at least|"
    r"not less than|not exceed|turnover|profitability|experience|blacklist|certif(?:ied|icate|ication)|"
    r"membership|undertaking|declaration|supporting documents?|documentary evidence|information security|"
    r"data security|technical|score|marks?|threshold|formula|lowest bid|bid value|inr|crores?|financial years?|commercial|contract|"
    r"liquidated damages|payment terms?)\b",
    re.IGNORECASE,
)
_TABLE_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
_TABLE_DESCRIPTION_START = re.compile(
    r"^(?:evaluation\b|capability\b|presentation of proposal to\b|the bidder\b|bidder\b)",
    re.IGNORECASE,
)


def _normalized_evidence(text: str) -> str:
    normalized = normalize_text(text).casefold()
    normalized = re.sub(r"^\s*(?:row\s*)?(?:\d+(?:\.\d+)*|[a-z])[.)-]?\s+", "", normalized)
    return re.sub(r"[^a-z0-9%₹]+", " ", normalized).strip()


def _purpose(text: str, categories: set[RequirementCategory]) -> BlueprintPurpose:
    if RequirementCategory.TECHNICAL in categories and _SOLUTION_TECHNICAL_CONTROL.search(text):
        return BlueprintPurpose.TECHNICAL_REQUIREMENTS
    if _SECURITY.search(text) or RequirementCategory.SECURITY in categories:
        return BlueprintPurpose.SECURITY
    if _EVALUATION.search(text):
        if RequirementCategory.FINANCIAL in categories or re.search(r"\b(financial|commercial|price|bid value)\b", text, re.IGNORECASE):
            return BlueprintPurpose.FINANCIAL_COMMERCIAL_EVALUATION
        return BlueprintPurpose.TECHNICAL_EVALUATION
    if _ELIGIBILITY.search(text) or RequirementCategory.ELIGIBILITY in categories:
        return BlueprintPurpose.ELIGIBILITY
    if RequirementCategory.DOCUMENT in categories or _DOCUMENT.search(text):
        return BlueprintPurpose.REQUIRED_DOCUMENTS
    if RequirementCategory.TECHNICAL in categories:
        return BlueprintPurpose.TECHNICAL_REQUIREMENTS
    if RequirementCategory.FINANCIAL in categories or RequirementCategory.COMMERCIAL in categories:
        return BlueprintPurpose.COMMERCIAL
    if RequirementCategory.CONTRACTUAL in categories:
        return BlueprintPurpose.CONTRACTUAL
    if _SCOPE.search(text):
        return BlueprintPurpose.SCOPE
    return BlueprintPurpose.OTHER_PROCUREMENT


def _source_key(source: SourceReference) -> tuple[int, str, str, str]:
    return source.page_number, source.section or "", source.clause or "", normalize_text(source.excerpt).casefold()


def _unique_sources(sources: list[SourceReference]) -> list[SourceReference]:
    unique = {_source_key(source): source for source in sources}
    return [unique[key] for key in sorted(unique)]


def _hint(candidate: LocalCandidate) -> LocalEvidenceHint:
    return LocalEvidenceHint(
        candidate_id=candidate.candidate_id,
        candidate_type=candidate.candidate_type,
        category=candidate.category,
        resolution_capability=candidate.resolution_capability,
        normalized=candidate.normalized,
        mandatory_signal=candidate.mandatory_signal,
        confidence=candidate.confidence,
        ambiguity_reason=candidate.ambiguity_reason,
    )


def _candidate_item(candidate: LocalCandidate, unit: GeminiWorkUnit) -> BlueprintEvidenceItem:
    sources = [evidence.source_reference for evidence in candidate.evidence]
    section_ids = sorted({evidence.section_id for evidence in candidate.evidence})
    categories = {candidate.category}
    purpose = _purpose(candidate.raw_text, categories)
    fingerprint = _normalized_evidence(candidate.raw_text)
    evidence_id = f"EVI-{hashlib.sha256(f'{PACKAGER_VERSION}|{purpose.value}|{fingerprint}'.encode()).hexdigest()[:20]}"
    return BlueprintEvidenceItem(
        evidence_id=evidence_id,
        origin=EvidenceOrigin.CANDIDATE,
        purpose=purpose,
        categories=sorted(categories, key=lambda category: category.value),
        text=candidate.raw_text,
        source_pages=sorted({source.page_number for source in sources}),
        source_section_ids=section_ids,
        source_work_unit_ids=[unit.work_unit_id],
        candidate_ids=[candidate.candidate_id],
        source_references=_unique_sources(sources),
        local_hints=[_hint(candidate)],
        requires_review=candidate.resolution_capability == ResolutionCapability.REVIEW_REQUIRED,
    )


def _residual_regions(text: str, candidate_texts: list[str]) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    normalized_candidates = [_normalized_evidence(value) for value in candidate_texts]
    unmatched_indexes: list[int] = []
    for index, line in enumerate(lines):
        normalized_line = _normalized_evidence(line)
        directly_represented = any(
            normalized_line == candidate or normalized_line in candidate
            for candidate in normalized_candidates
            if candidate
        )
        residual_normalized = normalized_line
        for candidate in normalized_candidates:
            if candidate:
                residual_normalized = residual_normalized.replace(candidate, " ")
        represented = directly_represented or _RESIDUAL_SIGNAL.search(residual_normalized) is None
        if _RESIDUAL_SIGNAL.search(line) and not represented and not _heading_only(line):
            unmatched_indexes.append(index)
    if not unmatched_indexes:
        return []
    windows = [(max(0, index - 1), min(len(lines) - 1, index + 1)) for index in unmatched_indexes]
    merged: list[tuple[int, int]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return ["\n".join(lines[start : end + 1]) for start, end in merged]


def _context_item(unit: GeminiWorkUnit, context, text: str | None = None, residual_index: int = 0) -> BlueprintEvidenceItem:
    section_candidates = [
        candidate
        for candidate in unit.candidates
        if any(evidence.section_id == context.section_id for evidence in candidate.evidence)
    ]
    categories = {candidate.category for candidate in section_candidates} or {RequirementCategory.OTHER}
    evidence_text = text or context.text
    purpose = _purpose(evidence_text, categories)
    fingerprint = _normalized_evidence(evidence_text)
    identity = f"{PACKAGER_VERSION}|{purpose.value}|{unit.work_unit_id}|{context.section_id}|{residual_index}|{fingerprint}"
    evidence_id = f"EVI-{hashlib.sha256(identity.encode()).hexdigest()[:20]}"
    source = SourceReference(page_number=context.page_number, section=context.heading, excerpt=normalize_text(evidence_text)[:600])
    return BlueprintEvidenceItem(
        evidence_id=evidence_id,
        origin=EvidenceOrigin.RESIDUAL_CONTEXT,
        purpose=purpose,
        categories=sorted(categories, key=lambda category: category.value),
        text=evidence_text,
        source_pages=[context.page_number],
        source_section_ids=[context.section_id],
        source_work_unit_ids=[unit.work_unit_id],
        source_references=[source],
        requires_review=any(
            candidate.resolution_capability == ResolutionCapability.REVIEW_REQUIRED
            for candidate in section_candidates
        ),
    )


def _technical_score_table_items(unit: GeminiWorkUnit) -> list[BlueprintEvidenceItem]:
    if not any(candidate.category == RequirementCategory.TECHNICAL for candidate in unit.candidates):
        return []
    lines = [line.strip() for context in unit.context for line in context.text.splitlines() if line.strip()]
    lowered = [line.casefold() for line in lines]
    maximum_index = next((index for index, line in enumerate(lowered) if line in {"maximum", "maximum marks"}), None)
    minimum_index = next((index for index, line in enumerate(lowered) if line in {"minimum", "minimum passing marks", "minimum marks"}), None)
    if maximum_index is None or minimum_index is None or abs(maximum_index - minimum_index) > 5:
        return []
    start = next((index for index in range(max(maximum_index, minimum_index) + 1, len(lines)) if lines[index] == "1"), None)
    if start is None:
        return []

    rows: list[tuple[str, str, str, str]] = []
    row_start = start
    serial = 1
    while row_start < len(lines):
        next_start = next(
            (
                index for index in range(row_start + 3, len(lines))
                if lines[index] == str(serial + 1)
                and index + 1 < len(lines)
                and not _TABLE_NUMBER.fullmatch(lines[index + 1])
                and _TABLE_NUMBER.fullmatch(lines[index - 1])
            ),
            None,
        )
        segment = lines[row_start + 1 : next_start] if next_start is not None else lines[row_start + 1 :]
        if len(segment) < 3 or not _TABLE_NUMBER.fullmatch(segment[-1]) or not _TABLE_NUMBER.fullmatch(segment[-2]):
            if next_start is None:
                break
            row_start = next_start
            serial += 1
            continue
        body = segment[:-2]
        description_start = next(
            (index for index, line in enumerate(body[1:], start=1) if _TABLE_DESCRIPTION_START.search(line)),
            len(body),
        )
        title = " ".join(body[:description_start]).strip()
        if not title:
            break
        description = " ".join(body[description_start:]).strip()
        rows.append((title, description, segment[-2], segment[-1]))
        if next_start is None:
            break
        row_start = next_start
        serial += 1

    if len(rows) < 2:
        return []
    anchor = unit.context[-1]
    section_ids = sorted({context.section_id for context in unit.context})
    page_numbers = sorted({context.page_number for context in unit.context})
    items: list[BlueprintEvidenceItem] = []
    for index, (title, description, maximum, minimum) in enumerate(rows, start=1):
        text = (
            f"[TECHNICAL SCORE ROW]\nCriterion: {title}\n"
            f"Description: {description}\nMaximum Marks: {maximum}\nMinimum Qualifying Marks: {minimum}"
        )
        item = _context_item(unit, anchor, text, 10_000 + index)
        items.append(item.model_copy(update={
            "purpose": BlueprintPurpose.TECHNICAL_EVALUATION,
            "categories": [RequirementCategory.TECHNICAL],
            "source_pages": page_numbers,
            "source_section_ids": section_ids,
        }))
    return items


def _confidently_irrelevant(item: BlueprintEvidenceItem) -> bool:
    if item.candidate_ids or item.requires_review:
        return False
    return _confidently_irrelevant_context(item.text)


def _confidently_irrelevant_context(text: str) -> bool:
    procurement_signal = _OBLIGATION.search(text) or _EVALUATION.search(text) or _DOCUMENT.search(text) or _SECURITY.search(text)
    if procurement_signal:
        return False
    metadata = _CONFIDENT_METADATA.search(text) is not None
    boilerplate = _COPYRIGHT_BOILERPLATE.search(text) is not None
    return metadata or boilerplate


def _heading_only(text: str) -> bool:
    stripped = text.strip()
    letters = [character for character in stripped if character.isalpha()]
    return bool(letters) and stripped.isupper() and len(stripped.split()) <= 12


def _mergeable(first: BlueprintEvidenceItem, second: BlueprintEvidenceItem) -> bool:
    if first.purpose != second.purpose or set(first.categories) != set(second.categories):
        return False
    left = _normalized_evidence(first.text)
    right = _normalized_evidence(second.text)
    if left == right:
        return True
    if not left or not right or min(len(left), len(right)) / max(len(left), len(right)) < 0.97:
        return False
    return SequenceMatcher(None, left, right, autojunk=False).ratio() >= 0.985


def _merge_items(first: BlueprintEvidenceItem, second: BlueprintEvidenceItem) -> BlueprintEvidenceItem:
    text = first.text if len(first.text) >= len(second.text) else second.text
    return first.model_copy(
        update={
            "text": text,
            "source_pages": sorted(set(first.source_pages + second.source_pages)),
            "source_section_ids": sorted(set(first.source_section_ids + second.source_section_ids)),
            "source_work_unit_ids": sorted(set(first.source_work_unit_ids + second.source_work_unit_ids)),
            "candidate_ids": sorted(set(first.candidate_ids + second.candidate_ids)),
            "source_references": _unique_sources(first.source_references + second.source_references),
            "local_hints": list({hint.candidate_id: hint for hint in first.local_hints + second.local_hints}.values()),
            "requires_review": first.requires_review or second.requires_review,
        }
    )


def _render_item(item: BlueprintEvidenceItem) -> str:
    pages = ",".join(map(str, item.source_pages))
    hint_lines = []
    for hint in item.local_hints:
        operator = hint.normalized.operator.value if hint.normalized.operator else None
        hint_lines.append(
            f"hint candidate={hint.candidate_id} type={hint.candidate_type.value} category={hint.category.value} "
            f"route={hint.resolution_capability.value} value={hint.normalized.value} operator={operator} "
            f"mandatory={hint.mandatory_signal}"
        )
    review = " review_required=true" if item.requires_review else ""
    hints = "\n" + "\n".join(hint_lines) if hint_lines else ""
    return f"[EVIDENCE {item.evidence_id}] pages={pages}{review}\n{item.text}{hints}"


def matching_evidence_pages(
    packages: list[BlueprintEvidencePackage], matcher: Callable[[str], bool]
) -> list[int]:
    return sorted(
        {
            page
            for package in packages
            for item in package.evidence_items
            if matcher(item.text)
            for page in item.source_pages
        }
    )


def _request_category(purpose: BlueprintPurpose) -> SemanticRequestCategory:
    if purpose in {
        BlueprintPurpose.ELIGIBILITY,
        BlueprintPurpose.REQUIRED_DOCUMENTS,
        BlueprintPurpose.SECURITY,
    }:
        return SemanticRequestCategory.QUALIFICATION
    if purpose in {
        BlueprintPurpose.SCOPE,
        BlueprintPurpose.TECHNICAL_REQUIREMENTS,
        BlueprintPurpose.TECHNICAL_EVALUATION,
    }:
        return SemanticRequestCategory.TECHNICAL
    if purpose in {
        BlueprintPurpose.FINANCIAL_COMMERCIAL_EVALUATION,
        BlueprintPurpose.COMMERCIAL,
    }:
        return SemanticRequestCategory.COMMERCIAL_FINANCIAL
    return SemanticRequestCategory.CONTRACTUAL_OTHER


def _semantic_hints(item: BlueprintEvidenceItem) -> list[str]:
    hints: list[str] = []
    for hint in item.local_hints:
        normalized = hint.normalized
        if normalized.value not in (None, True, False):
            parts = [f"value={normalized.value}"]
            if normalized.operator:
                parts.append(f"operator={normalized.operator.value}")
            if normalized.currency:
                parts.append(f"currency={normalized.currency}")
            if normalized.unit:
                parts.append(f"unit={normalized.unit}")
            rendered = " ".join(parts)
            if rendered not in hints:
                hints.append(rendered)
    return hints


def _compact_record(handle: str, item: BlueprintEvidenceItem) -> CompactEvidenceRecord:
    return CompactEvidenceRecord(
        handle=handle,
        evidence_id=item.evidence_id,
        source_pages=item.source_pages,
        text=item.text,
        requires_review=item.requires_review,
        semantic_hints=_semantic_hints(item),
    )


def _render_record(record: CompactEvidenceRecord) -> str:
    pages = ",".join(map(str, record.source_pages))
    flags = ["review"] if record.requires_review else []
    flags.extend(record.semantic_hints)
    suffix = f" | {'; '.join(flags)}" if flags else ""
    return f"[{record.handle} | p{pages}{suffix}]\n{record.text}"


def _build_semantic_request(
    category: SemanticRequestCategory, records: list[CompactEvidenceRecord]
) -> BlueprintSemanticRequest:
    compact_context = "\n\n".join(_render_record(record) for record in records)
    identity = "|".join([PACKAGER_VERSION, category.value] + [record.evidence_id for record in records])
    return BlueprintSemanticRequest(
        request_id=f"BSR-{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
        category=category,
        records=records,
        compact_context=compact_context,
        character_count=len(compact_context),
    )


def _build_semantic_requests(
    items: list[BlueprintEvidenceItem], max_request_characters: int
) -> list[BlueprintSemanticRequest]:
    ordered = sorted(items, key=lambda item: (item.purpose.value, item.source_pages, item.evidence_id))
    records_by_category: dict[SemanticRequestCategory, list[CompactEvidenceRecord]] = defaultdict(list)
    for index, item in enumerate(ordered, start=1):
        records_by_category[_request_category(item.purpose)].append(_compact_record(f"E{index:04d}", item))

    requests: list[BlueprintSemanticRequest] = []
    for category in SemanticRequestCategory:
        records = records_by_category.get(category, [])
        batch: list[CompactEvidenceRecord] = []
        for record in records:
            trial = _build_semantic_request(category, [*batch, record])
            if batch and trial.character_count > max_request_characters:
                requests.append(_build_semantic_request(category, batch))
                batch = [record]
            else:
                batch.append(record)
        if batch:
            requests.append(_build_semantic_request(category, batch))
    return requests


def _build_package(purpose: BlueprintPurpose, items: list[BlueprintEvidenceItem]) -> BlueprintEvidencePackage:
    context = "\n\n".join(_render_item(item) for item in items)
    identity = "|".join(
        [PACKAGER_VERSION, purpose.value]
        + [item.evidence_id for item in items]
        + sorted({work_unit_id for item in items for work_unit_id in item.source_work_unit_ids})
    )
    package_id = f"BEP-{hashlib.sha256(identity.encode()).hexdigest()[:20]}"
    return BlueprintEvidencePackage(
        package_id=package_id,
        primary_purpose=purpose,
        categories=sorted({category for item in items for category in item.categories}, key=lambda category: category.value),
        source_pages=sorted({page for item in items for page in item.source_pages}),
        source_section_ids=sorted({section_id for item in items for section_id in item.source_section_ids}),
        source_work_unit_ids=sorted({work_unit_id for item in items for work_unit_id in item.source_work_unit_ids}),
        candidate_ids=sorted({candidate_id for item in items for candidate_id in item.candidate_ids}),
        evidence_items=items,
        review_flags=[item.evidence_id for item in items if item.requires_review],
        context=context,
        character_count=len(context),
    )


class BlueprintEvidencePackager:
    def __init__(
        self,
        max_package_characters: int = DEFAULT_PACKAGE_MAX_CHARACTERS,
        max_request_characters: int = DEFAULT_REQUEST_MAX_CHARACTERS,
    ) -> None:
        if max_package_characters <= 0:
            raise ValueError("max_package_characters must be positive")
        if max_request_characters <= 0:
            raise ValueError("max_request_characters must be positive")
        self._max_package_characters = max_package_characters
        self._max_request_characters = max_request_characters

    def package(
        self,
        draft: LocalBlueprintDraft,
        work_units: list[GeminiWorkUnit],
        extracted_document_characters: int,
    ) -> BlueprintEvidencePlan:
        del draft  # Local deterministic evidence remains in the local Blueprint draft, outside Gemini packages.
        raw_items: list[BlueprintEvidenceItem] = []
        prefiltered_irrelevant_contexts = 0
        for unit in work_units:
            raw_items.extend(_candidate_item(candidate, unit) for candidate in unit.candidates)
            raw_items.extend(_technical_score_table_items(unit))
            for context in unit.context:
                section_candidates = [
                    candidate
                    for candidate in unit.candidates
                    if any(evidence.section_id == context.section_id for evidence in candidate.evidence)
                ]
                if unit.reason == WorkUnitReason.COVERAGE_SAFEGUARD or not section_candidates:
                    regions = [context.text] if _RESIDUAL_SIGNAL.search(context.text) else []
                    if not regions and _confidently_irrelevant_context(context.text):
                        prefiltered_irrelevant_contexts += 1
                else:
                    regions = _residual_regions(context.text, [candidate.raw_text for candidate in section_candidates])
                raw_items.extend(
                    _context_item(unit, context, region, index)
                    for index, region in enumerate(regions)
                )

        relevant_items = [item for item in raw_items if not _confidently_irrelevant(item)]
        excluded = len(raw_items) - len(relevant_items) + prefiltered_irrelevant_contexts
        deduplicated: list[BlueprintEvidenceItem] = []
        for item in relevant_items:
            match_index = next((index for index, existing in enumerate(deduplicated) if _mergeable(existing, item)), None)
            if match_index is None:
                deduplicated.append(item)
            else:
                deduplicated[match_index] = _merge_items(deduplicated[match_index], item)

        grouped: dict[BlueprintPurpose, list[BlueprintEvidenceItem]] = defaultdict(list)
        for item in deduplicated:
            grouped[item.purpose].append(item)

        packages: list[BlueprintEvidencePackage] = []
        for purpose in sorted(grouped, key=lambda value: value.value):
            batch: list[BlueprintEvidenceItem] = []
            for item in sorted(grouped[purpose], key=lambda value: (value.source_pages, value.evidence_id)):
                trial = _build_package(purpose, [*batch, item])
                if batch and trial.character_count > self._max_package_characters:
                    packages.append(_build_package(purpose, batch))
                    batch = [item]
                else:
                    batch.append(item)
            if batch:
                packages.append(_build_package(purpose, batch))

        package_sizes = [package.character_count for package in packages]
        package_characters = sum(package_sizes)
        input_characters = sum(unit.context_characters for unit in work_units)
        semantic_requests = _build_semantic_requests(deduplicated, self._max_request_characters)
        request_sizes = [request.character_count for request in semantic_requests]
        metrics = EvidencePackagingMetrics(
            input_work_units=len(work_units),
            input_work_unit_characters=input_characters,
            evidence_items_before_deduplication=len(raw_items),
            evidence_items_after_deduplication=len(deduplicated),
            candidate_derived_evidence=sum(item.origin == EvidenceOrigin.CANDIDATE for item in deduplicated),
            residual_context_evidence=sum(item.origin == EvidenceOrigin.RESIDUAL_CONTEXT for item in deduplicated),
            duplicate_evidence_consolidated=len(relevant_items) - len(deduplicated),
            confidently_irrelevant_exclusions=excluded,
            preserved_uncertain_evidence=sum(item.requires_review for item in deduplicated),
            package_count=len(packages),
            package_characters=package_characters,
            source_pages_represented=len({page for package in packages for page in package.source_pages}),
            source_work_units_represented=len({unit_id for package in packages for unit_id in package.source_work_unit_ids}),
            review_evidence_preserved=sum(item.requires_review for item in deduplicated),
            largest_package_characters=max(package_sizes, default=0),
            median_package_characters=statistics.median(package_sizes) if package_sizes else 0,
            extracted_document_characters=extracted_document_characters,
            package_to_document_ratio=package_characters / extracted_document_characters if extracted_document_characters else 0,
            package_to_work_unit_ratio=package_characters / input_characters if input_characters else 0,
            estimated_future_requests=len(semantic_requests),
        )
        gemini_facing_metrics = GeminiFacingMetrics(
            semantic_categories=list(dict.fromkeys(request.category for request in semantic_requests)),
            future_request_count=len(semantic_requests),
            evidence_records=sum(len(request.records) for request in semantic_requests),
            total_compact_context_characters=sum(request_sizes),
            largest_request_characters=max(request_sizes, default=0),
            median_request_characters=statistics.median(request_sizes) if request_sizes else 0,
            review_records=sum(record.requires_review for request in semantic_requests for record in request.records),
            source_pages_represented=len(
                {page for request in semantic_requests for record in request.records for page in record.source_pages}
            ),
        )
        return BlueprintEvidencePlan(
            packages=packages,
            semantic_requests=semantic_requests,
            metrics=metrics,
            gemini_facing_metrics=gemini_facing_metrics,
        )
