from pydantic import BaseModel, Field
from typing import Optional

from app.schemas import (
    DocumentSummary,
    AuditChecklist,
    DocumentAuditResult,
    FinalAuditReport,
)


class AuditState(BaseModel):
    audit_title: str = ""
    uploaded_folder: str = ""
    documents: list[str] = Field(default_factory=list)
    document_summaries: list[DocumentSummary] = Field(default_factory=list)
    audit_checklist: Optional[AuditChecklist] = None
    audit_results: list[DocumentAuditResult] = Field(default_factory=list)
    final_report: Optional[FinalAuditReport] = None
    processing_index: int = 0
