import re
from collections.abc import Iterable

from app.models.blueprint import NormalizedRequirement, RequirementCategory, SourceReference
from app.models.document_intelligence import CandidateEvidence, CandidateType, DocumentSection, LocalCandidate, LocalDocumentAnalysis, ProcessingMetrics, ResolutionCapability
from app.models.extraction import ExtractedDocument, ExtractedPage
from app.services.normalization import normalize_requirement_value, normalize_text

_SIGNALS: dict[RequirementCategory, tuple[str, ...]] = {
    RequirementCategory.ELIGIBILITY: ("eligibility", "pre-qualification", "qualification criteria", "turnover", "profitability", "blacklist"),
    RequirementCategory.TECHNICAL: ("technical", "scope of work", "methodology", "staffing", "quality assurance", "presentation", "relevant experience"),
    RequirementCategory.FINANCIAL: ("financial", "turnover", "financial score", "lowest bid", "bid value", "tender fee", "emd"),
    RequirementCategory.DOCUMENT: ("mandatory document", "supporting document", "documentary evidence", "bid submission", "annexure", "forms"),
    RequirementCategory.COMMERCIAL: ("commercial", "payment term", "price bid", "financial proposal"),
    RequirementCategory.CONTRACTUAL: ("contract", "liquidated damages", "indemnity", "copyright", "intellectual property", "termination"),
    RequirementCategory.SECURITY: ("information security", "data security", "cyber security", "iso 27001", "security undertaking"),
}
_REQUIREMENT = re.compile(r"\b(must|shall|should|required|mandatory|minimum|maximum|at least|not less than|not exceed|provide|submit|furnish|attach|enclose|demonstrate)\b", re.I)
_SUBMISSION = re.compile(r"\b(submit|provide|attach|enclose|furnish|supporting documents?|documentary evidence|copy of|certificate from|bidder shall provide)\b", re.I)
_DOCUMENT = re.compile(r"\b(certificate|audited statements?|registration|undertaking|declaration|proof|authorization|accreditation|membership)\b", re.I)
_IP = re.compile(r"\b(copyright|intellectual property|software licen[cs]e|licen[cs]e rights?|right or licen[cs]e)\b", re.I)
_AMBIGUOUS = re.compile(r"\b(not required|need not|no requirement|not mandatory|shall not be required|except(?:ion)?|unless|subject to|optional|preferably|desirable|preference may be given)\b", re.I)
_HISTORICAL = re.compile(r"\b(previous supplier|previous vendor|historical|was awarded|was completed|maximum contract value was|estimated project (?:cost|value)|estimated contract value|project budget)\b", re.I)
_QUANTITY = re.compile(r"\b(?:at least|minimum(?: of)?|not less than|more than|maximum(?: of)?|not more than|no more than)\s+(\d+)\s+(projects?|assignments?|installations?|clients?|locations?|employees?|professionals?)\b", re.I)
_HEADING = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[A-Z]|[IVXLC]+)[.)]?\s+\S+")
_TOC = re.compile(r"\.{2,}\s*\d+\s*$|\bpage\s+\d+\s*$", re.I)
_EVALUATION = re.compile(r"\b(score|marks?|weight(?:age)?|qualifying score|technical score|financial score|combined score|consolidated score|formula|lowest bid|bid value|percentage weighting)\b", re.I)
_STANDARD = re.compile(r"\bISO\s*[-:]?\s*\d{4,5}(?::\d{4})?\b", re.I)
_SOLUTION_TECHNICAL_CONTROL = re.compile(
    r"\b(?:solution|system|platform|application|architecture)\b.{0,100}"
    r"\b(?:implement|support|provide|maintain|enforce|security controls?|technical controls?|capabilit(?:y|ies))\b",
    re.I,
)
_APPLICABILITY = re.compile(r"\b(bidder|vendor|tenderer|applicant|supplier)\b", re.I)
_SUBSTANTIVE_PROCUREMENT = re.compile(
    r"\b(turnover|profitability|experience|blacklist(?:ed|ing)?|certificate|certification|membership|"
    r"supporting documents?|documentary evidence|score|marks?|threshold|liquidated damages|"
    r"information security|data security)\b",
    re.I,
)


def _category_for(text: str) -> tuple[RequirementCategory, float]:
    lowered = text.casefold()
    scores = {category: sum(lowered.count(term) for term in terms) for category, terms in _SIGNALS.items()}
    if _EVALUATION.search(text):
        scores[RequirementCategory.TECHNICAL] += 2
    if _IP.search(text):
        scores[RequirementCategory.CONTRACTUAL] += 4
    if _STANDARD.search(text):
        scores[RequirementCategory.ELIGIBILITY] += 2
        if "27001" in lowered:
            scores[RequirementCategory.SECURITY] += 2
    if _SOLUTION_TECHNICAL_CONTROL.search(text):
        scores[RequirementCategory.TECHNICAL] += 4
    category, score = max(scores.items(), key=lambda item: item[1])
    return (category, min(0.95, 0.55 + score * 0.1)) if score else (RequirementCategory.OTHER, 0.2)


