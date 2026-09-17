import hashlib

import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.models.extraction import ExtractionAssessment
from app.services.pdf_extractor import assess_extraction

client = TestClient(app, raise_server_exceptions=False)


def make_pdf(page_texts: list[str]) -> bytes:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    document.set_metadata({"title": "Tender test", "author": "TenderIQ"})
    data = document.tobytes()
    document.close()
    return data


def upload(data: bytes, filename: str = "tender.pdf", content_type: str = "application/pdf"):
    return client.post("/extract/pdf", files={"file": (filename, data, content_type)})


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_valid_text_pdf_extraction_and_statistics() -> None:
    data = make_pdf(["Tender qualification requirements and procurement conditions.", "Second page delivery requirements and contract milestones."])
    response = upload(data)
    assert response.status_code == 200
    document = response.json()["document"]
    assert document["page_count"] == 2
    assert [page["page_number"] for page in document["pages"]] == [1, 2]
    assert document["total_characters"] == sum(page["character_count"] for page in document["pages"])
    assert document["total_words"] == sum(page["word_count"] for page in document["pages"])
    assert document["text_pages"] == 2
    assert document["empty_pages"] == 0
    assert document["assessment"] == "TEXT_EXTRACTABLE"
    assert document["metadata"]["title"] == "Tender test"


def test_sha256_is_deterministic() -> None:
    data = make_pdf(["Deterministic source document with enough extractable text."])
    expected = hashlib.sha256(data).hexdigest()
    assert upload(data).json()["document"]["sha256"] == expected
    assert upload(data).json()["document"]["sha256"] == expected


def test_empty_upload_is_rejected() -> None:
    response = upload(b"")
    assert response.status_code == 400


def test_non_pdf_extension_is_rejected() -> None:
    response = upload(make_pdf(["Valid PDF bytes"]), "tender.txt")
    assert response.status_code == 415


def test_invalid_signature_is_rejected() -> None:
    response = upload(b"not a pdf")
    assert response.status_code == 415


def test_corrupted_pdf_is_handled_cleanly() -> None:
    response = upload(b"%PDF-corrupted")
    assert response.status_code == 422
    assert response.json() == {"detail": "PDF is corrupted or cannot be opened"}


def test_textless_page_is_preserved() -> None:
    response = upload(make_pdf(["Tender page with enough meaningful extracted content.", ""]))
    document = response.json()["document"]
    assert document["page_count"] == 2
    assert document["text_pages"] == 1
    assert document["empty_pages"] == 1
    assert document["pages"][1]["page_number"] == 2
    assert document["pages"][1]["text"] == ""
    assert document["assessment"] == "PARTIALLY_EXTRACTABLE"


def test_assessment_thresholds() -> None:
    assert assess_extraction(10, 9, 500) == ExtractionAssessment.TEXT_EXTRACTABLE
    assert assess_extraction(10, 4, 500) == ExtractionAssessment.PARTIALLY_EXTRACTABLE
    assert assess_extraction(10, 0, 0) == ExtractionAssessment.OCR_MAY_BE_REQUIRED
    assert assess_extraction(10, 10, 10) == ExtractionAssessment.OCR_MAY_BE_REQUIRED
