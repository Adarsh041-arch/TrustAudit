import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.schemas import AuditRequest, AuditResponse
from backend.runner import run_audit

app = FastAPI(title="TrustAudit API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/audit", response_model=AuditResponse)
def audit(req: AuditRequest):
    if not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=400, detail=f"Folder not found: {req.folder_path}")
    return run_audit(folder_path=req.folder_path, audit_title=req.audit_title)