def _looks_like_heading(line: str) -> bool:
    clean = line.strip()
    if not clean or len(clean) > 100 or clean.endswith((".", ";", "?", "!")):
        return False
    category, confidence = _category_for(clean)
    return len(clean.split()) <= 12 and (clean.isupper() or _HEADING.match(clean) is not None or confidence >= 0.75)


def _has_substantive_procurement_content(text: str) -> bool:
    applicability_rule = _APPLICABILITY.search(text) and (
        _REQUIREMENT.search(text) or _SUBSTANTIVE_PROCUREMENT.search(text) or _STANDARD.search(text)
    )
    evaluation_rule = _EVALUATION.search(text) and re.search(r"\b(criteria|minimum|maximum|qualifying|threshold|formula)\b", text, re.I)
    evidence_rule = _SUBMISSION.search(text) and _DOCUMENT.search(text)
    return bool(applicability_rule or evaluation_rule or evidence_rule)


def _is_toc_region(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 5:
        return False
    short = sum(len(line.split()) <= 12 for line in lines)
    references = sum(bool(_TOC.search(line) or re.search(r"\s\d{1,3}\s*$", line)) for line in lines)
    prose = sum(len(line.split()) >= 18 and line.endswith((".", ";")) for line in lines)
    looks_navigational = references >= 3 and short / len(lines) >= 0.55 and prose / len(lines) < 0.25
    return looks_navigational and not _has_substantive_procurement_content(text)


def _page_sections(page: ExtractedPage, start: int) -> list[DocumentSection]:
    regions: list[tuple[str | None, list[str]]] = []
    heading: str | None = None
    buffer: list[str] = []
    for line in page.text.splitlines():
        navigation_entry = _TOC.search(line) is not None
        if _looks_like_heading(line) and not navigation_entry and buffer and len(" ".join(buffer)) >= 60:
            regions.append((heading, buffer))
            heading, buffer = line.strip(), [line]
        else:
            if _looks_like_heading(line) and heading is None:
                heading = line.strip()
            buffer.append(line)
    if buffer:
        regions.append((heading, buffer))
    sections: list[DocumentSection] = []
    for region_heading, lines in regions:
        text = "\n".join(lines).strip()
        if text:
            category, confidence = _category_for(f"{region_heading or ''}\n{text}")
            sections.append(DocumentSection(section_id=f"SECTION-{start + len(sections):04d}", heading=region_heading, text=text, page_numbers=[page.page_number], category=category, relevance_confidence=confidence, is_table_of_contents=_is_toc_region(text)))
    return sections


def detect_sections(pages: list[ExtractedPage]) -> list[DocumentSection]:
    sections: list[DocumentSection] = []
    for page in pages:
        sections.extend(_page_sections(page, len(sections) + 1))
    return sections


def _sentences(text: str) -> Iterable[str]:
    for line in text.splitlines():
        for sentence in re.split(r"(?<=[;!?])\s+|(?<=\.)\s+(?=[A-Z])", line.strip()):
            if cleaned := normalize_text(sentence):
                yield cleaned


def _normalize(text: str) -> NormalizedRequirement:
    normalized = normalize_requirement_value(text)
    if normalized.value not in (None, True):
        return normalized
    if match := _QUANTITY.search(text):
        parsed = normalize_requirement_value(match.group(0))
        return NormalizedRequirement(value=match.group(1), operator=parsed.operator, unit=match.group(2).lower().rstrip("s"))
    return normalized


def _is_document(text: str, section: DocumentSection) -> bool:
    if _IP.search(text) and not _SUBMISSION.search(text):
        return False
    strong_context = section.category in {RequirementCategory.DOCUMENT, RequirementCategory.ELIGIBILITY} and section.relevance_confidence >= 0.75
    return _DOCUMENT.search(text) is not None and (_SUBMISSION.search(text) is not None or (strong_context and _REQUIREMENT.search(text) is not None))


def _candidate_type(text: str, normalized: NormalizedRequirement, document: bool) -> CandidateType:
    if document:
        return CandidateType.DOCUMENT_EVIDENCE
    if normalized.currency:
        return CandidateType.MONEY
    if normalized.unit == "percent":
        return CandidateType.PERCENTAGE
    if normalized.unit == "date":
        return CandidateType.DATE
    if normalized.period:
        return CandidateType.DURATION
    if _QUANTITY.search(text):
        return CandidateType.QUANTITATIVE
    if normalized.value is True:
        return CandidateType.MANDATORY_SIGNAL
    return CandidateType.SEMANTIC


def _route(text: str, normalized: NormalizedRequirement, requirement: bool, document: bool, category: RequirementCategory) -> tuple[ResolutionCapability, float, bool, str | None, bool | None]:
    mandatory = True if re.search(r"\b(must|shall|required|mandatory)\b", text, re.I) else None
    if _AMBIGUOUS.search(text) or _HISTORICAL.search(text):
        non_mandatory = re.search(
            r"\b(not required|need not|not mandatory|optional|preferably|desirable|preference may be given)\b",
            text,
            re.I,
        )
        return ResolutionCapability.REVIEW_REQUIRED, 0.5, True, "Exception, optionality, negation, or descriptive context requires human review", False if non_mandatory else None
    structured = normalized.value not in (None, True)
    complete = not structured or normalized.operator is not None
    bidder = re.search(r"\b(bidder|vendor|tenderer|applicant|supplier)\b", text, re.I) is not None
    if requirement and mandatory is True and complete and (document or (structured and bidder)) and category != RequirementCategory.OTHER:
        return ResolutionCapability.LOCAL_DETERMINISTIC, 0.9, False, None, mandatory
    reason = "Structured value lacks an unambiguous comparison operator" if structured and not complete else "Semantic interpretation is required"
    return ResolutionCapability.LLM_REQUIRED, 0.65, True, reason, mandatory


def extract_local_candidates(sections: list[DocumentSection]) -> list[LocalCandidate]:
    candidates: list[LocalCandidate] = []
    for section in sections:
        if section.is_table_of_contents:
            continue
        for sentence in _sentences(section.text):
            if section.heading and normalize_text(sentence).casefold() == normalize_text(section.heading).casefold():
                continue
            requirement = _REQUIREMENT.search(sentence) is not None
            document = _is_document(sentence, section)
            normalized = _normalize(sentence)
            if not (requirement or document or normalized.value is not None or _AMBIGUOUS.search(sentence) or _STANDARD.search(sentence) or _EVALUATION.search(sentence)):
                continue
            candidate_type = _candidate_type(sentence, normalized, document)
            category, _ = _category_for(f"{section.heading or ''}\n{sentence}")
            if document and category == RequirementCategory.OTHER:
                category = RequirementCategory.DOCUMENT
            if normalized.currency and category == RequirementCategory.OTHER:
                category = RequirementCategory.FINANCIAL
            capability, confidence, ambiguous, reason, mandatory = _route(sentence, normalized, requirement, document, category)
            candidates.append(LocalCandidate(candidate_id=f"LOCAL-{len(candidates) + 1:04d}", candidate_type=candidate_type, category=category, raw_text=sentence, normalized=normalized, mandatory_signal=mandatory, evidence=[CandidateEvidence(source_reference=SourceReference(page_number=section.page_numbers[0], section=section.heading, excerpt=sentence[:600]), section_id=section.section_id)], confidence=confidence, ambiguous=ambiguous, ambiguity_reason=reason, resolution_capability=capability))
    return candidates


def _metrics(document: ExtractedDocument, sections: list[DocumentSection], candidates: list[LocalCandidate]) -> ProcessingMetrics:
    relevant = {e.section_id for c in candidates for e in c.evidence} | {s.section_id for s in sections if s.category != RequirementCategory.OTHER and not s.is_table_of_contents}
    llm = {e.section_id for c in candidates if c.resolution_capability != ResolutionCapability.LOCAL_DETERMINISTIC for e in c.evidence}
    lengths = {s.section_id: len(s.text) for s in sections}
    return ProcessingMetrics(total_pages=document.page_count, total_extracted_characters=document.total_characters, detected_sections=len(sections), total_candidates=len(candidates), locally_deterministic_candidates=sum(c.resolution_capability == ResolutionCapability.LOCAL_DETERMINISTIC for c in candidates), llm_required_candidates=sum(c.resolution_capability == ResolutionCapability.LLM_REQUIRED for c in candidates), review_required_candidates=sum(c.resolution_capability == ResolutionCapability.REVIEW_REQUIRED for c in candidates), relevant_source_characters=sum(lengths[i] for i in relevant), potential_llm_context_characters=sum(lengths[i] for i in llm))


class LocalDocumentIntelligenceService:
    def analyze(self, document: ExtractedDocument) -> LocalDocumentAnalysis:
        sections = detect_sections(document.pages)
        candidates = extract_local_candidates(sections)
        return LocalDocumentAnalysis(source_filename=document.filename, source_sha256=document.sha256, pages=document.pages, sections=sections, candidates=candidates, metrics=_metrics(document, sections, candidates))
