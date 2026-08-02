/**
 * Audit V2 API Client — Communicates with FastAPI on port :8100
 */

export const V2_BASE = 'http://localhost:8100/api/v2'

export interface UploadResponse {
  message: string
  document: any
  documents?: any[]
  findings: any[]
  cluster_id: string | null
  is_vlm_fallback: boolean
}


export interface AuditLogResponse {
  tenant_id: string
  chain_valid: boolean
  verification_error: string | null
  entries: {
    entry_id: string
    action: string
    resource_type: string
    resource_id: string
    actor_id: string
    payload: any
    timestamp: string
    prev_hash: string
    hash_chain: string
  }[]
}

export interface ReviewQueueResponse {
  count: number
  pending_items: {
    item_id: string
    document_id: string
    priority_score: number
    finding: any
    created_at: string
    status: string
  }[]
  golden_set_candidates_count: number
}

export async function uploadDocumentsV2(
  files: FileList | File[],
  tenantId: string = 'tenant_default'
): Promise<UploadResponse> {
  const formData = new FormData()
  const fileArray = Array.from(files)
  fileArray.forEach((f) => formData.append('files', f))

  const res = await fetch(`${V2_BASE}/audit/upload?tenant_id=${encodeURIComponent(tenantId)}`, {
    method: 'POST',
    body: formData,
  })

  if (!res.ok) {
    const errorBody = await res.json().catch(() => null)
    throw new Error(errorBody?.detail || `Upload failed with status ${res.status}`)
  }

  return res.json()
}


export async function fetchFindingsV2(tenantId: string = 'tenant_default'): Promise<any> {
  const res = await fetch(`${V2_BASE}/audit/findings?tenant_id=${encodeURIComponent(tenantId)}`)
  if (!res.ok) throw new Error(`Failed to fetch findings (${res.status})`)
  return res.json()
}

export async function fetchAuditLogV2(tenantId: string = 'tenant_default'): Promise<AuditLogResponse> {
  const res = await fetch(`${V2_BASE}/audit/log?tenant_id=${encodeURIComponent(tenantId)}`)
  if (!res.ok) throw new Error(`Failed to fetch audit log (${res.status})`)
  return res.json()
}

export async function fetchReviewQueueV2(): Promise<ReviewQueueResponse> {
  const res = await fetch(`${V2_BASE}/audit/review-queue`)
  if (!res.ok) throw new Error(`Failed to fetch review queue (${res.status})`)
  return res.json()
}

export async function submitReviewV2(
  itemId: string,
  action: 'confirm' | 'reject_as_false_positive' | 'escalate',
  reviewerId: string = 'reviewer_1',
  comments?: string
): Promise<any> {
  const res = await fetch(`${V2_BASE}/audit/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      item_id: itemId,
      action,
      reviewer_id: reviewerId,
      comments,
    }),
  })
  if (!res.ok) {
    const errorBody = await res.json().catch(() => null)
    throw new Error(errorBody?.detail || `Review submission failed (${res.status})`)
  }
  return res.json()
}
