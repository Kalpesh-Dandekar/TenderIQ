# TenderIQ AI Service — PDF Extraction and Tender Blueprint V1

The service provides deterministic, page-wise PDF extraction and a source-grounded Tender Blueprint pipeline. A Tender Blueprint describes **what the tender requires**. A future Vendor Blueprint will describe **what a vendor claims or provides**; Vendor Blueprint is not implemented here.

## TenderIQ document intelligence architecture

TenderIQ separates five responsibilities:

1. **PyMuPDF extraction** reads embedded PDF text page by page.
2. **OCR** will later provide fallback text for scanned/image-only pages; it is not implemented.
3. **Local Document Intelligence** detects structure and procurement sections, extracts conservative candidates, normalizes safely measurable values, preserves evidence, and classifies resolution capability.
4. **Gemini semantic reasoning** is selective, evidence-grounded, and capability-routed by the hybrid planner. Local document intelligence and work-unit planning do not invoke Gemini.
5. **Python and human review** provide deterministic compliance calculations later and resolve remaining uncertainty respectively.

Permanent principles:

> Token optimization must never silently reduce procurement-analysis quality.

> LLM usage is selective, evidence-grounded and confidence-routed.

The internal `LocalDocumentIntelligenceService` accepts the existing B3 `ExtractedDocument` and requires no endpoint, Gemini, internet, database, vector store, or external service. Its reusable output preserves complete pages, detected sections, candidates, source evidence, routing decisions, and processing metrics so a document can be extracted and analyzed once, stored, and reused by future tender or vendor workflows.

Local candidates are not established Tender Requirements. Clear measurable clauses may be classified `LOCAL_DETERMINISTIC`; semantic clauses remain `LLM_REQUIRED`; negated, optional, historical, descriptive, or conflicting contexts are conservatively `REVIEW_REQUIRED`. Unknown content and original page text are retained.

## Hybrid Tender Blueprint finalization

The default scalable Blueprint flow is:

```text
PDF
→ PyMuPDF/OCR-ready extraction
→ Local Document Intelligence
→ Local Blueprint Draft
→ confidence and coverage routing
→ selective Gemini finalization
→ deterministic grounding, normalization, merge and validation
→ final Tender Blueprint
```

Gemini does not read every page by default. Locally reliable requirements and obvious mandatory documents can bypass it. Semantic and relevant review candidates are grouped into deterministic work units with coherent procurement-region context rather than isolated sentences. Substantive procurement-relevant uncovered sections remain eligible for semantic inspection so context reduction cannot silently reduce recall.

Every work unit retains real pages, headings, sections, excerpts, the document SHA-256, and a deterministic ID derived from source content plus prompt version. Duplicate work is suppressed within a run. This identity is suitable for a future persistent cache keyed by document, work unit, model, and prompt version; persistent caching is not implemented yet.

Gemini receives unresolved local information and grounded context under a strict finalization contract. Returned sources are checked against the supplied pages. Reliable local facts are merged first and cannot be silently replaced: conflicting interpretations become review-required. If selective finalization fails or omits an unresolved candidate, the local evidence remains in the Blueprint for review. Hybrid failure never activates expensive full-document processing automatically.

`POST /blueprint/tender` defaults to `HYBRID`. The frozen B4 behavior remains available only through the explicit query mode `?mode=FULL_LLM`, providing a benchmark and controlled recovery path.

Hybrid metrics record planned work units, coverage-safeguard units, context characters, actual request/retry counts, and SDK token metadata when supplied. This supports later comparison between full-LLM and hybrid utilization without inventing missing token counts.

### Blueprint evidence packaging

Internal work units are evidence containers, not API requests. The local `BlueprintEvidencePackager` converts unresolved work-unit evidence into a smaller set of packages organized by Blueprint purpose, while retaining original pages, sections, work-unit IDs, candidate IDs, excerpts, local normalization hints, and review flags. Local hints remain advisory; original evidence is authoritative.

Candidate extraction is not treated as complete evidence coverage. For each grounded work unit, the packager retains candidate evidence and compact, procurement-significant residual line regions not adequately represented by those candidates. Residual windows include adjacent source lines so table rows, formulas, and multi-line clauses remain intact without blindly duplicating complete work-unit context.

The packager excludes only confidently irrelevant candidate-free metadata or boilerplate. `OTHER` evidence, uncertain procurement content, and review-required evidence are preserved. Exact and very-high-confidence near duplicates are consolidated with all source references retained. Unrelated procurement domains are never combined solely to lower a future request count.

