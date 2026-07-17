import type { DocumentAuditResult, PredictionInterval } from '../types/audit'
import { FlatCard } from './FlatCard'
import { ScoreDisplay } from './ScoreDisplay'
import { StatusBadge } from './StatusBadge'
import { FailedRulesList } from './FailedRulesList'

interface DocumentCardProps {
  doc: DocumentAuditResult
  interval: PredictionInterval
}

export function DocumentCard({ doc, interval }: DocumentCardProps) {
  return (
    <FlatCard>
      <div className="flex gap-4">
        {doc.preview_base64 && (
          <div className="shrink-0 w-[120px] h-[120px] rounded-lg overflow-hidden border-[0.5px] border-border bg-surface-1">
            <img
              src={`data:image/jpeg;base64,${doc.preview_base64}`}
              alt={doc.document_name}
              className="w-full h-full object-cover"
            />
          </div>
        )}

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between mb-3">
            <div className="min-w-0 mr-4">
              <p className="text-[18px] font-medium text-ink truncate">{doc.document_name}</p>
              <p className="text-[13px] text-muted mt-0.5">
                Score: {doc.score.toFixed(1)}%
              </p>
            </div>
            <StatusBadge passed={doc.passed} />
          </div>

          <div className="mb-4">
            <ScoreDisplay score={doc.score} interval={interval} />
          </div>

          <FailedRulesList rules={doc.failed_rules} />

          {doc.remarks && (
            <p className="text-[13px] text-muted mt-3 italic leading-relaxed">{doc.remarks}</p>
          )}
        </div>
      </div>
    </FlatCard>
  )
}
