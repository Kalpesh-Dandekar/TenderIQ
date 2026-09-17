from pathlib import Path

from fastapi import HTTPException, UploadFile


async def read_validated_pdf(file: UploadFile, max_size_bytes: int) -> tuple[str, bytes]:
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Filename must end in .pdf")
    if file.content_type and file.content_type.lower() != "application/pdf":
        raise HTTPException(status_code=415, detail="Content type must be application/pdf")

    data = await file.read(max_size_bytes + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=400, detail="PDF file must not be empty")
    if len(data) > max_size_bytes:
        raise HTTPException(status_code=413, detail="PDF exceeds the configured size limit")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="File does not have a valid PDF signature")
    return filename, data
