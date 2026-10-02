import { useState } from 'react'
import {
  ArrowUpRight,
  ArrowRight,
  Search,
  FileText,
  CircleCheck,
  CircleAlert,
  ScanLine,
  UploadCloud,
  Layers,
  ChevronRight,
  ListFilter,
  X,
  Clock,
  History,
  AlertCircle,
} from 'lucide-react'
import type { DocumentAuditResult } from '../types/audit'
import type { AuditSessionSummary } from '../api/api_v2'
import { getDocumentStatus } from '../utils/documentStatus'

type FilterKey = 'all' | 'PASS' | 'FAIL' | 'NEEDS_REVIEW' | 'INCOMPLETE' | 'UNSUPPORTED'

function nextAction(d: DocumentAuditResult) {
  const status = getDocumentStatus(d)
  if (status.verdict === 'UNSUPPORTED') return 'Unrecognized document — no checks apply'
  if (status.verdict === 'INCOMPLETE') return 'Check missing or unreadable pages/evidence'
  return (
    d.failed_rules[0]?.recommendation ||
    (d.human_review_recommended
      ? 'Inspect evidence and resolve uncertainty'
      : 'Open results and supporting evidence')
  )
}

interface Props {
  documents: DocumentAuditResult[]
  executiveSummary?: string
  activeSessionId?: string | null
  sessions?: AuditSessionSummary[]
  onSelectSession?: (id: string) => void
  onGoToSessions?: () => void
  onOpenDocument?: (id: string) => void
  onLoadDemoData?: () => void
  onUpload?: () => void
}

