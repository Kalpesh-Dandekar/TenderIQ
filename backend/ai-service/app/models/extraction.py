from enum import StrEnum

from pydantic import BaseModel


class ExtractionAssessment(StrEnum):
    TEXT_EXTRACTABLE = "TEXT_EXTRACTABLE"
    PARTIALLY_EXTRACTABLE = "PARTIALLY_EXTRACTABLE"
    OCR_MAY_BE_REQUIRED = "OCR_MAY_BE_REQUIRED"


class PdfMetadata(BaseModel):
    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: str | None = None
    creator: str | None = None
    producer: str | None = None
    creation_date: str | None = None
    modification_date: str | None = None


class ExtractedPage(BaseModel):
    page_number: int
    text: str
    character_count: int
    word_count: int


class ExtractedDocument(BaseModel):
    filename: str
    sha256: str
    page_count: int
    total_characters: int
    total_words: int
    text_pages: int
    empty_pages: int
    assessment: ExtractionAssessment
    metadata: PdfMetadata
    pages: list[ExtractedPage]


class ExtractionResponse(BaseModel):
    success: bool = True
    document: ExtractedDocument
