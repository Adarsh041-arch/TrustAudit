import React from 'react'

interface VlmStatusBadgeProps {
  isVlm: boolean
  extractorVersion?: string
}

export const VlmStatusBadge: React.FC<VlmStatusBadgeProps> = ({ isVlm, extractorVersion }) => {
  if (isVlm) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/30 shadow-sm animate-pulse">
        <span className="w-2 h-2 rounded-full bg-purple-400"></span>
        VLM Vision AI ({extractorVersion || 'vlm_1.0.0'})
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 shadow-sm">
      <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
      Deterministic Text Layer ({extractorVersion || 'regex_1.0.0'})
    </span>
  )
}
