import { useState } from 'react'
import type { FailedChecklistItem } from '../types/audit'

interface FailedRulesListProps {
  rules: FailedChecklistItem[]
}

const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 }

export function FailedRulesList({ rules }: FailedRulesListProps) {
  const [open, setOpen] = useState<string | null>(null)
  const sorted = [...rules].sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity])

  if (rules.length === 0) return null

  return (
    <div className="space-y-2">
      <p className="text-[13px] text-muted font-medium">
        {rules.length} failed rule{rules.length > 1 ? 's' : ''}
      </p>
      {sorted.map((r) => {
        const isOpen = open === r.rule_id
        return (
          <div
            key={r.rule_id}
            className="border-[0.5px] border-border rounded-lg overflow-hidden"
          >
            <button
              onClick={() => setOpen(isOpen ? null : r.rule_id)}
              className="w-full flex items-center justify-between px-4 py-2.5 text-left cursor-pointer hover:bg-ink-50 transition-colors"
            >
              <div className="flex items-center gap-2 min-w-0">
                <SeverityDot sev={r.severity} />
                <span className="text-[13px] font-medium text-ink truncate">
                  {r.rule_id}: {r.rule_title}
                </span>
              </div>
              <span className="text-muted text-[13px] shrink-0 ml-2">{isOpen ? '−' : '+'}</span>
            </button>
            {isOpen && (
              <div className="px-4 pb-3 pt-1 border-t-[0.5px] border-border space-y-1.5">
                <p className="text-[13px] text-muted">{r.description}</p>
                {r.evidence && (
                  <p className="text-[13px] text-coral-600 bg-coral-50 rounded-lg px-3 py-1.5">
                    {r.evidence}
                    {r.page_number != null && (
                      <span className="text-muted ml-2">(p. {r.page_number})</span>
                    )}
                  </p>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function SeverityDot({ sev }: { sev: string }) {
  const color =
    sev === 'critical'
      ? 'bg-coral-600'
      : sev === 'high'
        ? 'bg-coral-600/60'
        : sev === 'medium'
          ? 'bg-gray-400'
          : 'bg-gray-400/50'
  return <span className={`w-2 h-2 rounded-full shrink-0 ${color}`} title={sev} />
}
