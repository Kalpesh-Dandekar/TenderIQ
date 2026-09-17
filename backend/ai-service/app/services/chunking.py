from dataclasses import dataclass

from app.models.extraction import ExtractedPage


@dataclass(frozen=True)
class PageSegment:
    page_number: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    segments: tuple[PageSegment, ...]

    @property
    def page_numbers(self) -> frozenset[int]:
        return frozenset(segment.page_number for segment in self.segments)

    def prompt_text(self) -> str:
        return "\n\n".join(f"[PAGE {segment.page_number}]\n{segment.text}" for segment in self.segments)


def _split_page(page: ExtractedPage, max_characters: int) -> list[PageSegment]:
    text = page.text.strip()
    if not text:
        return []
    return [PageSegment(page_number=page.page_number, text=text[start : start + max_characters]) for start in range(0, len(text), max_characters)]


def create_page_aware_chunks(pages: list[ExtractedPage], max_characters: int) -> list[TextChunk]:
    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    chunks: list[TextChunk] = []
    current: list[PageSegment] = []
    current_size = 0

    def flush() -> None:
        nonlocal current, current_size
        if current:
            chunks.append(TextChunk(chunk_id=f"CHUNK-{len(chunks) + 1:04d}", segments=tuple(current)))
            current = []
            current_size = 0

    for page in pages:
        for segment in _split_page(page, max_characters):
            separator_size = 2 if current else 0
            if current and current_size + separator_size + len(segment.text) > max_characters:
                flush()
            current.append(segment)
            current_size += separator_size + len(segment.text)
    flush()
    return chunks
