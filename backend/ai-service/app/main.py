from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routes.extraction import router as extraction_router

app = FastAPI(title="TenderIQ AI Service", version="0.1.0")
app.include_router(extraction_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "TenderIQ AI Service", "status": "healthy"}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, _error: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": "A PDF file is required"})


@app.exception_handler(Exception)
async def unexpected_error_handler(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Document extraction failed"})
