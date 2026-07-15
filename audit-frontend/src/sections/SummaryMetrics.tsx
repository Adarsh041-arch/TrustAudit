import type { FinalAuditReport } from '../types/audit'
import { MetricCard } from '../components/MetricCard'

interface SummaryMetricsProps {
  report: FinalAuditReport
}

export function SummaryMetrics({ report }: SummaryMetricsProps) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <MetricCard label="Documents processed" value={report.documents_processed} />
      <MetricCard label="Passed" value={report.documents_passed} color="teal" />
      <MetricCard label="Failed" value={report.documents_failed} color="coral" />
      <MetricCard
        label="Overall score"
        value={`${report.overall_score.toFixed(1)}%`}
        color="teal"
      />
    </div>
  )
}
