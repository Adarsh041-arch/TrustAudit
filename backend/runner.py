import base64
import math
import os
import time
from io import BytesIO
from typing import Optional

import fitz
from PIL import Image

from app.graph import build_graph
from app.state import AuditState
from app.schemas import FinalAuditReport

from backend.schemas import PredictionInterval, AuditResponse

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"})
THUMB_MAX_SIZE = 180


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
    except Exception:
        return ""


def compute_prediction_interval(report: FinalAuditReport) -> PredictionInterval:
    scores = [r.score for r in report.document_results]
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

    lower = max(0.0, report.overall_score - margin)
    upper = min(100.0, report.overall_score + margin)
    return PredictionInterval(lower=round(lower, 2), upper=round(upper, 2))


def run_audit(
    folder_path: str,
    audit_title: Optional[str] = None,
) -> AuditResponse:
    graph = build_graph()
    initial = AuditState(
        audit_title=audit_title or "Untitled Audit",
        uploaded_folder=folder_path,
    )
    t0 = time.time()
    result = graph.invoke(initial)
    elapsed = time.time() - t0

    report: FinalAuditReport = result["final_report"]
    interval = compute_prediction_interval(report)

    for doc_result in report.document_results:
        candidate = os.path.join(folder_path, doc_result.document_name)
        if os.path.isfile(candidate) and os.path.splitext(candidate)[1].lower() in SUPPORTED_EXTENSIONS:
            doc_result.preview_base64 = _generate_preview(candidate)

    return AuditResponse(
        report=report,
        prediction_interval=interval,
        elapsed_seconds=round(elapsed, 2),
    )
