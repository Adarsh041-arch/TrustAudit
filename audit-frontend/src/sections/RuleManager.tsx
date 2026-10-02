import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api/http'
import { V2_BASE } from '../api/api_v2'

type Definition = { field_path: string; operator: string; expected_value: string | null; second_value: string | null; quantifier: string; case_sensitive: boolean }
type Rule = { check_id: string; title: string; failure_message: string; applies_to: string[]; severity: string; score_weight: number | null; score_impact: boolean; blocking: boolean; enabled: boolean; source: string; configured: boolean; determinism: string; custom_definition: Definition | null }
type Configuration = { revision: number; rules: Rule[]; fields: string[]; can_edit: boolean; history: Array<{ revision: number; action: string; check_id: string; actor_id: string; created_at: string }> }
const DOCUMENTS = ['invoice', 'purchase_order', 'delivery_challan', 'goods_receipt_note', 'contract', 'letter', 'certificate_of_origin']
const OPERATORS: Record<string, string> = { is_present: 'Must be present', equals: 'Equals', not_equals: 'Does not equal', contains: 'Contains text', starts_with: 'Starts with', ends_with: 'Ends with', greater_than: 'Greater than', less_than: 'Less than', between: 'Between (inclusive)' }
const WEIGHTS: Record<string, number> = { critical: 40, high: 25, medium: 10, low: 5 }
const label = (value: string) => value.replaceAll('_', ' ')
const newRule = (): Rule => ({ check_id: '', title: '', failure_message: '', applies_to: ['invoice'], severity: 'medium', score_weight: 10, score_impact: true, blocking: true, enabled: true, source: 'custom', configured: true, determinism: 'deterministic', custom_definition: { field_path: 'header.payment_terms', operator: 'is_present', expected_value: null, second_value: null, quantifier: 'all', case_sensitive: false } })

