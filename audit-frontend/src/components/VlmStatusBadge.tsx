import React from 'react'

interface VlmStatusBadgeProps {
  isVlm: boolean
  extractorVersion?: string
}

export const VlmStatusBadge: React.FC<VlmStatusBadgeProps> = ({ isVlm, extractorVersion }) => {
  if (isVlm) {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-[13px] font-medium bg-blue-50 text-blue-600 border-[0.5px] border-blue-600/30">
        <span className="w-2 h-2 rounded-full bg-blue-600"></span>
        VLM Vision AI ({extractorVersion || 'vlm_1.0.0'})
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-[13px] font-medium bg-teal-50 text-teal-600 border-[0.5px] border-teal-600/30">
      <span className="w-2 h-2 rounded-full bg-teal-600"></span>
      Deterministic Text Layer ({extractorVersion || 'regex_1.0.0'})
    </span>
  )
}
