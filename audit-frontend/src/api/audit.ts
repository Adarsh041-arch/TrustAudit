import type { AuditResponse } from '../types/audit'

const BASE = 'http://localhost:8000'

export async function runAudit(
  folderPath: string,
  auditTitle?: string
): Promise<AuditResponse> {
  const res = await fetch(`${BASE}/api/audit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      folder_path: folderPath,
      audit_title: auditTitle || 'Untitled Audit',
    }),
  })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail || `Request failed (${res.status})`)
  }

  return res.json()
}

export async function downloadReport(
  folderPath: string,
  auditTitle?: string,
  format: 'docx' | 'pdf' = 'docx'
): Promise<void> {
  const res = await fetch(`${BASE}/api/audit/download?format=${format}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      folder_path: folderPath,
      audit_title: auditTitle || 'Untitled Audit',
    }),
  })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail || `Download failed (${res.status})`)
  }

  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?(.+?)"?$/)
  const filename = match?.[1] || `TrustAudit_Report.${format}`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export async function copilotChat(
  query: string,
  auditResults: any[],
  crossVerification?: any,
  chatHistory?: any[]
): Promise<string> {
  const res = await fetch(`${BASE}/api/copilot/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      audit_results: auditResults,
      cross_verification: crossVerification,
      chat_history: chatHistory
    })
  })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail || `Copilot failed (${res.status})`)
  }

  const data = await res.json()
  return data.answer
}

export async function trainMLClassifier(): Promise<string> {
  const res = await fetch(`${BASE}/api/ml/train`, {
    method: 'POST'
  })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail || 'ML Training failed')
  }

  const data = await res.json()
  return data.message
}

export async function getEvaluationData(): Promise<any> {
  const res = await fetch(`${BASE}/api/eval`)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail || 'Evaluation failed')
  }
  return res.json()
}
