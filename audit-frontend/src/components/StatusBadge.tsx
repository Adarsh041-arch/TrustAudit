interface StatusBadgeProps {
  passed: boolean
  label?: string
  status?: 'READY' | 'INCOMPLETE' | 'PENDING' | 'FAILED' | 'UNSUPPORTED'
}

export function StatusBadge({ passed, label, status }: StatusBadgeProps) {
  const text = label ?? (status && status !== 'READY' ? status.replace('_', ' ') : passed ? 'Pass' : 'Fail')
  const bg = status === 'INCOMPLETE' || status === 'PENDING'
    ? 'bg-amber-50 text-amber-700 border border-amber-600/20'
    : status === 'UNSUPPORTED'
      ? 'bg-slate-100 text-slate-600 border border-slate-300'
    : passed
      ? 'bg-teal-50 text-teal-600'
      : 'bg-coral-50 text-coral-600'

  return (
    <span className={`inline-block ${bg} rounded-lg px-3 py-1 text-[13px] font-medium`}>
      {text}
    </span>
  )
}
