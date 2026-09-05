import type { Contradiction, Severity } from '../types/audit'

const SEV_DOT: Record<Severity, string> = {
  critical: 'bg-coral-600',
  high: 'bg-coral-600/60',
  medium: 'bg-amber-600',
  low: 'bg-gray-400',
}

interface ContradictionListProps {
  contradictions: Contradiction[]
}

/**
 * LLM cross-check contradictions for one document (new_requirements.md §5, §8).
 * These are *advisory*: deterministic validators remain authoritative and are
 * never overturned, so contradictions are framed as review prompts, not FAILs.
 */
export function ContradictionList({ contradictions }: ContradictionListProps) {
  if (!contradictions || contradictions.length === 0) return null

  return (
    <div className="mt-4 space-y-2">
      <p className="text-[13px] text-amber-700 font-medium">
        {contradictions.length} cross-check contradiction{contradictions.length > 1 ? 's' : ''}{' '}
        (advisory)
      </p>
      {contradictions.map((c, i) => (
        <div
          key={`${c.nature}-${i}`}
          className="p-3 rounded-lg bg-amber-50 border-[0.5px] border-amber-600/30"
        >
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`w-2 h-2 rounded-full shrink-0 ${SEV_DOT[c.severity] ?? 'bg-gray-400'}`}
              title={c.severity}
            />
            <span className="text-[12px] font-medium text-amber-700 uppercase">
              {c.nature.replace(/_/g, ' ')}
            </span>
            <span className="text-[11px] text-muted ml-auto">
              confidence {(c.confidence * 100).toFixed(0)}%
            </span>
          </div>
          <p className="text-[13px] text-ink">{c.reason}</p>
          {c.evidence && <p className="text-[12px] text-muted mt-1">Evidence: {c.evidence}</p>}
          {c.conflicting_with && (
            <p className="text-[12px] text-muted mt-0.5">Conflicts with: {c.conflicting_with}</p>
          )}
        </div>
      ))}
    </div>
  )
}
