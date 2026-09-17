from collections.abc import Callable
from typing import Protocol

from pydantic import ValidationError

from app.models.blueprint import ChunkCandidates
from app.services.chunking import TextChunk


class GeminiConfigurationError(Exception):
    pass


class GeminiServiceError(Exception):
    pass


class CandidateProvider(Protocol):
    def extract_chunk(self, chunk: TextChunk) -> ChunkCandidates: ...


class GoogleGeminiProvider:
    def __init__(self, api_key: str | None, model: str, max_attempts: int = 2) -> None:
        self._api_key = api_key
        self._model = model
        self._max_attempts = max_attempts
        self._generate_override: Callable[[str], str] | None = None

    def _generate(self, prompt: str) -> str:
        if self._generate_override is not None:
            return self._generate_override(prompt)
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
            raise GeminiServiceError("Gemini candidate extraction failed") from error
        if not response.text:
            raise GeminiServiceError("Gemini returned an empty response")
        return response.text

    def extract_chunk(self, chunk: TextChunk) -> ChunkCandidates:
        prompt = _build_prompt(chunk)
        last_error: Exception | None = None
        for _attempt in range(self._max_attempts):
            try:
                return ChunkCandidates.model_validate_json(self._generate(prompt))
            except (ValidationError, ValueError) as error:
                last_error = error
        raise GeminiServiceError("Gemini returned malformed structured output") from last_error


def _build_prompt(chunk: TextChunk) -> str:
    pages = ", ".join(str(page) for page in sorted(chunk.page_numbers))
    return (
        "Extract only explicitly supported tender metadata, requirements, required documents, and evaluation rules. "
        "Do not invent values, page numbers, clauses, formulas, mandatory status, or evidence. Preserve concise exact excerpts. "
        "Use only source page numbers present in this chunk. Mark ambiguous items requires_review=true and lower confidence. "
        f"Allowed pages: {pages}. Chunk: {chunk.chunk_id}.\n\n{chunk.prompt_text()}"
    )
