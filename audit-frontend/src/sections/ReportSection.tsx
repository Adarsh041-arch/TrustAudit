import type { FinalAuditReport, PredictionInterval } from '../types/audit'
import { FlatCard } from '../components/FlatCard'
import { ScoreDisplay } from '../components/ScoreDisplay'
import { StatusBadge } from '../components/StatusBadge'

interface ReportSectionProps {
  report: FinalAuditReport
  interval: PredictionInterval
}

export function ReportSection({ report, interval }: ReportSectionProps) {
  const resultLabel =
    report.overall_result === 'PASS'
      ? 'Passed'
      : report.overall_result === 'REVIEW REQUIRED'
        ? 'Review required'
        : 'Failed'

  return (
    <FlatCard>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-[18px] font-medium text-ink">Audit Summary</h2>
          <p className="text-[13px] text-muted mt-0.5">{report.audit_title}</p>
        </div>
        <StatusBadge passed={report.overall_result === 'PASS'} label={resultLabel} />
      </div>

      <div className="flex items-center gap-6 mb-4">
        <ScoreDisplay score={report.overall_score} interval={interval} size="large" />
        <div className="text-[13px] text-muted space-y-0.5">
          <p>
            {report.documents_processed} document
            {report.documents_processed !== 1 ? 's' : ''} processed
          </p>
          <p>
            {report.documents_passed} passed, {report.documents_failed} failed
          </p>
        </div>
      </div>

      <div className="border-t-[0.5px] border-border pt-3">
        <p className="text-body text-ink leading-relaxed">{report.summary}</p>
      </div>
    </FlatCard>
  )
}
