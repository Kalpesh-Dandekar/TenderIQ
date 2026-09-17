import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    max_pdf_size_mb: int

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
    return Settings(max_pdf_size_mb=max_size)


settings = load_settings()
