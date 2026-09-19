import json
import os
from pathlib import Path

from app.models.blueprint_evidence import SemanticRequestCategory
from app.services.commercial_financial_blueprint import (
    CommercialFinancialBlueprintService,
    GoogleCommercialFinancialProvider,
    select_commercial_financial_request,
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
    service_root = Path(__file__).resolve().parent
    _load_runtime_configuration(service_root / ".env")
    from app.config import settings
    tender_path = service_root.parents[1] / "demo-data" / "IT Software RPF.pdf"
    document = extract_pdf(tender_path.read_bytes(), tender_path.name)
    analysis = LocalDocumentIntelligenceService().analyze(document)
    draft = build_local_draft(analysis)
    plan = BlueprintEvidencePackager().package(draft, create_work_units(draft), document.total_characters)
    request = select_commercial_financial_request(plan)
    if request.category != SemanticRequestCategory.COMMERCIAL_FINANCIAL:
        raise RuntimeError("Commercial-financial-only safety gate failed")
    print(json.dumps({"pre_execution": True, "category": request.category, "request_id": request.request_id,
                      "evidence_records": len(request.records), "compact_context_characters": request.character_count,
                      "planned_requests_selected": 1, "other_category_requests_selected": 0}, indent=2))
    result = CommercialFinancialBlueprintService(
        GoogleCommercialFinancialProvider(settings.gemini_api_key, settings.gemini_model)
    ).execute(plan)
    print(json.dumps({
        "execution": result.model_dump(mode="json", exclude={"rules": {"__all__": {"source_references"}}}),
        "rule_summaries": [{
            "rule_id": item.rule_id, "kind": item.kind, "title": item.title,
            "formula_expression": item.formula_expression, "formula_variables": item.formula_variables,
            "technical_weight_percent": item.technical_weight_percent,
            "financial_weight_percent": item.financial_weight_percent,
            "money_value": item.money_value, "currency": item.currency,
            "evidence_handles": item.evidence_handles, "source_pages": item.source_pages,
            "requires_review": item.requires_review, "review_reason": item.review_reason,
        } for item in result.rules],
        "other_category_requests_executed": 0,
    }, indent=2))


if __name__ == "__main__": main()
