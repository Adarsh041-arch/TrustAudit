import type { ReactNode } from 'react'

interface FlatCardProps {
  children: ReactNode
  className?: string
  title?: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  glow?: 'teal' | 'coral' | 'blue' | 'none'
}

export function FlatCard({
  children,
  className = '',
  title,
  subtitle,
  action,
  glow = 'none',
}: FlatCardProps) {
  const glowClass =
    glow === 'teal'
      ? 'border-teal-500/40 shadow-lg shadow-teal-500/5'
      : glow === 'coral'
        ? 'border-coral-500/40 shadow-lg shadow-coral-500/5'
        : glow === 'blue'
          ? 'border-blue-500/40 shadow-lg shadow-blue-500/5'
          : 'border-border/90'

  return (
    <div
      className={`bg-surface-2/90 border rounded-2xl p-5 md:p-6 shadow-sm transition-all duration-200 ${glowClass} ${className}`}
    >
      {(title || action) && (
        <div className="flex items-start justify-between gap-3 mb-4 pb-3 border-b border-border/60">
          <div>
            {typeof title === 'string' ? (
              <h3 className="text-[17px] font-semibold text-ink tracking-tight">{title}</h3>
            ) : (
              title
            )}
            {subtitle && (
              <p className="text-[12.5px] text-muted mt-0.5 leading-relaxed">{subtitle}</p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      {children}
    </div>
  )
}
