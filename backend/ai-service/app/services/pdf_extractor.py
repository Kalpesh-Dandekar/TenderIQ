import hashlib

import pymupdf

from app.models.extraction import (
    ExtractedDocument,
    ExtractedPage,
    ExtractionAssessment,
    PdfMetadata,
)

MIN_MEANINGFUL_CHARACTERS_PER_PAGE = 20
TEXT_EXTRACTABLE_PAGE_RATIO = 0.8


class PdfExtractionError(Exception):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def assess_extraction(page_count: int, text_pages: int, total_characters: int) -> ExtractionAssessment:
    if page_count == 0 or text_pages == 0 or total_characters < page_count * MIN_MEANINGFUL_CHARACTERS_PER_PAGE:
        return ExtractionAssessment.OCR_MAY_BE_REQUIRED
    if text_pages / page_count >= TEXT_EXTRACTABLE_PAGE_RATIO:
        return ExtractionAssessment.TEXT_EXTRACTABLE
    return ExtractionAssessment.PARTIALLY_EXTRACTABLE


def _safe_metadata(metadata: dict[str, str] | None) -> PdfMetadata:
    source = metadata or {}

    def value(name: str) -> str | None:
        raw = source.get(name, "").strip()
        return raw or None

    return PdfMetadata(
        title=value("title"),
        author=value("author"),
        subject=value("subject"),
        keywords=value("keywords"),
        creator=value("creator"),
        producer=value("producer"),
        creation_date=value("creationDate"),
        modification_date=value("modDate"),
    )


def extract_pdf(data: bytes, filename: str) -> ExtractedDocument:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as error:
        raise PdfExtractionError("PDF is corrupted or cannot be opened") from error

    try:
        if document.needs_pass:
            raise PdfExtractionError("Password-protected PDFs cannot be extracted", 422)

        pages: list[ExtractedPage] = []
        text_pages = 0
        total_characters = 0
        total_words = 0
        for index, page in enumerate(document):
            text = page.get_text("text")
            character_count = len(text)
            word_count = len(text.split())
            if len(text.strip()) >= MIN_MEANINGFUL_CHARACTERS_PER_PAGE:
                text_pages += 1
            total_characters += character_count
            total_words += word_count
            pages.append(
                ExtractedPage(
                    page_number=index + 1,
                    text=text,
                    character_count=character_count,
                    word_count=word_count,
                )
            )

        page_count = len(pages)
        return ExtractedDocument(
            filename=filename,
            sha256=hashlib.sha256(data).hexdigest(),
            page_count=page_count,
            total_characters=total_characters,
            total_words=total_words,
            text_pages=text_pages,
            empty_pages=page_count - text_pages,
            assessment=assess_extraction(page_count, text_pages, total_characters),
            metadata=_safe_metadata(document.metadata),
            pages=pages,
        )
    except PdfExtractionError:
        raise
    except Exception as error:
        raise PdfExtractionError("PDF text extraction failed", 422) from error
    finally:
        document.close()
