import { useEffect, useState } from 'react'
import {
  Sliders,
  Award,
  Cpu,
  RefreshCw
} from 'lucide-react'
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
  const [loading, setLoading] = useState(false)
  const [accessToken, setAccessToken] = useState('')

  useEffect(() => {
    loadEval()
  }, [])

  function loadEval() {
    setLoading(true)
    fetchEvalV2()
      .then(setEvalData)
      .catch(() => setEvalData(null))
      .finally(() => setLoading(false))
  }

  return (
    <div className="space-y-6">
      <FlatCard>
        <h3 className="text-[17px] font-bold text-ink">Workspace connection</h3>
        <p className="text-sm text-muted my-2">For a hosted workspace, enter the access token issued by your administrator. It is kept for this browser session.</p>
        <label className="text-sm text-ink" htmlFor="workspace-token">Access token</label>
        <input id="workspace-token" type="password" autoComplete="off" value={accessToken} onChange={e => setAccessToken(e.target.value)} className="block w-full border border-border rounded-lg p-2 my-2 bg-surface-1" />
        <button className="v2-primary" disabled={!accessToken.trim()} onClick={() => { sessionStorage.setItem('audit_access_token', accessToken.trim()); window.location.reload() }}>Connect workspace</button>
        <button className="v2-text-button mt-3" onClick={() => { sessionStorage.removeItem('audit_access_token'); window.location.reload() }}>Clear connection</button>
      </FlatCard>
      {/* Display preference; the server owns clearance policy. */}
      <FlatCard glow="teal">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2.5 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-[17px] font-bold text-ink">
                Review display preference
              </h3>
              <p className="text-[12.5px] text-muted">
                This local preference does not change audit decisions. Required checks and missing evidence determine clearance on the server.
              </p>
            </div>
          </div>
          <span className="text-[24px] font-mono font-bold text-teal-600 dark:text-teal-400 px-3 py-1 rounded-xl bg-teal-500/10 border border-teal-500/20">
            {threshold}%
          </span>
        </div>

        <div className="space-y-3 pt-2">
          <input
            type="range"
            min={50}
            max={95}
            step={1}
            value={threshold}
            onChange={(e) => onThresholdChange(Number(e.target.value))}
            className="w-full h-2.5 bg-surface-1 rounded-lg appearance-none cursor-pointer accent-teal-600"
          />
          <div className="flex justify-between text-[11px] text-muted font-mono">
            <span>50 (Lower score)</span>
            <span className="font-bold text-teal-600 dark:text-teal-400">75 (Default)</span>
            <span>95 (Higher score)</span>
          </div>
        </div>
      </FlatCard>

      {/* Golden Set Benchmarks */}
      <FlatCard>
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-border/60">
          <div className="flex items-center gap-2.5">
            <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400">
              <Award className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-[17px] font-bold text-ink">
                Golden-Set Benchmark Evaluation (Precision & Recall)
              </h3>
              <p className="text-[12.5px] text-muted">
                Saved fixture evaluation results. These do not establish accuracy on your production documents.
              </p>
            </div>
          </div>

          <button
            onClick={loadEval}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[12px] font-semibold border border-border bg-surface-1 hover:bg-surface-3 text-ink transition-all cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {!evalData?.metrics ? (
          <div className="p-6 rounded-xl bg-surface-1 border border-border text-center">
            <p className="text-[13px] text-muted">
              No live evaluation harness results detected yet. Run{' '}
              <code className="px-2 py-0.5 rounded font-mono text-[12px] bg-surface-2 text-teal-600">
                python evaluation/measure_v2.py
              </code>{' '}
              to compute baselines against the candidate golden set.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
            {METRIC_LABELS.map(([key, label]) => {
              const v = evalData.metrics![key]
              return (
                <div
                  key={key}
                  className="p-4 rounded-xl bg-surface-1 border border-border hover:border-border-bright transition-all"
                >
                  <span className="text-[11px] font-bold uppercase tracking-wider text-muted block truncate">
                    {label}
                  </span>
                  <div className="text-[20px] font-mono font-bold text-ink mt-1">
                    {v === null
                      ? '—'
                      : key.startsWith('average_')
                        ? String(v)
                        : `${(v * 100).toFixed(1)}%`}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </FlatCard>

      {/* Engine Architecture & Runtime Settings */}
      <FlatCard>
        <div className="flex items-center gap-2.5 mb-3">
          <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-[16px] font-bold text-ink">Engine Architecture Specifications</h3>
            <p className="text-[12px] text-muted">V2 Deterministic Pipeline Parameters</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 text-[12.5px] mt-4">
          <div className="p-3.5 rounded-xl bg-surface-1 border border-border">
            <span className="text-muted text-[11px] font-medium block">Orchestrator</span>
            <span className="text-ink font-semibold mt-0.5 block">Temporal Workflow Engine</span>
          </div>
          <div className="p-3.5 rounded-xl bg-surface-1 border border-border">
            <span className="text-muted text-[11px] font-medium block">Dual Extraction Mode</span>
            <span className="text-ink font-semibold mt-0.5 block">Deterministic Regex + Vision VLM</span>
          </div>
          <div className="p-3.5 rounded-xl bg-surface-1 border border-border">
            <span className="text-muted text-[11px] font-medium block">Audit Governance</span>
            <span className="text-ink font-semibold mt-0.5 block">SHA-256 Hash Chain Protocol</span>
          </div>
        </div>
      </FlatCard>
    </div>
  )
}