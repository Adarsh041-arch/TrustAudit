import type { PredictionInterval } from '../types/audit'

interface ScoreDisplayProps {
  score: number
  interval: PredictionInterval
  size?: 'normal' | 'large'
}

export function ScoreDisplay({ score, interval, size = 'normal' }: ScoreDisplayProps) {
  const valueSize = size === 'large' ? 'text-[32px]' : 'text-[24px]'

  return (
    <div className="inline-flex flex-col items-start">
      <span className={`${valueSize} font-medium text-teal-600 leading-none`}>
        {score.toFixed(1)}%
      </span>
      <span className="text-[13px] text-muted mt-1">
        {interval.lower.toFixed(1)}% – {interval.upper.toFixed(1)}%
      </span>
    </div>
  )
}
