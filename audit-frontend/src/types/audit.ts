export interface FailedChecklistItem {
  rule_id: string
  rule_title: string
  description: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  evidence: string
  page_number: number | null
}

export interface DocumentAuditResult {
  document_name: string
  passed: boolean
  score: number
  failed_rules: FailedChecklistItem[]
  remarks: string
  preview_base64: string
}

export interface FinalAuditReport {
  audit_title: string
  documents_processed: number
  documents_passed: number
  documents_failed: number
  overall_score: number
  overall_result: 'PASS' | 'REVIEW REQUIRED' | 'FAIL'
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
}

export type Status = 'idle' | 'loading' | 'success' | 'error'
