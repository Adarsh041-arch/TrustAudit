import type { DocumentAuditResult } from '../types/audit'
import { DocumentCard } from '../components/DocumentCard'

interface DocumentListProps {
  documents: DocumentAuditResult[]
}

export function DocumentList({ documents }: DocumentListProps) {
  return (
    <div className="space-y-4">
      <h2 className="text-[18px] font-medium text-ink">Documents</h2>
      {documents.map((doc) => (
        <DocumentCard key={doc.document_name} doc={doc} />
      ))}
    </div>
  )
}
