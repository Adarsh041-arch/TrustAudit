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
  auditTitle?: string
): Promise<void> {
  const res = await fetch(`${BASE}/api/audit/download`, {
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
  const filename = match?.[1] || `TrustAudit_Report.docx`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
