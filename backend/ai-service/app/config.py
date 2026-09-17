import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    max_pdf_size_mb: int
    gemini_api_key: str | None
    gemini_model: str
    blueprint_chunk_max_characters: int
    gemini_max_attempts: int

    @property
    def max_pdf_size_bytes(self) -> int:
        return self.max_pdf_size_mb * 1024 * 1024


def load_settings() -> Settings:
    raw_size = os.getenv("MAX_PDF_SIZE_MB", "25")
    try:
        max_size = int(raw_size)
    except ValueError as error:
        raise RuntimeError("MAX_PDF_SIZE_MB must be an integer") from error
    if not 1 <= max_size <= 100:
        raise RuntimeError("MAX_PDF_SIZE_MB must be between 1 and 100")
    chunk_size = _bounded_integer("BLUEPRINT_CHUNK_MAX_CHARACTERS", 12000, 1000, 50000)
    max_attempts = _bounded_integer("GEMINI_MAX_ATTEMPTS", 2, 1, 3)
    return Settings(
        max_pdf_size_mb=max_size,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        blueprint_chunk_max_characters=chunk_size,
        gemini_max_attempts=max_attempts,
    )


def _bounded_integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


settings = load_settings()
