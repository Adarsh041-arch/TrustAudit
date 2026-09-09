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
  document_status: 'READY' | 'INCOMPLETE' | 'PENDING' | 'FAILED' | 'UNSUPPORTED'
  audit_status?: 'PASS' | 'FAIL' | 'NOT_AUDITED' | 'NEEDS_REVIEW' | 'INCOMPLETE' | 'UNSUPPORTED'
  decision?: { status: string; blockers: string[]; required_checks: number; completed_checks: number; policy_version: string; scope: string }
  check_results?: Array<{ check_id: string; status: string; message: string; coverage?: Record<string, number> }>
  cross_check?: { execution_status: string; supported: boolean | null; partial?: boolean }
  score: number | null
  risk_level: string
  risk_explanation: string
  failed_rules: FailedChecklistItem[]
  ml_prediction: MLPredictionDetail | null
  confidence_score: number
  prediction_interval: PredictionInterval | null
  human_review_recommended: boolean
  remarks: string
  preview_base64: string
  page_count: number
  summary_text: string
  vision_backend: string
  vision_model: string | null
  coverage_complete: boolean
  pages_examined: number
  pages_unreadable: number[]
  grounding_rejection_count: number
  grounding_rejections?: string[]
  extraction_disagreements?: Record<string, string>
  extraction_strategy?: 'native_regex' | 'transcript_only' | 'transcript_plus_structured_fallback' | 'unsupported'
  glm_call_count?: number
  vision_call_count?: number
  structured_fallback_used?: boolean
  transcript_cache_hit?: boolean
  extraction_latency_ms?: number
  fallback_reasons?: string[]
  classification_status?: 'CONFIRMED' | 'AMBIGUOUS' | 'CONFLICTED' | 'UNSUPPORTED'
  classification_confidence?: number
  classification_method?: string
  classification_evidence?: Array<{ page: number; text: string }>
  alternative_types?: string[]
  metadata: Record<string, any>
  // Evidence-based pipeline output (new_requirements.md §5, §8). Optional so
  // report-only / legacy payloads that omit them still type-check; render with
  // `?? []`.
  evidences?: PipelineEvidence[]
  contradictions?: Contradiction[]
}

// ─── Evidence-based pipeline types (mirror audit_v2/domain/evidence.py) ──────

export type EvidenceNature =
  | 'metadata'
  | 'extracted_fields'
  | 'arithmetic_computation'
  | 'vlm_observations'
  | 'ocr+regex_observations'

export type Severity = 'critical' | 'high' | 'medium' | 'low'

/** One typed, provenance-tagged observation about a document (spec §5). */
export interface PipelineEvidence {
  evidence_id: string
  document_id: string
  nature: EvidenceNature
  /** regex | rapidocr | vlm | vlm_corrected | arithmetic | metadata */
  source: string
  payload: Record<string, any>
  summary: string
  confidence: number
  page: number | null
  created_at: string
}

/** An LLM-detected conflict between evidences (advisory, never authoritative). */
export interface Contradiction {
  document_id: string
  nature: EvidenceNature
  evidence: string
  reason: string
  confidence: number
  severity: Severity
  conflicting_with: string | null
}

// ─── Real-time pipeline progress (SSE, new_requirements.md §6) ───────────────

export type PipelineStepName =
  | 'received'
  | 'classify'
  | 'extract_regex'
  | 'extract_ocr'
  | 'extract_vlm'
  | 'vlm_selfcheck'
  | 'arithmetic'
  | 'cross_check'
  | 'score'
  | 'done'

export type StepStatusName = 'start' | 'ok' | 'skip' | 'error'

/** One progress event streamed from the server as it processes a document. */
export interface StepEvent {
  document_id: string
  step: PipelineStepName
  status: StepStatusName
  detail: string
  data: Record<string, any>
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
