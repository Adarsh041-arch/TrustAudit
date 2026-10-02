import { useEffect, useState } from 'react'
import { AlertTriangle, FileText, X } from 'lucide-react'
import type { DocumentAuditResult } from '../types/audit'
import type { ReclassifiableDocType } from '../api/api_v2'

const TYPE_OPTIONS: { value: ReclassifiableDocType; label: string }[] = [
  { value: 'invoice', label: 'Invoice' },
  { value: 'purchase_order', label: 'Purchase Order' },
  { value: 'delivery_challan', label: 'Delivery Challan' },
  { value: 'goods_receipt_note', label: 'Goods Receipt Note' },
  { value: 'contract', label: 'Contract' },
  { value: 'letter', label: 'Letter' },
  { value: 'certificate_of_origin', label: 'Certificate of Origin' },
]

interface UnsupportedReviewModalProps {
  documents: DocumentAuditResult[]
  onConfirm: (documentId: string, docType: ReclassifiableDocType) => Promise<void>
  onSkip: (documentId: string) => void
  onClose: () => void
}

export function UnsupportedReviewModal({ documents, onConfirm, onSkip, onClose }: UnsupportedReviewModalProps) {
  const [index, setIndex] = useState(0)
  const [selectedType, setSelectedType] = useState<ReclassifiableDocType>('invoice')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const current = documents[Math.min(index, documents.length - 1)]

  useEffect(() => {
    setSelectedType('invoice')
    setError(null)
  }, [current?.document_id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!current) return null

  const handleConfirm = async () => {
    setSaving(true)
    setError(null)
    try {
      await onConfirm(current.document_id, selectedType)
      if (index + 1 >= documents.length) {
        onClose()
      } else {
        setIndex((i) => i + 1)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reclassify failed')
    } finally {
      setSaving(false)
    }
  }

  const handleSkip = () => {
    onSkip(current.document_id)
    if (index + 1 >= documents.length) {
      onClose()
    } else {
      setIndex((i) => i + 1)
    }
  }

  return (
    <div className="fixed inset-0 z-[120] bg-slate-950/70 backdrop-blur-sm flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Review unsupported document">
      <div className="w-full max-w-2xl rounded-2xl bg-white dark:bg-slate-900 border border-border shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-amber-500/10">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-amber-500/15 text-amber-600 dark:text-amber-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-[15px] font-bold text-ink">Human review needed — unsupported document</h2>
              <p className="text-[12px] text-muted">
                {index + 1} of {documents.length} · the classifier could not assign a type
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-surface-1 text-muted hover:text-ink transition-colors cursor-pointer" aria-label="Close review">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div className="flex items-center gap-2 min-w-0">
            <FileText className="w-4 h-4 text-teal-600 shrink-0" />
            <span className="truncate text-[14px] font-semibold text-ink" title={current.document_name}>
              {current.document_name}
            </span>
          </div>

          {current.preview_base64 ? (
            <div className="rounded-xl overflow-hidden border border-border bg-white flex items-center justify-center max-h-72">
              <img
                src={`data:image/jpeg;base64,${current.preview_base64}`}
                alt={`Preview of ${current.document_name}`}
                className="w-full h-full max-h-72 object-contain"
              />
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border p-6 text-center text-[12px] text-muted">
              No preview available for this document.
            </div>
          )}

          <div>
            <label htmlFor="unsupported-doc-type" className="block text-[12px] font-semibold text-ink mb-1.5">
              What type of document is this?
            </label>
            <select
              id="unsupported-doc-type"
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value as ReclassifiableDocType)}
              className="w-full rounded-xl border border-border bg-surface-1 px-3 py-2.5 text-[13px] text-ink outline-none focus:border-teal-500"
            >
              {TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <p className="text-[11.5px] text-muted mt-1.5">
              Choosing a type re-runs the checks for that type. If the type needs a different
              extraction (e.g. photo → invoice), the document is fully re-read including vision —
              this takes longer. Contracts and letters are fully audited; only documents that still
              match no known type stay unsupported.
            </p>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-600 text-[12.5px]">
              {error}
            </div>
          )}

          <div className="flex items-center justify-between gap-2 pt-1">
            <button
              onClick={handleSkip}
              disabled={saving}
              className="px-4 py-2 rounded-xl text-[13px] font-semibold border border-border bg-surface-1 hover:bg-surface-3 text-muted hover:text-ink transition-all cursor-pointer disabled:opacity-40"
            >
              Skip for now
            </button>
            <button
              onClick={handleConfirm}
              disabled={saving}
              className="px-5 py-2 rounded-xl text-[13px] font-semibold bg-gradient-to-r from-teal-500 to-emerald-600 text-white disabled:opacity-40 shadow-md active:scale-95 transition-all cursor-pointer"
            >
              {saving ? 'Re-auditing…' : 'Confirm type & re-audit'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
