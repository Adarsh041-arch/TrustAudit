import React from 'react'
import type { ExtractionMode } from '../api/api_v2'

interface VlmStatusBadgeProps {
  mode: ExtractionMode
  extractorVersion?: string
}

const MODE_STYLES: Record<ExtractionMode, { label: string; cls: string }> = {
  dual: {
    label: 'Dual Extraction (Regex + VLM)',
    cls: 'bg-violet-50 text-violet-600 border-violet-600/30',
  },
  vlm_text: {
    label: 'VLM Text Extraction',
    cls: 'bg-blue-50 text-blue-600 border-blue-600/30',
  },
  vlm: {
    label: 'VLM Vision AI',
    cls: 'bg-blue-50 text-blue-600 border-blue-600/30',
  },
  regex: {
    label: 'Deterministic Text Layer',
    cls: 'bg-teal-50 text-teal-600 border-teal-600/30',
  },
}

export const VlmStatusBadge: React.FC<VlmStatusBadgeProps> = ({ mode, extractorVersion }) => {
  const { label, cls } = MODE_STYLES[mode]
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-[13px] font-medium border-[0.5px] ${cls}`}>
      <span className="w-2 h-2 rounded-full bg-current"></span>
      {label}
      {extractorVersion && <span className="opacity-70">({extractorVersion})</span>}
    </span>
  )
}
