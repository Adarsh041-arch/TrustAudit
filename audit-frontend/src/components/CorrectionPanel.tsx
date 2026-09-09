import { useState } from 'react'
import { apiFetch } from '../api/http'
import { V2_BASE } from '../api/api_v2'

export function CorrectionPanel({ documentId, pageCount }: { documentId: string; pageCount: number }) {
  const [revision, setRevision] = useState<string | null>(null)
  const [field, setField] = useState('header.grand_total')
  const [value, setValue] = useState('')
  const [quote, setQuote] = useState('')
  const [reason, setReason] = useState('')
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function load() {
    setBusy(true)
    try {
      const response = await apiFetch(`${V2_BASE}/documents/${encodeURIComponent(documentId)}/revision`)
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Could not load current revision')
      setRevision(body.revision)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not load revision') }
    finally { setBusy(false) }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const response = await apiFetch(`${V2_BASE}/documents/${encodeURIComponent(documentId)}/corrections`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: revision, reason,
          changes: [{ path: field, value, page, source_quote: quote }] }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Correction could not be saved')
      window.location.reload()
    } catch (err) { setError(err instanceof Error ? err.message : 'Correction failed') }
    finally { setBusy(false) }
  }
  const inputClass = 'block w-full border border-border rounded-lg p-2 mt-1 bg-surface-1'
  return <section className="v2-panel p-5">
    <h2 className="text-lg font-semibold">Correct extracted evidence</h2>
    <p className="text-sm text-muted my-2">A reviewer can correct a field using the source document. The original evidence and change history are retained, related checks run again, and the correction remains flagged for review.</p>
    {!revision ? <button type="button" className="v2-text-button" disabled={busy} onClick={load}>Open correction form</button> :
      <form onSubmit={submit} className="space-y-3 text-sm">
        <label className="block">Field<select className={inputClass} value={field} onChange={e => setField(e.target.value)}>
          <option value="header.grand_total">Grand total</option><option value="header.subtotal">Subtotal</option>
          <option value="header.invoice_number">Invoice number</option><option value="header.invoice_date">Invoice date</option>
          <option value="header.po_reference">Purchase order reference</option><option value="header.vendor_name">Supplier name</option>
        </select></label>
        <label className="block">Correct value<input className={inputClass} required maxLength={2000} value={value} onChange={e => setValue(e.target.value)} /></label>
        <label className="block">Source page<input className={inputClass} type="number" min={1} max={pageCount} required value={page} onChange={e => setPage(Number(e.target.value))} /></label>
        <label className="block">Exact source quote<textarea className={inputClass} required maxLength={4000} value={quote} onChange={e => setQuote(e.target.value)} /></label>
        <label className="block">Reason<textarea className={inputClass} required minLength={3} maxLength={4000} value={reason} onChange={e => setReason(e.target.value)} /></label>
        <button className="v2-primary" disabled={busy}>{busy ? 'Saving…' : 'Save correction and rerun checks'}</button>
      </form>}
    {error && <p className="text-sm text-red-600 mt-3" role="alert">{error}</p>}
  </section>
}
