import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.schemas import AuditRequest, AuditResponse
from backend.runner import run_audit
from backend.report_generator import generate_audit_docx

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


@app.post("/api/audit/download")
def audit_download(req: AuditRequest):
    if not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=400, detail=f"Folder not found: {req.folder_path}")
    response = run_audit(folder_path=req.folder_path, audit_title=req.audit_title)
    docx_bytes = generate_audit_docx(response)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"TrustAudit_Report_{ts}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
