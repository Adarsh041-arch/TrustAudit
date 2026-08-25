/**
 * Payment Reconciliation API client — /api/recon on :8100
 */

const RECON_BASE = 'http://localhost:8100/api/recon'

export interface PayoutRecord {
  txn_id: string
  payout_amount: string
  payout_date: string
  settlement_status: string
  currency: string
}

export interface BankEntry {
  bank_ref: string
  credited_amount: string
  value_date: string
  counterparty: string | null
  currency: string
}

export interface LedgerRecord {
  invoice_id: string
  expected_amount: string
  due_date: string
  payer_id: string
  currency: string
}

export type MatchStatus = 'MATCHED' | 'EXCEPTION' | 'PARTIAL'

export interface MatchResult {
  txn_id: string
  status: MatchStatus
  payout: PayoutRecord | null
  bank: BankEntry | null
  ledger: LedgerRecord | null
  exception_type: string | null
  risk_level: 'critical' | 'high' | 'medium' | 'low' | null
  amount_delta: string | null
  date_drift_days: number | null
  decision_fingerprint: string
  llm_explanation: string | null
}

export interface ValidationReport {
  detected: number
  total_breaks: number
  fee_matches_confirmed: number
  fee_total: number
  drift_matches_confirmed: number
  drift_total: number
  false_positives: string[]
  false_negatives: string[]
  passed: boolean
}

export interface ReconciliationRun {
  run_id: string
  run_at: string
  total: number
  matched: number
  exceptions: number
  match_rate: string
  unmatched_bank_credits: number
  results: MatchResult[]
  llm_summary: string | null
  mode: 'demo' | 'live'
  validation: ValidationReport | null
  mode_note: string | null
}

export interface ReconHealth {
  match_rate: string | null
  last_run_id: string | null
  last_run_at: string | null
  total_runs_this_session: number
}

export interface ForecastBucket {
  week_start: string
  settled: string
  in_transit: string
  expected: string
  at_risk: string
}

export interface CashForecast {
  as_of: string
  median_lag_days: number
  lag_source: 'derived' | 'fallback'
  buckets: ForecastBucket[]
  in_transit_ids: string[]
  at_risk_ids: string[]
  llm_summary: string | null
}

export async function fetchForecast(runId: string): Promise<CashForecast> {
  const res = await fetch(`${RECON_BASE}/results/${runId}/forecast`)
  if (!res.ok) throw new Error(`Forecast failed with status ${res.status}`)
  return res.json()
}

export async function runReconciliation(
  payout: File,
  bank: File,
  ledger: File,
  groundTruth?: File | null,
): Promise<ReconciliationRun> {
  const formData = new FormData()
  formData.append('payout_report', payout)
  formData.append('bank_statement', bank)
  formData.append('ledger', ledger)
  if (groundTruth) formData.append('ground_truth', groundTruth)

  const res = await fetch(`${RECON_BASE}/run`, { method: 'POST', body: formData })
  if (!res.ok) {
    const errorBody = await res.json().catch(() => null)
    throw new Error(errorBody?.detail || `Reconciliation failed with status ${res.status}`)
  }
  return res.json()
}

export async function downloadReconReport(run: ReconciliationRun, format: 'docx' | 'pdf'): Promise<Blob> {
  const res = await fetch(`${RECON_BASE}/report?format=${format}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(run),
  })
  if (!res.ok) throw new Error(`Report download failed with status ${res.status}`)
  return res.blob()
}

export async function fetchReconHealth(): Promise<ReconHealth> {
  const res = await fetch(`${RECON_BASE}/health`)
  if (!res.ok) throw new Error(`Health check failed with status ${res.status}`)
  return res.json()
}

export async function askAi(runId: string, txnId: string, question: string): Promise<string> {
  const res = await fetch(`${RECON_BASE}/results/${runId}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ txn_id: txnId, question }),
  })
  if (!res.ok) {
    const errorBody = await res.json().catch(() => null)
    throw new Error(errorBody?.detail || `Ask AI failed with status ${res.status}`)
  }
  return (await res.json()).answer as string
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
