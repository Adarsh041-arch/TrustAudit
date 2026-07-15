import math
import time
from typing import Optional

from app.graph import build_graph
from app.state import AuditState
from app.schemas import FinalAuditReport

from backend.schemas import PredictionInterval, AuditResponse


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

    return AuditResponse(
        report=report,
        prediction_interval=interval,
        elapsed_seconds=round(elapsed, 2),
    )
