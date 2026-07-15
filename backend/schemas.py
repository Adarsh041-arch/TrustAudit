from pydantic import BaseModel, Field
from typing import Optional

from app.schemas import FinalAuditReport


class PredictionInterval(BaseModel):
    lower: float
    upper: float


class AuditResponse(BaseModel):
    report: FinalAuditReport
    prediction_interval: PredictionInterval
    elapsed_seconds: float


class AuditRequest(BaseModel):
    folder_path: str
    audit_title: Optional[str] = "Untitled Audit"
