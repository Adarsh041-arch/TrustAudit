from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class PredictionInterval(BaseModel):
    lower: float
    upper: float

class FailedRuleDetail(BaseModel):
    rule_id: str
    rule_title: str
    finding: str
    evidence: str
    impact: str
    recommendation: str
    severity: str
    page_number: Optional[int] = None

class MLProbabilities(BaseModel):
    compliant: float
    partially_compliant: float
    non_compliant: float

class MLPredictionDetail(BaseModel):
    prediction: str
    probabilities: MLProbabilities
    features_used: List[float]
    mode: str

class EnhancedDocumentResult(BaseModel):
    document_name: str
    document_type: str
    passed: bool
    score: float
    risk_level: str
    risk_explanation: str
    failed_rules: List[FailedRuleDetail] = Field(default_factory=list)
    ml_prediction: Optional[MLPredictionDetail] = None
    confidence_score: float
    human_review_recommended: bool
    remarks: str
    preview_base64: str = ""
    page_count: int = 1
    summary_text: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

class EnhancedFinalReport(BaseModel):
    audit_title: str
    documents_processed: int
    documents_passed: int
    documents_failed: int
    overall_score: float
    overall_result: str
    summary: str
    document_results: List[EnhancedDocumentResult] = Field(default_factory=list)

class EnhancedAuditResponse(BaseModel):
    report: EnhancedFinalReport
    prediction_interval: PredictionInterval
    elapsed_seconds: float
    cross_verification: Optional[Dict[str, Any]] = None
    analytics: Optional[Dict[str, Any]] = None

class AuditRequest(BaseModel):
    folder_path: str
    audit_title: Optional[str] = "Untitled Audit"

class CopilotChatRequest(BaseModel):
    query: str
    audit_results: List[Dict[str, Any]]
    cross_verification: Optional[Dict[str, Any]] = None
    chat_history: Optional[List[Dict[str, str]]] = None

class CopilotChatResponse(BaseModel):
    answer: str
