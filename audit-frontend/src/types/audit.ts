export interface FailedChecklistItem {
  rule_id: string
  rule_title: string
  finding: string
  evidence: string
  description?: string
  impact: string
  recommendation: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  page_number: number | null
}


export interface MLProbabilities {
  compliant: number
  partially_compliant: number
  non_compliant: number
}

export interface MLPredictionDetail {
  prediction: string
  probabilities: MLProbabilities
  features_used: number[]
  mode: string
}

export interface DocumentAuditResult {
  document_id: string
  document_name: string
  document_type: string
  passed: boolean
  score: number
  risk_level: string
  risk_explanation: string
  failed_rules: FailedChecklistItem[]
  ml_prediction: MLPredictionDetail | null
  confidence_score: number
  human_review_recommended: boolean
  remarks: string
  preview_base64: string
  page_count: number
  summary_text: string
  metadata: Record<string, any>
}

export interface FinalAuditReport {
  audit_title: string
  documents_processed: number
  documents_passed: number
  documents_failed: number
  overall_score: number
  overall_result: string
  summary: string
  document_results: DocumentAuditResult[]
}

export interface PredictionInterval {
  lower: number
  upper: number
}

export interface AuditResponse {
  report: FinalAuditReport
  prediction_interval: PredictionInterval
  elapsed_seconds: number
  cross_verification?: any
  analytics?: any
}

export type Status = 'idle' | 'loading' | 'success' | 'error'
