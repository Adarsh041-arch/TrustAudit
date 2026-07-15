interface MetricCardProps {
  label: string
  value: string | number
  color?: 'teal' | 'coral' | 'ink'
}

export function MetricCard({ label, value, color = 'ink' }: MetricCardProps) {
  const colorClass =
    color === 'teal' ? 'text-teal-600' : color === 'coral' ? 'text-coral-600' : 'text-ink'

  return (
    <div className="bg-surface-1 rounded-lg p-4">
      <p className="text-[13px] text-muted mb-1">{label}</p>
      <p className={`text-[24px] font-medium ${colorClass}`}>{value}</p>
    </div>
  )
}
