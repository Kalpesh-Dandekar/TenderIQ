# TenderIQ AI Service

Minimal FastAPI foundation for future document-intelligence capabilities.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Check `GET http://localhost:8000/health`.
