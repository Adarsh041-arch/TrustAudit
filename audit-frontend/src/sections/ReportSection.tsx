import { useState } from 'react'
import { downloadReportV2 } from '../api/api_v2'
import type { DocumentAuditResult } from '../types/audit'
import { FlatCard } from '../components/FlatCard'

interface ReportSectionProps {
  documents: DocumentAuditResult[]
  findings: any[]
}

export function ReportSection({ documents, findings }: ReportSectionProps) {
  const [busy, setBusy] = useState<'docx' | 'pdf' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleDownload(format: 'docx' | 'pdf') {
    try {
      setBusy(format)
      const blob = await downloadReportV2(format, documents, findings)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `TrustAudit_Report.${format}`
      a.click()
      URL.revokeObjectURL(url)
      setError(null)
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <FlatCard>
        <h3 className="text-[16px] font-medium text-ink mb-2">Download DOCX</h3>
        <p className="text-[13px] text-muted mb-4">
          Word report with executive summary, per-document scores, risk levels and failed-rule tables.
        </p>
        <button
          onClick={() => handleDownload('docx')}
          disabled={busy !== null || documents.length === 0}
          className="px-4 py-2 rounded-lg text-[13px] font-medium border-[0.5px] border-teal-600 text-teal-600 bg-transparent hover:bg-teal-50 disabled:opacity-40 disabled:pointer-events-none transition-colors cursor-pointer"
        >
          {busy === 'docx' ? 'Generating\u2026' : 'Download DOCX'}
        </button>
      </FlatCard>
      <FlatCard>
        <h3 className="text-[16px] font-medium text-ink mb-2">Download PDF</h3>
        <p className="text-[13px] text-muted mb-4">
          Portable PDF report with color-coded severity tables.
        </p>
        <button
          onClick={() => handleDownload('pdf')}
          disabled={busy !== null || documents.length === 0}
          className="px-4 py-2 rounded-lg text-[13px] font-medium border-[0.5px] border-coral-600 text-coral-600 bg-transparent hover:bg-coral-50 disabled:opacity-40 disabled:pointer-events-none transition-colors cursor-pointer"
        >
          {busy === 'pdf' ? 'Generating\u2026' : 'Download PDF'}
        </button>
      </FlatCard>
      {error && <p className="text-[13px] text-coral-600 md:col-span-2">{error}</p>}
      {documents.length === 0 && (
        <p className="text-[13px] text-muted md:col-span-2">
          Upload documents first; reports are generated from the current session's accumulated results.
        </p>
      )}
    </div>
  )
}