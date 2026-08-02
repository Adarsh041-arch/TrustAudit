import base64
import math
import os
import time
import logging
from io import BytesIO
from typing import Optional, List, Dict, Any

import fitz
from PIL import Image

from audit_engine.explainable_audit import ComplianceAuditEngine
from audit_engine.cross_verification import CrossVerifier
from analytics.aggregator import AnalyticsAggregator
from backend.schemas import (
    EnhancedAuditResponse,
    EnhancedFinalReport,
    EnhancedDocumentResult,
    PredictionInterval
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"})
THUMB_MAX_SIZE = 180
CHECKLIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "checklist.md")

def _generate_preview(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".pdf":
            doc = fitz.open(file_path)
            if len(doc) == 0:
                doc.close()
                return ""
            pix = doc.load_page(0).get_pixmap()
            doc.close()
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        else:
            img = Image.open(file_path).convert("RGB")

        img.thumbnail((THUMB_MAX_SIZE, THUMB_MAX_SIZE), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        logger.warning(f"Thumbnail generation skipped for {file_path}: {e}")
        return ""

def compute_prediction_interval(scores: List[float], overall_score: float) -> PredictionInterval:
    n = len(scores)
    if n == 0:
        return PredictionInterval(lower=100.0, upper=100.0)
    if n == 1:
        margin = 12.5
    else:
        mean = sum(scores) / n
        variance = sum((s - mean) ** 2 for s in scores) / (n - 1)
        std_dev = math.sqrt(variance)
        margin = 1.96 * std_dev / math.sqrt(n)

    lower = max(0.0, overall_score - margin)
    upper = min(100.0, overall_score + margin)
    return PredictionInterval(lower=round(lower, 2), upper=round(upper, 2))

def run_enhanced_audit(
    folder_path: str,
    audit_title: Optional[str] = None,
) -> EnhancedAuditResponse:
    """Runs the full compliance auditing platform pipeline on the target folder."""
    t0 = time.time()
    
    # 1. Discover files
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"Folder not found: {folder_path}")
        
    documents = []
    for entry in os.scandir(folder_path):
        if entry.is_file():
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                documents.append(entry.path)
    documents = sorted(documents)
    
    # 2. Audit each document using the compliance audit engine
    engine = ComplianceAuditEngine()
    engine.initialize_policies(CHECKLIST_PATH)
    
    doc_results: List[EnhancedDocumentResult] = []
    scores = []
    
    for doc_path in documents:
        # Run audit
        res_data = engine.audit_document(doc_path, CHECKLIST_PATH)
        
        # Add preview image
        preview = _generate_preview(doc_path)
        res_data["preview_base64"] = preview
        
        # Map to Pydantic schema
        doc_res = EnhancedDocumentResult(**res_data)
        doc_results.append(doc_res)
        scores.append(doc_res.score)

    total = len(doc_results)
    passed = sum(1 for r in doc_results if r.passed)
    failed = total - passed
    overall_score = sum(scores) / total if total > 0 else 100.0
    
    if overall_score >= 80.0:
        overall_result = "PASS"
    elif overall_score >= 50.0:
        overall_result = "REVIEW REQUIRED"
    else:
        overall_result = "FAIL"
        
    summary_text = (
        f"Audit complete. {total} document(s) processed: "
        f"{passed} passed, {failed} failed. "
        f"Overall compliance score: {overall_score:.1f}%."
    )
    
    # 3. Create Enhanced Final Report
    report = EnhancedFinalReport(
        audit_title=audit_title or "Compliance Audit Report",
        documents_processed=total,
        documents_passed=passed,
        documents_failed=failed,
        overall_score=round(overall_score, 2),
        overall_result=overall_result,
        summary=summary_text,
        document_results=doc_results
    )
    
    # 4. Math prediction intervals
    interval = compute_prediction_interval(scores, overall_score)
    
    # Convert doc_results to raw dicts for verifier & aggregator
    raw_doc_results = [r.model_dump() for r in doc_results]
    
    # 5. Cross Verification (Three-Way Match)
    cross_res = CrossVerifier.verify_documents(raw_doc_results)
    
    # 6. Analytics Metrics & Chart Formats
    analytics_res = AnalyticsAggregator.aggregate_results(raw_doc_results)
    
    elapsed = time.time() - t0
    
    return EnhancedAuditResponse(
        report=report,
        prediction_interval=interval,
        elapsed_seconds=round(elapsed, 2),
        cross_verification=cross_res,
        analytics=analytics_res
    )
