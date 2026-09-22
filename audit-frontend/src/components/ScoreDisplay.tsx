import type { PredictionInterval, DocumentAuditResult } from '../types/audit'
import { formatDocumentScore } from '../utils/documentStatus'

interface ScoreDisplayProps {
  score?: number | null
  interval?: PredictionInterval | null
  size?: 'normal' | 'large'
  doc?: Partial<DocumentAuditResult> | null
}

export function ScoreDisplay({ score, interval, size = 'normal', doc }: ScoreDisplayProps) {
  const valueSize = size === 'large' ? 'text-[32px]' : 'text-[24px]'
  const formatted = formatDocumentScore(doc ?? { score })

  return (
    <div className="inline-flex flex-col items-start">
      <span className={`${valueSize} font-bold ${formatted.colorClass} leading-none font-mono`}>
        {formatted.value}
      </span>
      <span className="text-[12px] text-muted mt-1 font-medium">
        {interval && formatted.isNumeric
          ? `${interval.lower.toFixed(1)}% – ${interval.upper.toFixed(1)}% CI`
          : formatted.label}
      </span>
    </div>
  )
}
