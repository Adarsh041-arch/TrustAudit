import type { ReactNode } from 'react'

interface FlatCardProps {
  children: ReactNode
  className?: string
}

export function FlatCard({ children, className = '' }: FlatCardProps) {
  return (
    <div
      className={`bg-surface-2 border-[0.5px] border-border rounded-xl p-5 ${className}`}
    >
      {children}
    </div>
  )
}
