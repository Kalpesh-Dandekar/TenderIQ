import json
import os
from pathlib import Path

from app.models.blueprint_evidence import SemanticRequestCategory
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.evidence_packager import BlueprintEvidencePackager
from app.services.hybrid_blueprint import build_local_draft, create_work_units
from app.services.pdf_extractor import extract_pdf
from app.services.qualification_blueprint import (
    GoogleQualificationProvider,
    QualificationBlueprintService,
    select_qualification_request,
)


def _load_runtime_configuration(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in {"GEMINI_API_KEY", "GEMINI_MODEL"}:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def main() -> None:
    service_root = Path(__file__).resolve().parent
    _load_runtime_configuration(service_root / ".env")
    from app.config import settings

    tender_path = service_root.parents[1] / "demo-data" / "IT Software RPF.pdf"
    document = extract_pdf(tender_path.read_bytes(), tender_path.name)
    analysis = LocalDocumentIntelligenceService().analyze(document)
    draft = build_local_draft(analysis)
    work_units = create_work_units(draft)
    plan = BlueprintEvidencePackager().package(draft, work_units, document.total_characters)
    request = select_qualification_request(plan)
    if request.category != SemanticRequestCategory.QUALIFICATION:
        raise RuntimeError("Qualification-only safety gate failed")

    result = QualificationBlueprintService(
        GoogleQualificationProvider(settings.gemini_api_key, settings.gemini_model)
    ).execute(plan)
    safe_report = {
        "request": {
            "category": request.category,
            "request_id": request.request_id,
            "evidence_records": len(request.records),
            "compact_context_characters": request.character_count,
        },
        "execution": result.model_dump(mode="json", exclude={"requirements": {"__all__": {"source_references"}}}),
        "requirement_summaries": [
            {
                "requirement_id": item.requirement_id,
                "title": item.title,
                "requirement_text": item.requirement_text,
                "mandatory": item.mandatory,
                "normalized": item.normalized.model_dump(mode="json"),
                "evidence_handles": item.evidence_handles,
                "source_pages": item.source_pages,
                "requires_review": item.requires_review,
                "review_reason": item.review_reason,
            }
            for item in result.requirements
        ],
        "other_category_requests_executed": 0,
    }
    print(json.dumps(safe_report, indent=2))


if __name__ == "__main__":
    main()
