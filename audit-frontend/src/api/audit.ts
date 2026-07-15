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
