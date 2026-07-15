import type { DocumentAuditResult, PredictionInterval } from '../types/audit'
import { DocumentCard } from '../components/DocumentCard'

interface DocumentListProps {
  documents: DocumentAuditResult[]
  interval: PredictionInterval
}

export function DocumentList({ documents, interval }: DocumentListProps) {
  return (
    <div className="space-y-4">
      <h2 className="text-[18px] font-medium text-ink">Documents</h2>
      {documents.map((doc) => (
        <DocumentCard key={doc.document_name} doc={doc} interval={interval} />
      ))}
    </div>
  )
}
