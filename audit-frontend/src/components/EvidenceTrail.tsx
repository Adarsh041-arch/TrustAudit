import { useState } from 'react'
import type { EvidenceNature, PipelineEvidence } from '../types/audit'

const NATURE_LABEL: Record<EvidenceNature, string> = {
  metadata: 'Metadata',
  extracted_fields: 'Extracted Fields',
  arithmetic_computation: 'Arithmetic',
  vlm_observations: 'VLM',
  'ocr+regex_observations': 'OCR / Regex',
}

interface EvidenceTrailProps {
  evidences: PipelineEvidence[]
}

/**
 * The ordered, provenance-tagged evidence trail for one document
 * (new_requirements.md §5, §8). Each row shows the evidence nature + source and
 * a summary; expanding reveals the raw structured payload the pipeline recorded.
 */
export function EvidenceTrail({ evidences }: EvidenceTrailProps) {
  const [open, setOpen] = useState<string | null>(null)
  if (!evidences || evidences.length === 0) return null

  return (
    <div className="mt-4 space-y-2">
      <p className="text-[13px] text-muted font-medium">Evidence trail ({evidences.length})</p>
      {evidences.map((e) => {
        const isOpen = open === e.evidence_id
        return (
          <div
            key={e.evidence_id}
            className="border-[0.5px] border-border rounded-lg overflow-hidden"
          >
            <button
              onClick={() => setOpen(isOpen ? null : e.evidence_id)}
              className="w-full flex items-center justify-between px-4 py-2.5 text-left cursor-pointer hover:bg-ink-50 transition-colors"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-teal-50 text-teal-600 border-[0.5px] border-teal-600/30 shrink-0">
                  {NATURE_LABEL[e.nature] ?? e.nature}
                </span>
                <span className="text-[12px] font-mono text-muted shrink-0">{e.source}</span>
                <span className="text-[13px] text-ink truncate">{e.summary}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-2">
                {e.page != null && <span className="text-[11px] text-muted">p.{e.page}</span>}
                <span className="text-muted text-[13px]">{isOpen ? '−' : '+'}</span>
              </div>
            </button>
            {isOpen && (
              <div className="px-4 pb-3 pt-1 border-t-[0.5px] border-border">
                <pre className="text-[12px] text-ink bg-surface-1 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-words">
                  {JSON.stringify(e.payload, null, 2)}
                </pre>
                <div className="text-[11px] text-muted mt-1.5">
                  confidence {(e.confidence * 100).toFixed(0)}%
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