Internal audit packages default to a 24,000-character ceiling. They are not future API requests. A separate Gemini-facing plan assigns each evidence item once to `QUALIFICATION`, `TECHNICAL`, `COMMERCIAL_FINANCIAL`, or `CONTRACTUAL_OTHER`, while retaining its more granular local purpose and complete provenance.

Gemini-facing records use compact handles, pages, grounded text, review state, and only useful normalized value hints. Section IDs, work-unit IDs, candidate IDs, routing explanations, and duplicate provenance remain in the local evidence map. Category batching happens before size splitting, with an 80,000-character request ceiling. Oversized categories split only between complete evidence records, and no evidence is truncated. These ceilings are character-based planning boundaries, not token estimates. BP-3C.0 performs no Gemini request.

Packaging metrics compare characters before and after packaging, including candidate-derived and residual evidence counts, deduplication, exclusions, review preservation, represented sources, and package-size distribution. They are character measurements and must not be described as exact token or cost savings.

The same extraction and local-intelligence layers are designed for later Vendor Blueprint reuse, but Vendor Blueprint is not implemented.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Configuration is read from process environment variables and documented in `.env.example`:

- `MAX_PDF_SIZE_MB`: upload limit, default 25 MB.
- `GEMINI_API_KEY`: required only when Blueprint generation is actually invoked. Never commit it.
- `GEMINI_MODEL`: configurable model name.
- `BLUEPRINT_CHUNK_MAX_CHARACTERS`: bounded page-aware chunk size.
- `GEMINI_MAX_ATTEMPTS`: bounded structured-output attempts, limited to 1–3.

Application import, startup, PDF extraction, and tests do not contact Gemini. The Gemini client is created lazily only during actual candidate generation.

## Endpoints

- `GET http://localhost:8000/health`
- `POST http://localhost:8000/extract/pdf` with multipart field `file`
- `POST http://localhost:8000/blueprint/tender` with multipart field `file`

PowerShell example:

```powershell
curl.exe -X POST http://localhost:8000/extract/pdf -F "file=@C:\path\to\tender.pdf;type=application/pdf"
```

Each page is returned separately with human-friendly page numbering, text, character count, and word count. Document totals include text and empty-page counts. The SHA-256 digest identifies the received bytes but does not prove authenticity.

The deterministic assessment uses centralized thresholds:

- `TEXT_EXTRACTABLE`: meaningful text exists on at least 80% of pages.
- `PARTIALLY_EXTRACTABLE`: meaningful text exists, but on fewer than 80% of pages.
- `OCR_MAY_BE_REQUIRED`: no meaningful pages or less than 20 extracted characters per document page on average.

The assessment is a processing hint, not a definitive claim that OCR is required. OCR and Tender Blueprint generation are not implemented in B3.

## Tender Blueprint V1

The Blueprint endpoint reuses B3 validation and extraction, then runs this pipeline:

1. Split extracted pages into bounded chunks without losing page provenance. Oversized pages may be divided, but every segment retains its original page number.
2. Ask the isolated Google GenAI provider for structured candidate metadata, requirements, required documents, and evaluation rules.
3. Validate every response against strict Pydantic models. Malformed output receives only the configured bounded attempts.
4. Reject requirement, document, and evaluation references that point outside their source chunk or quote text absent from the referenced page.
5. Normalize safely detectable INR amounts, lakh/crore values, percentages, dates, durations, operators, and explicit boolean language in Python.
6. Conservatively deduplicate exact normalized wording while preserving all distinct source references.
7. Assign deterministic category-based requirement IDs, document IDs, and evaluation IDs after merging.

Raw wording is always retained. Ambiguous or conflicting facts remain unknown and are marked for review rather than invented. Natural-language requirements are not forced into numeric rules.

The generated JSON maps to the B1 `TenderBlueprint.blueprintJson` field. Requirements and required documents can later be projected into the corresponding B1 relational models. Generation itself does not require PostgreSQL, and persistence is intentionally deferred.

V1 limitations include reliance on text already extracted by PyMuPDF, conservative lexical deduplication, no OCR, no Vendor Blueprint, no evidence mapping, and no vendor evaluation. PDF metadata and SHA-256 identifiers are not authenticity proof.

## Tests

```powershell
python -m pytest
```

Gemini is mocked or replaced by fakes in automated tests. Tests require no API key, internet access, quota, or external service.
