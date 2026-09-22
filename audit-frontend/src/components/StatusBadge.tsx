import type { DocumentAuditResult } from '../types/audit'
import { getDocumentStatus } from '../utils/documentStatus'

interface StatusBadgeProps {
  /** Pass the full document — the badge will derive its own label and colour. */
  doc: DocumentAuditResult
}

export function StatusBadge({ doc }: StatusBadgeProps) {
  const status = getDocumentStatus(doc)
  return (
    <span className={`inline-block ${status.badgeBg} rounded-lg px-3 py-1 text-[13px] font-medium whitespace-nowrap`}>
      {status.label}
    </span>
  )
}