export function DashboardSection({
  documents,
  executiveSummary,
  activeSessionId,
  sessions,
  onSelectSession,
  onGoToSessions,
  onOpenDocument,
  onLoadDemoData,
  onUpload,
}: Props) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<FilterKey>('all')
  const [sort, setSort] = useState('priority')

  const counts = {
    all: documents.length,
    pass: documents.filter((d) => getDocumentStatus(d).verdict === 'PASS').length,
    fail: documents.filter((d) => getDocumentStatus(d).verdict === 'FAIL').length,
    needs_review: documents.filter((d) => getDocumentStatus(d).verdict === 'NEEDS_REVIEW').length,
    incomplete: documents.filter((d) => getDocumentStatus(d).verdict === 'INCOMPLETE').length,
    unsupported: documents.filter((d) => getDocumentStatus(d).verdict === 'UNSUPPORTED').length,
  }

  const rank = (d: DocumentAuditResult) => {
    const v = getDocumentStatus(d).verdict
    if (v === 'FAIL') return 0
    if (v === 'NEEDS_REVIEW') return 1
    if (v === 'INCOMPLETE') return 2
    if (v === 'PASS') return 3
    return 4 // UNSUPPORTED / NOT_AUDITED
  }

  const filtered = documents
    .filter((d) => {
      const v = getDocumentStatus(d).verdict
      if (filter !== 'all' && v !== filter) return false
      const target = `${d.document_name} ${d.document_id} ${d.document_type} ${d.metadata?.vendor_name || ''}`.toLowerCase()
      return target.includes(search.toLowerCase())
    })
    .sort((a, b) =>
      sort === 'name'
        ? a.document_name.localeCompare(b.document_name)
        : rank(a) - rank(b) || a.document_name.localeCompare(b.document_name)
    )

  const attention = [...documents]
    .filter((d) => {
      const v = getDocumentStatus(d).verdict
      return v === 'FAIL' || v === 'NEEDS_REVIEW' || v === 'INCOMPLETE'
    })
    .sort((a, b) => rank(a) - rank(b))

  const pages = documents.reduce((n, d) => n + d.page_count, 0)
  const examined = documents.reduce((n, d) => n + d.pages_examined, 0)

  const metrics = [
    {
      id: 'all' as const,
      label: 'Total Documents',
      value: counts.all,
      detail: 'In this audit session',
      icon: FileText,
      active: filter === 'all',
      onClick: () => setFilter('all'),
    },
    {
      id: 'PASS' as const,
      label: 'Passed',
      value: counts.pass,
      detail: 'All mandatory checks cleared',
      icon: CircleCheck,
      active: filter === 'PASS',
      onClick: () => setFilter('PASS'),
    },
    {
      id: 'FAIL' as const,
      label: 'Failed',
      value: counts.fail,
      detail: 'Mandatory checks failed',
      icon: CircleAlert,
      active: filter === 'FAIL',
      onClick: () => setFilter('FAIL'),
    },
    {
      id: 'NEEDS_REVIEW' as const,
      label: 'Needs Review',
      value: counts.needs_review,
      detail: 'Review flags or variance',
      icon: AlertCircle,
      active: filter === 'NEEDS_REVIEW',
      onClick: () => setFilter('NEEDS_REVIEW'),
    },
  ]

  const allFilterTabs: Array<{ id: FilterKey; label: string; count: number }> = [
    { id: 'all', label: 'All documents', count: counts.all },
    { id: 'PASS', label: 'Pass', count: counts.pass },
    { id: 'FAIL', label: 'Fail', count: counts.fail },
    { id: 'NEEDS_REVIEW', label: 'Needs Review', count: counts.needs_review },
    { id: 'INCOMPLETE', label: 'Incomplete', count: counts.incomplete },
    { id: 'UNSUPPORTED', label: 'Unsupported', count: counts.unsupported },
  ]
  const filterTabs = allFilterTabs.filter((t) => t.id === 'all' || t.count > 0 || t.id === 'PASS' || t.id === 'FAIL')

  return (
    <div className="v2-overview">
      <div className="v2-page-heading">
        <div>
          <p className="v2-eyebrow">YOUR AUDIT, AT A GLANCE</p>
          <h1>Every document. A clearer picture.</h1>
          <p>Track what’s ready, what needs attention, and what to do next.</p>
        </div>
        <button className="v2-primary" onClick={onUpload}>
          <UploadCloud size={17} /> Upload documents
        </button>
      </div>

      {/* Session context bar */}
      {sessions && sessions.length > 0 && (
        <div className="v2-session-context-bar mb-5">
          <div className="v2-session-context-left">
            <span className="v2-session-context-badge">
              <Clock size={14} className="text-teal-600 dark:text-teal-400" />
              <span className="font-semibold text-ink">
                {activeSessionId === 'all'
                  ? 'All Sessions Combined (Aggregate)'
                  : activeSessionId
                    ? `Showing: ${activeSessionId}`
                    : 'Current Session'}
              </span>
            </span>
            <span className="v2-session-context-count text-muted text-[12px]">
              <strong>{documents.length}</strong> document{documents.length !== 1 ? 's' : ''} in this audit
            </span>
          </div>
          <div className="v2-session-context-right">
            <label className="v2-session-select-label">
              <span className="text-[12px] text-muted font-medium">Switch session:</span>
              <select
                value={activeSessionId || ''}
                onChange={(e) => onSelectSession?.(e.target.value)}
                className="v2-session-dropdown"
                aria-label="Select audit session"
              >
                {sessions.map((s, idx) => (
                  <option key={s.session_id} value={s.session_id}>
                    {idx === 0 ? 'Latest Run: ' : ''}{s.session_id} ({s.document_count} doc{s.document_count !== 1 ? 's' : ''})
                  </option>
                ))}
                <option value="all">
                  All Sessions Combined (All {sessions.reduce((a, b) => a + (b.document_count || 0), 0)} docs)
                </option>
              </select>
            </label>
            {onGoToSessions && (
              <button
                onClick={onGoToSessions}
                className="v2-text-button v2-all-sessions-link"
              >
                <History size={14} /> Sessions History ({sessions.length})
              </button>
            )}
          </div>
        </div>
      )}

      {/* Metric Cards */}
      <div className="v2-metrics">
        {metrics.map((m) => (
          <button
            key={m.id}
            className={`v2-stat ${m.id === 'all' ? '' : m.id === 'PASS' ? 'passed' : m.id === 'FAIL' ? 'attention' : 'review'} ${m.active ? 'selected' : ''}`}
            onClick={m.onClick}
            aria-pressed={m.active}
          >
            <div>
              <span>{m.label}</span>
              <m.icon size={19} />
            </div>
            <strong>{m.value.toString().padStart(2, '0')}</strong>
            <small>{m.detail}</small>
          </button>
        ))}
      </div>

      <div className="v2-overview-grid">
        {/* Focus First */}
        <section className="v2-panel v2-attention">
          <div className="v2-panel-heading">
            <div>
              <p className="v2-eyebrow">FOCUS FIRST</p>
              <h2>
                {attention.length
                  ? 'A few things need your attention'
                  : documents.length
                    ? 'Your workspace is up to date'
                    : 'Your first audit starts here'}
              </h2>
            </div>
            <span className="v2-count">{attention.length} documents</span>
          </div>
          {attention.length ? (
            <div className="v2-action-list">
              {attention.slice(0, 3).map((d) => {
                const s = getDocumentStatus(d)
                return (
                  <button key={d.document_id} onClick={() => onOpenDocument?.(d.document_id)}>
                    <span className={`v2-action-icon ${s.variant}`}>
                      <CircleAlert size={19} />
                    </span>
                    <div>
                      <strong>
                        {d.failed_rules[0]?.rule_title ||
                          (s.verdict === 'INCOMPLETE'
                            ? 'Mandatory checks incomplete'
                            : 'Human review required')}
                      </strong>
                      <span>
                        {d.document_name} · <span className={`font-semibold ${s.variant}`}>{s.label}</span>
                      </span>
                      <p>{nextAction(d)}</p>
                    </div>
                    <ArrowUpRight size={18} />
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="v2-start">
              <div className="v2-start-icon">
                <Layers size={28} />
              </div>
              <h3>
                {documents.length
                  ? 'All documents are in order'
                  : 'Bring the whole transaction together'}
              </h3>
              <p>
                {documents.length
                  ? 'All audited documents passed deterministic checks with no pending review flags.'
                  : 'Add an invoice with its purchase order and receipt. See the checks, discrepancies, and supporting evidence in one place.'}
              </p>
              <button
                className="v2-text-button"
                onClick={documents.length ? () => onOpenDocument?.(documents[0].document_id) : onUpload}
              >
                {documents.length ? 'Explore a document' : 'Start your first audit'}{' '}
                <ArrowRight size={16} />
              </button>
            </div>
          )}
          {attention.length > 3 && (
            <button
              className="v2-panel-footer"
              onClick={() => setFilter(counts.fail > 0 ? 'FAIL' : 'NEEDS_REVIEW')}
            >
              Show all documents needing attention <ArrowRight size={15} />
            </button>
          )}
        </section>

        {/* Audit Snapshot */}
        <section className="v2-panel v2-snapshot">
          <div className="v2-panel-heading">
            <div>
              <p className="v2-eyebrow">AUDIT SNAPSHOT</p>
              <h2>Where things stand</h2>
            </div>
            <ScanLine size={20} />
          </div>
          <div className="v2-coverage">
            <strong>
              {pages ? Math.round((examined / pages) * 100) : '—'}
              {pages > 0 && <small>%</small>}
            </strong>
            <span>Pages examined</span>
            <div className="v2-progress-track">
              <div
                style={{
                  width: `${pages ? Math.min(100, (examined / pages) * 100) : 0}%`,
                }}
              />
            </div>
            <p>{examined} of {pages} pages examined · not a verification score</p>
          </div>
          <div className="v2-status-breakdown">
            {[
              { id: 'PASS' as const, label: 'Pass', count: counts.pass, cls: 'passed' },
              { id: 'FAIL' as const, label: 'Fail', count: counts.fail, cls: 'attention' },
              { id: 'NEEDS_REVIEW' as const, label: 'Needs Review', count: counts.needs_review, cls: 'review' },
              { id: 'INCOMPLETE' as const, label: 'Incomplete', count: counts.incomplete, cls: 'incomplete' },
              { id: 'UNSUPPORTED' as const, label: 'Unsupported', count: counts.unsupported, cls: 'unsupported' },
            ]
              .filter((item) => item.count > 0)
              .map((item) => (
                <button key={item.id} onClick={() => setFilter(item.id)}>
                  <span>
                    <i className={item.cls} />
                    {item.label}
                  </span>
                  <strong>{item.count}</strong>
                  <ChevronRight size={14} />
                </button>
              ))}
          </div>
          <p className="v2-snapshot-note">
            A reported pass and an advisory document are different. Open each document for context.
          </p>
        </section>
      </div>

      {/* Document Tracker */}
      <section className="v2-panel v2-register">
        <div className="v2-panel-heading">
          <div>
            <h2>
              Document tracker <span className="v2-count">{documents.length}</span>
            </h2>
            <p>Find a document, understand its status, and pick up the next action.</p>
          </div>
          <span className="v2-register-label">
            <Layers size={15} /> Current workspace
          </span>
        </div>

        <div className="v2-table-tools">
          <div className="v2-filter-tabs" aria-label="Filter documents">
            {filterTabs.map((tab) => (
              <button
                key={tab.id}
                aria-pressed={filter === tab.id}
                className={filter === tab.id ? 'active' : ''}
                onClick={() => setFilter(tab.id)}
              >
                {tab.label}
                <small>{tab.count}</small>
              </button>
            ))}
          </div>
          <div className="v2-search">
            <Search size={16} />
            <input
              aria-label="Search documents"
              placeholder="Search documents or suppliers…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button aria-label="Clear search" onClick={() => setSearch('')}>
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        <div className="v2-table-scroll">
          <table className="v2-document-table">
            <thead>
              <tr>
                <th>Document / supplier</th>
                <th>Status</th>
                <th>Evidence coverage</th>
                <th>Next action</th>
                <th>
                  <span className="sr-only">Open document</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => {
                const docStatus = getDocumentStatus(d)
                return (
                  <tr key={d.document_id}>
                    <td>
                      <button
                        className="v2-document-link"
                        onClick={() => onOpenDocument?.(d.document_id)}
                      >
                        <span className="v2-file-icon">
                          <FileText size={20} />
                        </span>
                        <span>
                          <strong>{d.document_name}</strong>
                          <small>
                            {d.document_type.replaceAll('_', ' ')}
                            {d.metadata?.vendor_name ? ` · ${d.metadata.vendor_name}` : ''}
                          </small>
                        </span>
                      </button>
                    </td>
                    <td>
                      <span className={`v2-status ${docStatus.variant}`}>
                        <i />
                        {docStatus.label}
                      </span>
                      {d.failed_rules.length > 0 && (
                        <small className="v2-cell-note">
                          {d.failed_rules.length} finding{d.failed_rules.length !== 1 ? 's' : ''}
                        </small>
                      )}
                    </td>
                    <td>
                      <span className="v2-page-count">
                        {d.pages_examined} / {d.page_count} pages
                      </span>
                      <small className="v2-cell-note">
                        {d.coverage_complete ? 'All pages examined' : 'Partial scan'}
                      </small>
                    </td>
                    <td>
                      <p className="v2-next-action" title={nextAction(d)}>
                        {nextAction(d)}
                      </p>
                    </td>
                    <td>
                      <button
                        className="v2-icon-button"
                        aria-label={`Open ${d.document_name}`}
                        onClick={() => onOpenDocument?.(d.document_id)}
                      >
                        <ArrowUpRight size={18} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {!filtered.length && (
          <div className="v2-empty-results">
            <FileText size={25} />
            <strong>
              {documents.length ? 'No documents match these filters' : 'No documents yet'}
            </strong>
            <p>
              {documents.length
                ? 'Try another search or reset your filters.'
                : 'Upload your files to start tracking an audit, or explore the sample workspace.'}
            </p>
            <button
              className="v2-text-button"
              onClick={
                documents.length
                  ? () => {
                      setSearch('')
                      setFilter('all')
                    }
                  : onLoadDemoData
              }
            >
              {documents.length ? 'Reset filters' : 'Explore sample workspace'}{' '}
              <ArrowRight size={15} />
            </button>
          </div>
        )}

        <div className="v2-table-footer">
          <span>
            Showing {filtered.length} of {documents.length} documents
          </span>
          <label>
            <ListFilter size={14} />
            <select
              aria-label="Sort documents"
              value={sort}
              onChange={(e) => setSort(e.target.value)}
            >
              <option value="priority">Attention first</option>
              <option value="name">Document name</option>
            </select>
          </label>
        </div>
      </section>

      {executiveSummary && (
        <details className="v2-summary">
          <summary>Read the audit summary</summary>
          <p>{executiveSummary}</p>
        </details>
      )}
    </div>
  )
}
