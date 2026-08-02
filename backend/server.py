import os
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.schemas import (
    AuditRequest, 
    EnhancedAuditResponse, 
    CopilotChatRequest, 
    CopilotChatResponse
)
from backend.runner import run_enhanced_audit
from reporting.report_builders import generate_docx_report, generate_pdf_report
from copilot.chat_bot import CopilotChatbot
from ml_models.risk_classifier import DocumentRiskClassifier
from evaluation.evaluator import ComplianceEvaluator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TrustAudit Compliance Intelligence Platform API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.post("/api/audit", response_model=EnhancedAuditResponse)
def audit(req: AuditRequest):
    if not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=400, detail=f"Folder not found: {req.folder_path}")
    try:
        return run_enhanced_audit(folder_path=req.folder_path, audit_title=req.audit_title)
    except Exception as e:
        logger.error(f"Audit failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/audit/download")
def audit_download(req: AuditRequest, format: str = Query("docx", enum=["docx", "pdf"])):
    if not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=400, detail=f"Folder not found: {req.folder_path}")
    
    try:
        response_data = run_enhanced_audit(folder_path=req.folder_path, audit_title=req.audit_title)
        
        # Convert response object to dict for reporting builders
        audit_dict = response_data.model_dump()
        
        if format.lower() == "pdf":
            file_bytes = generate_pdf_report(audit_dict)
            media_type = "application/pdf"
            filename = f"TrustAudit_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        else:
            file_bytes = generate_docx_report(audit_dict)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = f"TrustAudit_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
            
        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Download generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/copilot/chat", response_model=CopilotChatResponse)
def copilot_chat(req: CopilotChatRequest):
    try:
        answer = CopilotChatbot.answer_query(
            query=req.query,
            audit_results=req.audit_results,
            cross_verification=req.cross_verification,
            chat_history=req.chat_history
        )
        return CopilotChatResponse(answer=answer)
    except Exception as e:
        logger.error(f"Copilot Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ml/train")
def train_classifier():
    try:
        classifier = DocumentRiskClassifier()
        classifier.train_and_save()
        return {"status": "success", "message": "Random Forest model trained and saved successfully."}
    except Exception as e:
        logger.error(f"ML Classifier training failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/eval")
def get_evaluation():
    try:
        # Run mock evaluation benchmarks
        mock_predictions = [
            {"document_name": "INV-1.pdf", "passed": True, "score": 95.0, "confidence": 88.5, "latency": 2.1},
            {"document_name": "PO-1.pdf", "passed": True, "score": 90.0, "confidence": 85.0, "latency": 1.9},
            {"document_name": "REC-1.jpg", "passed": False, "score": 45.0, "confidence": 92.0, "latency": 1.5},
            {"document_name": "INV-2.pdf", "passed": False, "score": 60.0, "confidence": 70.0, "latency": 2.4},
            {"document_name": "CONTRACT-1.pdf", "passed": True, "score": 100.0, "confidence": 95.0, "latency": 3.1}
        ]
        
        mock_ground_truth = [
            {"document_name": "INV-1.pdf", "passed_actual": True},
            {"document_name": "PO-1.pdf", "passed_actual": True},
            {"document_name": "REC-1.jpg", "passed_actual": False},
            {"document_name": "INV-2.pdf", "passed_actual": False},
            {"document_name": "CONTRACT-1.pdf", "passed_actual": True}
        ]
        
        results = ComplianceEvaluator.evaluate_performance(mock_predictions, mock_ground_truth)
        return results
    except Exception as e:
        logger.error(f"Evaluation report failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
