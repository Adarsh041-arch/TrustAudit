import type { PipelineStepName, StepStatusName } from '../types/audit'

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

/**
 * Live per-document pipeline progress (new_requirements.md §6). Renders one row
 * per document, each with the ordered pipeline steps coloured by their latest
 * streamed status. Steps that never arrive stay faint (e.g. VLM/cross-check are
 * skipped when no API key is configured).
 */
export function PipelineProgress({ docs }: PipelineProgressProps) {
  if (docs.length === 0) return null
  return (
    <div className="mt-4 space-y-3">
      {docs.map((d) => (
        <div
          key={d.document_id}
          className="p-3 rounded-lg bg-surface-1 border-[0.5px] border-border"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[13px] font-medium text-ink truncate mr-2">{d.filename}</span>
            <span className="text-[11px] text-muted font-mono shrink-0">{d.document_id}</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {STEP_ORDER.map((s) => (
              <StepChip key={s.key} label={s.label} status={d.steps[s.key]} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function StepChip({ label, status }: { label: string; status?: StepStatusName }) {
  const cls =
    status === 'ok'
      ? 'bg-teal-50 text-teal-600 border-teal-600/30'
      : status === 'start'
        ? 'bg-amber-50 text-amber-700 border-amber-600/30 animate-pulse'
        : status === 'skip'
          ? 'bg-surface-2 text-muted border-border'
          : status === 'error'
            ? 'bg-coral-50 text-coral-600 border-coral-600/30'
            : 'bg-surface-2 text-muted/40 border-border'

  const mark =
    status === 'ok'
      ? '✓'
      : status === 'error'
        ? '✕'
        : status === 'skip'
          ? '–'
          : status === 'start'
            ? '⟳'
            : '·'

  return (
    <span
      className={`px-2 py-0.5 rounded-md text-[11px] font-medium border-[0.5px] ${cls}`}
      title={status ?? 'pending'}
    >
      <span className="mr-1">{mark}</span>
      {label}
    </span>
  )
}
