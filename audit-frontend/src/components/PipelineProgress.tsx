import type { PipelineStepName, StepStatusName } from '../types/audit'
import { Check, Loader2, AlertCircle, Minus, Sparkles } from 'lucide-react'

/** Per-document progress accumulated from the SSE `step` events. */
export interface DocProgress {
  document_id: string
  filename: string
  steps: Partial<Record<PipelineStepName, StepStatusName>>
}

const STEP_ORDER: { key: PipelineStepName; label: string }[] = [
  { key: 'received', label: 'Received' },
  { key: 'classify', label: 'Classify' },
  { key: 'extract_regex', label: 'Regex' },
  { key: 'extract_ocr', label: 'OCR' },
  { key: 'extract_vlm', label: 'VLM' },
  { key: 'vlm_selfcheck', label: 'Self-check' },
  { key: 'arithmetic', label: 'Arithmetic' },
  { key: 'cross_check', label: 'Cross-check' },
  { key: 'score', label: 'Score' },
  { key: 'done', label: 'Done' },
]

interface PipelineProgressProps {
  docs: DocProgress[]
}

export function PipelineProgress({ docs }: PipelineProgressProps) {
  if (docs.length === 0) return null

  return (
    <div className="mt-5 space-y-3.5">
      <div className="flex items-center justify-between text-[12px] text-muted font-medium">
        <span className="flex items-center gap-1.5 text-teal-600 dark:text-teal-400">
          <Sparkles className="w-3.5 h-3.5" />
          Real-Time Streaming Audit Pipeline (SSE)
        </span>
        <span>{docs.length} document stream(s) active</span>
      </div>

      {docs.map((d) => {
        const completedCount = STEP_ORDER.filter((s) => d.steps[s.key] === 'ok').length
        const totalVisible = STEP_ORDER.length
        const progressPct = Math.round((completedCount / totalVisible) * 100)

        return (
          <div
            key={d.document_id}
            className="p-4 rounded-xl bg-surface-2 border border-border shadow-xs hover:border-border-bright transition-all"
          >
            <div className="flex items-center justify-between gap-3 mb-2.5">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-[13.5px] font-semibold text-ink truncate">{d.filename}</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-surface-1 border border-border text-muted">
                  {d.document_id}
                </span>
              </div>
              <span className="text-[12px] font-mono font-medium text-teal-600 dark:text-teal-400 shrink-0">
                {progressPct}%
              </span>
            </div>

            {/* Micro progress bar */}
            <div className="w-full bg-surface-1 h-1.5 rounded-full overflow-hidden mb-3 border border-border/40">
              <div
                className="bg-gradient-to-r from-teal-500 to-emerald-500 h-full transition-all duration-300 rounded-full"
                style={{ width: `${Math.max(progressPct, 5)}%` }}
              />
            </div>

            <div className="flex flex-wrap gap-1.5">
              {STEP_ORDER.map((s) => (
                <StepChip key={s.key} label={s.label} status={d.steps[s.key]} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function StepChip({ label, status }: { label: string; status?: StepStatusName }) {
  const getBadgeStyle = () => {
    switch (status) {
      case 'ok':
        return {
          cls: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30 font-medium',
          icon: <Check className="w-2.5 h-2.5 stroke-[3]" />,
        }
      case 'start':
        return {
          cls: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/40 animate-pulse font-medium',
          icon: <Loader2 className="w-2.5 h-2.5 animate-spin" />,
        }
      case 'error':
        return {
          cls: 'bg-coral-500/15 text-coral-600 dark:text-coral-400 border-coral-500/40 font-medium',
          icon: <AlertCircle className="w-2.5 h-2.5" />,
        }
      case 'skip':
        return {
          cls: 'bg-surface-1 text-muted/60 border-border/60',
          icon: <Minus className="w-2.5 h-2.5" />,
        }
      default:
        return {
          cls: 'bg-surface-1/60 text-muted/40 border-border/40',
          icon: <span className="w-1.5 h-1.5 rounded-full bg-muted/30" />,
        }
    }
  }

  const { cls, icon } = getBadgeStyle()

  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] border transition-all ${cls}`}
      title={status ?? 'pending'}
    >
      {icon}
      <span>{label}</span>
    </span>
  )
}