export function RuleManager() {
  const [config, setConfig] = useState<Configuration | null>(null)
  const [draft, setDraft] = useState<Rule | null>(null)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const editorRef = useRef<HTMLFormElement>(null)
  const [editorRequest, setEditorRequest] = useState(0)
  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    editor.focus({ preventScroll: true })
    editor.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' })
  }, [editorRequest])
  function openEditor(rule: Rule) {
    setDraft(structuredClone(rule))
    setError('')
    setEditorRequest(previous => previous + 1)
  }
  async function load() {
    const response = await apiFetch(`${V2_BASE}/rules`)
    if (!response.ok) {
      if (response.status === 404) throw new Error('The connected backend does not have the checks API. Restart the TrustAudit backend with the latest code, then retry.')
      if (response.status === 401 || response.status === 403) throw new Error('Workspace access was denied. Check your access token in Workspace connection, then retry.')
      throw new Error(`Could not load workspace checks (HTTP ${response.status}). Please retry.`)
    }
    setConfig(await response.json())
  }
  async function retry() {
    setError('')
    try { await load() }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not reach the backend. Check that TrustAudit is running, then retry.') }
  }
  useEffect(() => { void load().catch(err => setError(err.message)) }, [])
  function change<K extends keyof Rule>(key: K, value: Rule[K]) {
    setDraft(previous => previous ? { ...previous, [key]: value } : previous)
  }
  function condition(key: keyof Definition, value: string | boolean) {
    setDraft(previous => previous?.custom_definition ? { ...previous, custom_definition: { ...previous.custom_definition, [key]: value } } : previous)
  }
  async function save(remove = false) {
    if (!draft || !config) return
    setBusy(true); setError(''); setNotice('')
    const isNew = !draft.check_id
    const shared = { expected_revision: config.revision, enabled: draft.enabled, severity: draft.severity, score_weight: draft.score_weight, score_impact: draft.score_impact, blocking: draft.blocking, applies_to: draft.applies_to }
    const body = remove ? { expected_revision: config.revision } : draft.source === 'custom'
      ? { ...shared, title: draft.title, failure_message: draft.failure_message, ...(isNew ? { definition: draft.custom_definition } : { custom_definition: draft.custom_definition }) }
      : shared
    try {
      const response = await apiFetch(`${V2_BASE}/rules${isNew ? '' : `/${encodeURIComponent(draft.check_id)}`}`, { method: remove ? 'DELETE' : isNew ? 'POST' : 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const result = await response.json()
      if (!response.ok) {
        if (response.status === 409) await load()
        throw new Error(typeof result.detail === 'string' ? result.detail : 'Check the rule fields and try again')
      }
      await load(); setDraft(null)
      setNotice('Checks saved. Existing workspace documents have been rechecked. Refresh the workspace to see their updated results.')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save checks') }
    finally { setBusy(false) }
  }
  const rules = config?.rules.filter(rule => `${rule.title} ${rule.check_id} ${rule.applies_to.join(' ')}`.toLowerCase().includes(query.toLowerCase())) ?? []
  return <section className="v2-panel" aria-label="Workspace checks">
    <div className="v2-panel-heading"><div><h2>Workspace checks</h2><p>Choose what to check and how much a failed check deducts from a document’s 100-point score.</p></div><button className="v2-primary" disabled={!config?.can_edit || busy} onClick={() => openEditor(newRule())}>Add check</button></div>
    <div className="px-6 pb-5 space-y-4">
      <p className="text-sm text-muted">Priority controls how urgently a finding is shown. Weight is the score deduction (0–100 points). Blocking checks determine pass or fail independently of the score. Recommended fields default to no score deduction.</p>
      {config && <p className="text-xs text-muted">Configuration version {config.revision} · {config.rules.filter(rule => rule.enabled).length} enabled checks{!config.can_edit && ' · Read only — ask your workspace administrator for rule configuration access'}</p>}
      {error && <div role="alert" className="text-red-600"><p>{error}</p>{!config && <button type="button" className="v2-text-button" onClick={() => void retry()}>Retry loading checks</button>}</div>}
      {notice && <div role="status" className="text-emerald-700 dark:text-emerald-300"><p>{notice}</p><button type="button" className="v2-text-button" onClick={() => window.location.reload()}>Refresh workspace results</button></div>}
      {!config && !error && <p role="status">Loading checks…</p>}
      <label className="v2-search"><span>Search</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Check name or document type" /></label>
      <div className="v2-table-scroll"><table className="v2-document-table"><thead><tr><th>Check</th><th>Documents</th><th>Priority</th><th>Score deduction</th><th>Status</th><th>Action</th></tr></thead><tbody>{rules.map(rule => <tr key={rule.check_id}>
        <td><strong>{rule.title}</strong><small className="v2-cell-note">{rule.source === 'custom' ? 'Your custom check' : 'Built-in check'}{rule.configured ? ' · Customized' : ''}{rule.determinism !== 'deterministic' ? ' · Advisory definition; automatic execution unavailable' : ''}</small></td>
        <td className="text-xs capitalize">{rule.applies_to.map(label).join(', ')}</td><td className="capitalize">{rule.severity}</td><td>{rule.score_impact ? `${rule.score_weight ?? WEIGHTS[rule.severity]} points` : 'None'}</td><td>{rule.enabled ? 'Enabled' : 'Disabled'}{rule.blocking && rule.enabled && <small className="v2-cell-note">Blocks clearance</small>}</td><td><button className="v2-text-button" disabled={!config?.can_edit || busy} onClick={() => openEditor(rule)}>Edit</button></td>
      </tr>)}</tbody></table>{config && !rules.length && <p className="p-5 text-muted">No checks match your search.</p>}</div>
      {draft && <form ref={editorRef} tabIndex={-1} className="p-5 rounded-xl border border-border bg-surface-1 space-y-4 scroll-mt-6" onSubmit={event => { event.preventDefault(); void save() }} aria-label="Edit check">
        <h3 className="text-lg font-semibold">{draft.check_id ? 'Edit check' : 'Create a custom check'}</h3>
        <div className="grid md:grid-cols-2 gap-4">
          <label className="block text-sm">Check name<input className="block w-full p-2 border border-border rounded-lg bg-surface-2" required minLength={3} maxLength={160} readOnly={draft.source === 'built_in'} value={draft.title} onChange={event => change('title', event.target.value)} /></label>
          <label className="block text-sm">Priority<select className="block w-full p-2 border border-border rounded-lg bg-surface-2" value={draft.severity} onChange={event => change('severity', event.target.value)}>{['low', 'medium', 'high', 'critical'].map(priority => <option key={priority} value={priority}>{label(priority)}</option>)}</select></label>
          <label className="block text-sm">Weight (points deducted on failure)<input className="block w-full p-2 border border-border rounded-lg bg-surface-2" type="number" min={0} max={100} step="0.1" required value={draft.score_weight ?? WEIGHTS[draft.severity]} onChange={event => change('score_weight', Number(event.target.value))} /></label>
          <div className="space-y-2 text-sm"><label className="block"><input type="checkbox" checked={draft.enabled} onChange={event => change('enabled', event.target.checked)} /> Enable this check</label><label className="block"><input type="checkbox" checked={draft.score_impact} onChange={event => change('score_impact', event.target.checked)} /> Affect document score</label><label className="block"><input type="checkbox" checked={draft.blocking} onChange={event => change('blocking', event.target.checked)} /> Failure blocks clearance</label></div>
        </div>
        <fieldset><legend className="text-sm mb-2">Apply to document types (select at least one)</legend><div className="flex flex-wrap gap-4">{DOCUMENTS.map(type => <label className="text-sm capitalize" key={type}><input type="checkbox" checked={draft.applies_to.includes(type)} onChange={event => change('applies_to', event.target.checked ? [...draft.applies_to, type] : draft.applies_to.filter(value => value !== type))} /> {label(type)}</label>)}</div></fieldset>
        {draft.source === 'custom' && draft.custom_definition && <div className="space-y-3">
          <div className="grid md:grid-cols-2 gap-4"><label className="text-sm">Document field<select className="block w-full p-2 border border-border rounded-lg bg-surface-2" value={draft.custom_definition.field_path} onChange={event => condition('field_path', event.target.value)}>{config?.fields.map(field => <option key={field} value={field}>{label(field.replace('.', ' → '))}</option>)}</select></label><label className="text-sm">Condition<select className="block w-full p-2 border border-border rounded-lg bg-surface-2" value={draft.custom_definition.operator} onChange={event => condition('operator', event.target.value)}>{Object.entries(OPERATORS).map(([operator, text]) => <option key={operator} value={operator}>{text}</option>)}</select></label></div>
          {draft.custom_definition.operator !== 'is_present' && <label className="block text-sm">Expected value<input required maxLength={500} className="block w-full p-2 border border-border rounded-lg bg-surface-2" value={draft.custom_definition.expected_value ?? ''} onChange={event => condition('expected_value', event.target.value)} /></label>}
          {draft.custom_definition.operator === 'between' && <label className="block text-sm">Upper value<input required maxLength={500} className="block w-full p-2 border border-border rounded-lg bg-surface-2" value={draft.custom_definition.second_value ?? ''} onChange={event => condition('second_value', event.target.value)} /></label>}
          {draft.custom_definition.field_path.includes('_items.') || draft.custom_definition.field_path.startsWith('tax_lines.') || draft.custom_definition.field_path.startsWith('certificate_goods.') ? <label className="block text-sm">Rows to check<select className="block w-full p-2 border border-border rounded-lg bg-surface-2" value={draft.custom_definition.quantifier} onChange={event => condition('quantifier', event.target.value)}><option value="all">Every row must satisfy the condition</option><option value="any">At least one row must satisfy the condition</option></select></label> : null}
          <label className="block text-sm"><input type="checkbox" checked={draft.custom_definition.case_sensitive} onChange={event => condition('case_sensitive', event.target.checked)} /> Match text case exactly</label>
          <label className="block text-sm">Message shown when the check fails<input required minLength={3} maxLength={500} className="block w-full p-2 border border-border rounded-lg bg-surface-2" value={draft.failure_message} onChange={event => change('failure_message', event.target.value)} placeholder="For example: Payment terms must include 30 days" /></label>
        </div>}
        <div className="flex flex-wrap gap-4"><button className="v2-primary" disabled={busy || !draft.applies_to.length} type="submit">{busy ? 'Saving and rechecking…' : 'Save and recheck'}</button><button className="v2-text-button" type="button" disabled={busy} onClick={() => setDraft(null)}>Cancel</button>{draft.check_id && (draft.source === 'custom' || draft.configured) && <button className="v2-text-button" type="button" disabled={busy} onClick={() => void save(true)}>{draft.source === 'custom' ? 'Delete custom check' : 'Restore built-in defaults'}</button>}</div>
      </form>}
      {!!config?.history.length && <details><summary className="text-sm cursor-pointer">Recent changes</summary><ul className="text-xs text-muted space-y-2 pt-3">{[...config.history].reverse().map(event => <li key={event.revision}>Version {event.revision} · {label(event.action)} · {event.actor_id} · {new Date(event.created_at).toLocaleString()}</li>)}</ul></details>}
    </div>
  </section>
}
