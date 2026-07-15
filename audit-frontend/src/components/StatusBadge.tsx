interface StatusBadgeProps {
  passed: boolean
  label?: string
}

export function StatusBadge({ passed, label }: StatusBadgeProps) {
  const text = label ?? (passed ? 'Pass' : 'Fail')
  const bg = passed ? 'bg-teal-50 text-teal-600' : 'bg-coral-50 text-coral-600'

  return (
    <span className={`inline-block ${bg} rounded-lg px-3 py-1 text-[13px] font-medium`}>
      {text}
    </span>
  )
}
