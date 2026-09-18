from enum import StrEnum

from pydantic import Field

from app.models.blueprint import CandidateDocument, CandidateRequirement, ChunkCandidates, StrictModel, TenderBlueprint
from app.models.document_intelligence import LocalCandidate, LocalDocumentAnalysis, ProcessingMetrics


class BlueprintMode(StrEnum):
    HYBRID = "HYBRID"
    FULL_LLM = "FULL_LLM"


class WorkUnitReason(StrEnum):
    UNRESOLVED_CANDIDATES = "UNRESOLVED_CANDIDATES"
    COVERAGE_SAFEGUARD = "COVERAGE_SAFEGUARD"


class GroundedContext(StrictModel):
    page_number: int = Field(ge=1)
    section_id: str
    heading: str | None = None
    text: str


class LocalBlueprintDraft(StrictModel):
    analysis: LocalDocumentAnalysis
    local_requirements: list[CandidateRequirement] = Field(default_factory=list)
    local_documents: list[CandidateDocument] = Field(default_factory=list)
    unresolved_candidates: list[LocalCandidate] = Field(default_factory=list)


class GeminiWorkUnit(StrictModel):
    work_unit_id: str
    prompt_version: str
    document_sha256: str
    reason: WorkUnitReason
    section_ids: list[str] = Field(min_length=1)
    page_numbers: list[int] = Field(min_length=1)
    context: list[GroundedContext] = Field(min_length=1)
    candidates: list[LocalCandidate] = Field(default_factory=list)

    @property
    def context_characters(self) -> int:
        return sum(len(item.text) for item in self.context)


class GeminiUsage(StrictModel):
    request_count: int = Field(default=1, ge=0)
    retry_count: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class WorkUnitResult(StrictModel):
    candidates: ChunkCandidates
    usage: GeminiUsage = Field(default_factory=GeminiUsage)


class HybridBlueprintResult(StrictModel):
    blueprint: TenderBlueprint
    draft: LocalBlueprintDraft
    work_units: list[GeminiWorkUnit]
    metrics: ProcessingMetrics
