import { useEffect, useState } from 'react'
import { fetchEvalV2 } from '../api/api_v2'
import type { EvalResponse } from '../api/api_v2'
import { FlatCard } from '../components/FlatCard'

interface SettingsSectionProps {
  threshold: number
  onThresholdChange: (t: number) => void
}

const METRIC_LABELS: [keyof NonNullable<EvalResponse['metrics']>, string][] = [
  ['accuracy', 'Accuracy'],
  ['precision', 'Precision'],
  ['recall', 'Recall'],
  ['f1_score', 'F1 Score'],
  ['false_positive_rate', 'False Positive Rate'],
  ['false_negative_rate', 'False Negative Rate'],
  ['average_latency_seconds', 'Avg Latency (s)'],
  ['average_confidence_score', 'Avg Confidence'],
]

export function SettingsSection({ threshold, onThresholdChange }: SettingsSectionProps) {
  const [evalData, setEvalData] = useState<EvalResponse | null>(null)

  useEffect(() => {
    fetchEvalV2()
      .then(setEvalData)
      .catch(() => setEvalData(null))
  }, [])

  return (
    <div className="space-y-4">
      <FlatCard>
        <h3 className="text-[16px] font-medium text-ink mb-2">Confidence Threshold</h3>
        <p className="text-[13px] text-muted mb-4">
          Documents scoring below this threshold show the "Human review recommended" badge in the inspector.
        </p>
        <div className="flex items-center gap-4">
          <input
            type="range"
            min={50}
            max={95}
            step={1}
            value={threshold}
            onChange={(e) => onThresholdChange(Number(e.target.value))}
            className="flex-1 accent-teal-600"
          />
          <span className="text-[18px] font-medium text-teal-600 w-12 text-right">{threshold}%</span>
        </div>
      </FlatCard>

      <FlatCard>
        <h3 className="text-[16px] font-medium text-ink mb-4">Evaluation Framework (golden-set baselines)</h3>
        {!evalData?.metrics ? (
          <p className="text-[13px] text-muted py-4">
            No baseline data available. Run the golden-set harness (evaluation/measure_v2.py) to populate.
          </p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {METRIC_LABELS.map(([key, label]) => {
              const v = evalData.metrics![key]
              return (
                <div key={key} className="p-3 rounded-lg bg-surface-1 border-[0.5px] border-border">
                  <div className="text-[11px] text-muted uppercase font-medium">{label}</div>
                  <div className="text-[18px] font-medium text-ink mt-1">
                    {v === null ? '\u2014' : key.startsWith('average_') ? String(v) : `${(v * 100).toFixed(1)}%`}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </FlatCard>
    </div>
  )
}