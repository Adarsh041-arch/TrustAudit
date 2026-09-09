import { useState } from 'react'
import { ArrowUpRight, ArrowRight, Search, FileText, CircleCheck, CircleAlert, ScanLine, UploadCloud, Layers, ChevronRight, ListFilter, X } from 'lucide-react'
import type { DocumentAuditResult } from '../types/audit'

type Status = 'attention' | 'incomplete' | 'passed'
function statusOf(d: DocumentAuditResult): Status {
  if (d.audit_status === 'FAIL') return 'attention' 
  if (['INCOMPLETE','UNSUPPORTED'].includes(d.audit_status || '') || d.document_status !== 'READY' || d.audit_status === 'NOT_AUDITED' || !d.coverage_complete) return 'incomplete'
  if (['FAIL','NEEDS_REVIEW'].includes(d.audit_status || '') || d.human_review_recommended || !d.passed || d.failed_rules.length > 0) return 'attention'
  return 'passed'
}
const labels = { attention: 'Needs attention', incomplete: 'Incomplete', passed: 'Reported pass' }
function nextAction(d: DocumentAuditResult) {
  if (statusOf(d) === 'incomplete') return 'Check missing or unreadable evidence'
  return d.failed_rules[0]?.recommendation || (d.human_review_recommended ? 'Inspect evidence and resolve uncertainty' : 'Open results and supporting evidence')
}
interface Props { documents: DocumentAuditResult[]; executiveSummary?: string; onOpenDocument?: (id: string) => void; onLoadDemoData?: () => void; onUpload?: () => void }
export function DashboardSection({ documents, executiveSummary, onOpenDocument, onLoadDemoData, onUpload }: Props) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Status | 'all'>('all')
  const [sort, setSort] = useState('priority')
  const counts = { all: documents.length, attention: documents.filter(d => statusOf(d) === 'attention').length, incomplete: documents.filter(d => statusOf(d) === 'incomplete').length, passed: documents.filter(d => statusOf(d) === 'passed').length }
  const rank = (d: DocumentAuditResult) => d.failed_rules.some(r => r.severity === 'critical') ? 0 : statusOf(d) === 'attention' ? 1 : statusOf(d) === 'incomplete' ? 2 : 3
  const filtered = documents.filter(d => (filter === 'all' || statusOf(d) === filter) && `${d.document_name} ${d.document_id} ${d.document_type} ${d.metadata?.vendor_name || ''}`.toLowerCase().includes(search.toLowerCase())).sort((a,b) => sort === 'name' ? a.document_name.localeCompare(b.document_name) : rank(a) - rank(b) || a.document_name.localeCompare(b.document_name))
  const attention = [...documents].filter(d => statusOf(d) !== 'passed').sort((a,b) => rank(a)-rank(b))
  const pages = documents.reduce((n,d) => n + d.page_count,0)
  const examined = documents.reduce((n,d) => n + d.pages_examined,0)
  const metrics = [
    { id: 'all' as const, label: 'Documents', value: counts.all, detail: 'In this workspace', icon: FileText },
    { id: 'attention' as const, label: 'Needs attention', value: counts.attention, detail: 'Findings or review requested', icon: CircleAlert },
    { id: 'incomplete' as const, label: 'Incomplete', value: counts.incomplete, detail: 'Evidence needs a closer look', icon: ScanLine },
    { id: 'passed' as const, label: 'Reported pass', value: counts.passed, detail: 'No review flag in returned results', icon: CircleCheck },
  ]
  return <div className="v2-overview">
    <div className="v2-page-heading"><div><p className="v2-eyebrow">YOUR AUDIT, AT A GLANCE</p><h1>Every document. A clearer picture.</h1><p>Track what’s ready, what needs attention, and what to do next.</p></div><button className="v2-primary" onClick={onUpload}><UploadCloud size={17} /> Upload documents</button></div>
    <div className="v2-metrics">{metrics.map(m => <button key={m.id} className={`v2-stat ${m.id} ${filter === m.id ? 'selected' : ''}`} onClick={() => setFilter(m.id)} aria-pressed={filter === m.id}><div><span>{m.label}</span><m.icon size={19} /></div><strong>{m.value.toString().padStart(2,'0')}</strong><small>{m.detail}</small></button>)}</div>
    <div className="v2-overview-grid">
      <section className="v2-panel v2-attention"><div className="v2-panel-heading"><div><p className="v2-eyebrow">FOCUS FIRST</p><h2>{attention.length ? 'A few things need your attention' : documents.length ? 'Your workspace is up to date' : 'Your first audit starts here'}</h2></div><span className="v2-count">{attention.length} documents</span></div>
        {attention.length ? <div className="v2-action-list">{attention.slice(0,3).map(d => <button key={d.document_id} onClick={() => onOpenDocument?.(d.document_id)}><span className={`v2-action-icon ${statusOf(d)}`}><CircleAlert size={19} /></span><div><strong>{d.failed_rules[0]?.rule_title || (statusOf(d) === 'incomplete' ? 'Evidence is incomplete' : 'Review requested')}</strong><span>{d.document_name}</span><p>{nextAction(d)}</p></div><ArrowUpRight size={18} /></button>)}</div> : <div className="v2-start"><div className="v2-start-icon"><Layers size={28} /></div><h3>{documents.length ? 'Keep the evidence close' : 'Bring the whole transaction together'}</h3><p>{documents.length ? 'Open a document below to inspect the returned checks and evidence. Reported passes reflect the current audit engine.' : 'Add an invoice with its purchase order and receipt. See the checks, discrepancies, and supporting evidence in one place.'}</p><button className="v2-text-button" onClick={documents.length ? () => onOpenDocument?.(documents[0].document_id) : onUpload}>{documents.length ? 'Explore a document' : 'Start your first audit'} <ArrowRight size={16} /></button></div>}
        {attention.length > 3 && <button className="v2-panel-footer" onClick={() => setFilter('attention')}>Show all documents needing attention <ArrowRight size={15} /></button>}
      </section>
      <section className="v2-panel v2-snapshot"><div className="v2-panel-heading"><div><p className="v2-eyebrow">AUDIT SNAPSHOT</p><h2>Where things stand</h2></div><ScanLine size={20} /></div><div className="v2-coverage"><strong>{pages ? Math.round(examined/pages*100) : '—'}{pages > 0 && <small>%</small>}</strong><span>Pages examined</span><div className="v2-progress-track"><div style={{width: `${pages ? Math.min(100,examined/pages*100) : 0}%`}} /></div><p>{examined} of {pages} pages examined · not a verification score</p></div><div className="v2-status-breakdown">{(['attention','incomplete','passed'] as const).map(s => <button key={s} onClick={() => setFilter(s)}><span><i className={s} />{labels[s]}</span><strong>{counts[s]}</strong><ChevronRight size={14} /></button>)}</div><p className="v2-snapshot-note">A reported pass and a completed human review are different. Open each document for context.</p></section>
    </div>
    <section className="v2-panel v2-register"><div className="v2-panel-heading"><div><h2>Document tracker <span className="v2-count">{documents.length}</span></h2><p>Find a document, understand its status, and pick up the next action.</p></div><span className="v2-register-label"><Layers size={15} /> Current workspace</span></div>
      <div className="v2-table-tools"><div className="v2-filter-tabs" aria-label="Filter documents">{(['all','attention','incomplete','passed'] as const).map(s => <button key={s} aria-pressed={filter === s} className={filter === s ? 'active' : ''} onClick={() => setFilter(s)}>{s === 'all' ? 'All documents' : labels[s]}<small>{counts[s]}</small></button>)}</div><div className="v2-search"><Search size={16} /><input aria-label="Search documents" placeholder="Search documents or suppliers…" value={search} onChange={e => setSearch(e.target.value)} />{search && <button aria-label="Clear search" onClick={() => setSearch('')}><X size={14} /></button>}</div></div>
      <div className="v2-table-scroll"><table className="v2-document-table"><thead><tr><th>Document / supplier</th><th>Status</th><th>Evidence coverage</th><th>Next action</th><th><span className="sr-only">Open document</span></th></tr></thead><tbody>{filtered.map(d => <tr key={d.document_id}><td><button className="v2-document-link" onClick={() => onOpenDocument?.(d.document_id)}><span className="v2-file-icon"><FileText size={20} /></span><span><strong>{d.document_name}</strong><small>{d.document_type.replaceAll('_',' ')}{d.metadata?.vendor_name ? ` · ${d.metadata.vendor_name}` : ''}</small></span></button></td><td><span className={`v2-status ${statusOf(d)}`}><i />{labels[statusOf(d)]}</span>{d.failed_rules.length > 0 && <small className="v2-cell-note">{d.failed_rules.length} finding{d.failed_rules.length !== 1 ? 's' : ''}</small>}</td><td><span className="v2-page-count">{d.pages_examined} / {d.page_count} pages</span><small className="v2-cell-note">{d.coverage_complete ? 'Examined' : 'Incomplete'}</small></td><td><p className="v2-next-action" title={nextAction(d)}>{nextAction(d)}</p></td><td><button className="v2-icon-button" aria-label={`Open ${d.document_name}`} onClick={() => onOpenDocument?.(d.document_id)}><ArrowUpRight size={18} /></button></td></tr>)}</tbody></table></div>
      {!filtered.length && <div className="v2-empty-results"><FileText size={25} /><strong>{documents.length ? 'No documents match these filters' : 'No documents yet'}</strong><p>{documents.length ? 'Try another search or reset your filters.' : 'Upload your files to start tracking an audit, or explore the sample workspace.'}</p><button className="v2-text-button" onClick={documents.length ? () => {setSearch('');setFilter('all')} : onLoadDemoData}>{documents.length ? 'Reset filters' : 'Explore sample workspace'} <ArrowRight size={15} /></button></div>}
      <div className="v2-table-footer"><span>Showing {filtered.length} of {documents.length} documents</span><label><ListFilter size={14} /><select aria-label="Sort documents" value={sort} onChange={e => setSort(e.target.value)}><option value="priority">Attention first</option><option value="name">Document name</option></select></label></div>
    </section>
    {executiveSummary && <details className="v2-summary"><summary>Read the audit summary</summary><p>{executiveSummary}</p></details>}
  </div>
}
