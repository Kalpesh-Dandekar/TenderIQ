from collections.abc import Callable
from typing import Protocol

from pydantic import ValidationError

from app.models.blueprint import ChunkCandidates
from app.models.hybrid_blueprint import GeminiUsage, GeminiWorkUnit, WorkUnitResult
from app.services.chunking import TextChunk


class GeminiConfigurationError(Exception):
    pass


class GeminiServiceError(Exception):
    def __init__(self, message: str, request_count: int = 0, retry_count: int = 0) -> None:
        super().__init__(message)
        self.request_count = request_count
        self.retry_count = retry_count


class CandidateProvider(Protocol):
    def extract_chunk(self, chunk: TextChunk) -> ChunkCandidates: ...


class GoogleGeminiProvider:
    def __init__(self, api_key: str | None, model: str, max_attempts: int = 2) -> None:
        self._api_key = api_key
        self._model = model
        self._max_attempts = max_attempts
        self._generate_override: Callable[[str], str] | None = None

    def _generate(self, prompt: str) -> str:
        text, _usage = self._generate_response(prompt)
        return text

    def _generate_response(self, prompt: str) -> tuple[str, GeminiUsage]:
        if self._generate_override is not None:
            return self._generate_override(prompt), GeminiUsage()
        if not self._api_key:
            raise GeminiConfigurationError("Gemini is not configured")
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ChunkCandidates,
                    temperature=0,
                ),
            )
        except GeminiConfigurationError:
            raise
        except Exception as error:
            raise GeminiServiceError("Gemini candidate extraction failed", request_count=1) from error
        if not response.text:
            raise GeminiServiceError("Gemini returned an empty response", request_count=1)
        usage_metadata = response.usage_metadata
        usage = GeminiUsage(
            input_tokens=getattr(usage_metadata, "prompt_token_count", None) if usage_metadata else None,
            output_tokens=getattr(usage_metadata, "candidates_token_count", None) if usage_metadata else None,
        )
        return response.text, usage

    def extract_chunk(self, chunk: TextChunk) -> ChunkCandidates:
        prompt = _build_prompt(chunk)
        last_error: Exception | None = None
        for _attempt in range(self._max_attempts):
            try:
                return ChunkCandidates.model_validate_json(self._generate(prompt))
            except (ValidationError, ValueError) as error:
                last_error = error
        raise GeminiServiceError("Gemini returned malformed structured output") from last_error

    def finalize_work_unit(self, work_unit: GeminiWorkUnit) -> WorkUnitResult:
        prompt = _build_hybrid_prompt(work_unit)
        total_input: int | None = None
        total_output: int | None = None
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                text, usage = self._generate_response(prompt)
                if usage.input_tokens is not None:
                    total_input = (total_input or 0) + usage.input_tokens
                if usage.output_tokens is not None:
                    total_output = (total_output or 0) + usage.output_tokens
                candidates = ChunkCandidates.model_validate_json(text)
                return WorkUnitResult(
                    candidates=candidates,
                    usage=GeminiUsage(
                        request_count=attempt,
                        retry_count=attempt - 1,
                        input_tokens=total_input,
                        output_tokens=total_output,
                    ),
                )
            except (ValidationError, ValueError) as error:
                last_error = error
        raise GeminiServiceError(
            "Gemini returned malformed structured output", request_count=self._max_attempts, retry_count=self._max_attempts - 1
        ) from last_error


def _build_prompt(chunk: TextChunk) -> str:
    pages = ", ".join(str(page) for page in sorted(chunk.page_numbers))
    return (
        "Extract only explicitly supported tender metadata, requirements, required documents, and evaluation rules. "
        "Do not invent values, page numbers, clauses, formulas, mandatory status, or evidence. Preserve concise exact excerpts. "
        "Use only source page numbers present in this chunk. Mark ambiguous items requires_review=true and lower confidence. "
        f"Allowed pages: {pages}. Chunk: {chunk.chunk_id}.\n\n{chunk.prompt_text()}"
    )


def _build_hybrid_prompt(work_unit: GeminiWorkUnit) -> str:
    local_candidates = "\n".join(
        f"- {candidate.candidate_id}: {candidate.raw_text} [{candidate.resolution_capability}]"
        for candidate in work_unit.candidates
    ) or "- No local candidate; inspect this procurement-relevant uncovered section."
    context = "\n\n".join(
        f"[PAGE {item.page_number}] [SECTION {item.section_id}]"
        f"{f' [HEADING {item.heading}]' if item.heading else ''}\n{item.text}"
        for item in work_unit.context
    )
    return (
        "Finalize only the unresolved tender information in this grounded work unit. "
        "Use deterministic local facts as constraints and do not overwrite them without explicit source evidence. "
        "Identify requirements, required evidence, and evaluation relationships only when supported by supplied text. "
        "Do not invent thresholds, mandatory status, documents, formulas, dates, clauses, excerpts, or page numbers. "
        "Preserve uncertainty with requires_review=true and lower confidence. Every returned item must quote an exact supplied excerpt.\n\n"
        f"WORK UNIT: {work_unit.work_unit_id}\nREASON: {work_unit.reason}\nLOCAL UNRESOLVED CANDIDATES:\n{local_candidates}\n\n"
        f"GROUNDED CONTEXT:\n{context}"
    )
