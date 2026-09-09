import type { ReactNode } from 'react'

interface MetricCardProps {
  label: string
  value: string | number
  color?: 'teal' | 'coral' | 'blue' | 'amber' | 'ink'
  subtext?: string
  icon?: ReactNode
  trend?: string
}

export function MetricCard({
  label,
  value,
  color = 'ink',
  subtext,
  icon,
  trend,
}: MetricCardProps) {
  const colorMap = {
    teal: {
      text: 'text-teal-600 dark:text-teal-400',
      bg: 'bg-teal-500/10 dark:bg-teal-500/15',
      border: 'border-teal-500/20',
      iconColor: 'text-teal-600 dark:text-teal-400',
    },
    coral: {
      text: 'text-coral-600 dark:text-coral-400',
      bg: 'bg-coral-500/10 dark:bg-coral-500/15',
      border: 'border-coral-500/20',
      iconColor: 'text-coral-600 dark:text-coral-400',
    },
    blue: {
      text: 'text-blue-600 dark:text-blue-400',
      bg: 'bg-blue-500/10 dark:bg-blue-500/15',
      border: 'border-blue-500/20',
      iconColor: 'text-blue-600 dark:text-blue-400',
    },
    amber: {
      text: 'text-amber-600 dark:text-amber-400',
      bg: 'bg-amber-500/10 dark:bg-amber-500/15',
      border: 'border-amber-500/20',
      iconColor: 'text-amber-600 dark:text-amber-400',
    },
    ink: {
      text: 'text-ink',
      bg: 'bg-surface-1',
      border: 'border-border/80',
      iconColor: 'text-muted',
    },
  }

  const theme = colorMap[color] || colorMap.ink

  return (
    <div
      className={`rounded-xl p-4 border bg-surface-2 shadow-xs transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 ${theme.border}`}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-[12px] font-medium text-muted uppercase tracking-wider truncate">
          {label}
        </span>
        {icon && (
          <div className={`p-1.5 rounded-lg ${theme.bg} ${theme.iconColor} shrink-0`}>
            {icon}
          </div>
        )}
      </div>

      <div className="flex items-baseline gap-2">
        <span className={`text-[26px] font-bold tracking-tight font-mono ${theme.text}`}>
          {value}
        </span>
        {trend && (
          <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">
            {trend}
          </span>
        )}
      </div>

      {subtext && <p className="text-[11px] text-muted mt-1 truncate">{subtext}</p>}
    </div>
  )
}
