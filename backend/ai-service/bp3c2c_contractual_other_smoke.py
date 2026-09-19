import json
import os
from pathlib import Path

from app.models.blueprint_evidence import SemanticRequestCategory
from app.services.contractual_other_blueprint import (
    ContractualOtherBlueprintService, GoogleContractualOtherProvider, select_contractual_other_requests,
)
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.evidence_packager import BlueprintEvidencePackager
from app.services.hybrid_blueprint import build_local_draft, create_work_units
from app.services.pdf_extractor import extract_pdf


def _load_runtime_configuration(path: Path) -> None:
    if not path.is_file(): return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        name, value = line.split("=", 1); name = name.strip()
        if name not in {"GEMINI_API_KEY", "GEMINI_MODEL"}: continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}: value = value[1:-1]
        os.environ.setdefault(name, value)


def main() -> None:
    root = Path(__file__).resolve().parent
    _load_runtime_configuration(root / ".env")
    from app.config import settings
    tender = root.parents[1] / "demo-data" / "IT Software RPF.pdf"
    document = extract_pdf(tender.read_bytes(), tender.name)
    analysis = LocalDocumentIntelligenceService().analyze(document)
    draft = build_local_draft(analysis)
    plan = BlueprintEvidencePackager().package(draft, create_work_units(draft), document.total_characters)
    requests = select_contractual_other_requests(plan)
    if any(request.category != SemanticRequestCategory.CONTRACTUAL_OTHER for request in requests):
        raise RuntimeError("Contractual-other-only safety gate failed")
    print(json.dumps({
        "pre_execution": True, "category": SemanticRequestCategory.CONTRACTUAL_OTHER,
        "request_ids": [request.request_id for request in requests],
        "evidence_records": sum(len(request.records) for request in requests),
        "compact_context_characters": sum(request.character_count for request in requests),
        "planned_requests_selected": len(requests), "other_category_requests_selected": 0,
    }, indent=2))
    result = ContractualOtherBlueprintService(
        GoogleContractualOtherProvider(settings.gemini_api_key, settings.gemini_model)
    ).execute(plan)
    print(json.dumps({
        "execution": result.model_dump(mode="json", exclude={"rules": {"__all__": {"source_references"}}}),
        "rule_summaries": [{
            "rule_id": rule.rule_id, "kind": rule.kind, "title": rule.title,
            "responsible_party": rule.responsible_party, "obligation_semantics": rule.obligation_semantics,
            "duration_value": rule.duration_value, "duration_unit": rule.duration_unit,
            "deadline_or_timing": rule.deadline_or_timing, "percentage_value": rule.percentage_value,
            "money_value": rule.money_value, "currency": rule.currency,
            "evidence_handles": rule.evidence_handles, "source_pages": rule.source_pages,
            "requires_review": rule.requires_review, "review_reason": rule.review_reason,
        } for rule in result.rules],
        "other_category_requests_executed": 0,
    }, indent=2))


if __name__ == "__main__": main()
