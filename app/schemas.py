from pydantic import BaseModel, Field
from typing import Optional
from typing_extensions import Literal


class DocumentSummary(BaseModel):
    document_name: str
    document_type: Optional[str] = None
    page_count: Optional[int] = None
    summary: Optional[str] = None
    language: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class AuditRule(BaseModel):
    rule_id: str
    title: str
    description: str
    severity: Literal["critical", "high", "medium", "low"]
    mandatory: bool = True


class AuditChecklist(BaseModel):
    audit_name: str
    version: str = "1.0"
    rules: list[AuditRule] = Field(default_factory=list)


class FailedChecklistItem(BaseModel):
    rule_id: str
    rule_title: str
    description: str
    severity: Literal["critical", "high", "medium", "low"]
    evidence: str = ""
    page_number: Optional[int] = None


class DocumentAuditResult(BaseModel):
    document_name: str
    passed: bool
    score: float = Field(ge=0.0, le=100.0)
    failed_rules: list[FailedChecklistItem] = Field(default_factory=list)
    remarks: str = ""
    preview_base64: str = ""


class FinalAuditReport(BaseModel):
    audit_title: str
    documents_processed: int
    documents_passed: int
    documents_failed: int
    overall_score: float
    overall_result: str
    summary: str
    document_results: list[DocumentAuditResult] = Field(default_factory=list)
