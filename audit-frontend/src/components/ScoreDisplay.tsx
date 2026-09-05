import type { PredictionInterval } from '../types/audit'

interface ScoreDisplayProps {
  score: number | null
  interval: PredictionInterval | null
  size?: 'normal' | 'large'
}

export function ScoreDisplay({ score, interval, size = 'normal' }: ScoreDisplayProps) {
  const valueSize = size === 'large' ? 'text-[32px]' : 'text-[24px]'

  return (
    <div className="inline-flex flex-col items-start">
      {score === null ? (
        <>
          <span className={`${valueSize} font-medium text-slate-500 leading-none`}>Not audited</span>
          <span className="text-[13px] text-muted mt-1">Classification review required</span>
        </>
      ) : (
        <>
      <span className={`${valueSize} font-medium text-teal-600 leading-none`}>
        {score.toFixed(1)}%
      </span>
      {interval && <span className="text-[13px] text-muted mt-1">
        {interval.lower.toFixed(1)}% – {interval.upper.toFixed(1)}%
      </span>}
        </>
      )}
    </div>
  )
}
