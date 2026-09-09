import { useState } from 'react'
import { FileText, Download, Loader2, CheckCircle2, FileSpreadsheet, Sparkles } from 'lucide-react'
import { downloadReportV2 } from '../api/api_v2'
import type { DocumentAuditResult } from '../types/audit'
import { FlatCard } from '../components/FlatCard'

interface ReportSectionProps {
  documents: DocumentAuditResult[]
  findings: any[]
  executiveSummary?: string
}

export function ReportSection({ documents, findings, executiveSummary = '' }: ReportSectionProps) {
  const [busy, setBusy] = useState<'docx' | 'pdf' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [successFormat, setSuccessFormat] = useState<'docx' | 'pdf' | null>(null)

  async function handleDownload(format: 'docx' | 'pdf') {
    try {
      setBusy(format)
      setError(null)
      const blob = await downloadReportV2(
        format,
        documents,
        findings,
        'TrustAudit Forensic Evaluation Report',
        executiveSummary
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `TrustAudit_Report_${new Date().toISOString().slice(0, 10)}.${format}`
      a.click()
      URL.revokeObjectURL(url)
      setSuccessFormat(format)
      setTimeout(() => setSuccessFormat(null), 3500)
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      {/* Scope summary */}
      <FlatCard>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400">
                <Sparkles className="w-5 h-5" />
              </div>
              <h2 className="text-[18px] font-bold text-ink">
                Executive Forensic Audit Reports
              </h2>
            </div>
            <p className="text-[12.5px] text-muted mt-1 max-w-2xl">
              Export formal audit dossiers complete with executive summary, mathematical triangulation,
              failed-rule citations, and cryptographic ledger proofs.
            </p>
          </div>

          <div className="flex items-center gap-2 self-stretch sm:self-auto bg-surface-1 p-2.5 rounded-xl border border-border text-[12px]">
            <span className="font-mono font-bold text-ink">{documents.length}</span>
            <span className="text-muted">Documents</span>
            <span className="text-border-bright">•</span>
            <span className="font-mono font-bold text-coral-600">{findings.length}</span>
            <span className="text-muted">Findings</span>
          </div>
        </div>
      </FlatCard>

      {successFormat && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300 text-[13px] flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4" />
          <span>Successfully generated and downloaded {successFormat.toUpperCase()} audit report!</span>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-coral-500/10 border border-coral-500/30 text-coral-600 text-[13px]">
          {error}
        </div>
      )}

      {/* Export Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <FlatCard glow="teal">
          <div className="flex items-start gap-3.5 mb-3">
            <div className="p-3 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-[16.5px] font-bold text-ink">Microsoft Word Dossier (.docx)</h3>
              <p className="text-[12.5px] text-muted mt-0.5">
                Formatted Word document with editable tables, full evidence transcripts, and executive notes.
              </p>
            </div>
          </div>

          <div className="mt-5 pt-4 border-t border-border/60 flex items-center justify-between">
            <span className="text-[11.5px] text-muted font-mono">Format: .docx (Office Open XML)</span>
            <button
              onClick={() => handleDownload('docx')}
              disabled={busy !== null || documents.length === 0}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[13px] font-semibold bg-gradient-to-r from-teal-500 to-emerald-600 hover:from-teal-600 hover:to-emerald-700 text-white disabled:opacity-40 shadow-xs cursor-pointer active:scale-95 transition-all"
            >
              {busy === 'docx' ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Compiling Dossier…
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" /> Download DOCX
                </>
              )}
            </button>
          </div>
        </FlatCard>

        <FlatCard glow="coral">
          <div className="flex items-start gap-3.5 mb-3">
            <div className="p-3 rounded-xl bg-coral-500/10 text-coral-600 dark:text-coral-400">
              <FileSpreadsheet className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-[16.5px] font-bold text-ink">Portable Audit Report (.pdf)</h3>
              <p className="text-[12.5px] text-muted mt-0.5">
                Standardized immutable PDF with color-coded severity matrix, charts, and signatures.
              </p>
            </div>
          </div>

          <div className="mt-5 pt-4 border-t border-border/60 flex items-center justify-between">
            <span className="text-[11.5px] text-muted font-mono">Format: .pdf (Vector & Tables)</span>
            <button
              onClick={() => handleDownload('pdf')}
              disabled={busy !== null || documents.length === 0}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[13px] font-semibold bg-gradient-to-r from-coral-500 to-amber-600 hover:from-coral-600 hover:to-amber-700 text-white disabled:opacity-40 shadow-xs cursor-pointer active:scale-95 transition-all"
            >
              {busy === 'pdf' ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Rendering PDF…
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" /> Download PDF
                </>
              )}
            </button>
          </div>
        </FlatCard>
      </div>

      {documents.length === 0 && (
        <div className="p-4 rounded-xl bg-surface-1 border border-border text-center text-[13px] text-muted">
          Ingest documents or load the sample dossier to enable report compilation.
        </div>
      )}
    </div>
  )
}
