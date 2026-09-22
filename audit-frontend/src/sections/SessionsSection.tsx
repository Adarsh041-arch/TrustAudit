import { useState } from 'react'
import {
  History,
  Calendar,
  Clock,
  CheckCircle2,
  AlertTriangle,
  ScanLine,
  FileText,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Search,
  Plus,
  RefreshCw,
  Copy,
  Check,
  Layers,
  ExternalLink
} from 'lucide-react'
import type { AuditSessionSummary } from '../api/api_v2'
import { getDocumentStatus, formatDocumentScore } from '../utils/documentStatus'

interface Props {
  sessions: AuditSessionSummary[]
  activeSessionId: string | null
  isLoading?: boolean
  onSelectSession: (sessionId: string) => void
  onOpenWorkspace: (sessionId: string, documentId?: string) => void
  onNewAudit: () => void
  onRefresh?: () => void
}

export function SessionsSection({
  sessions,
  activeSessionId,
  isLoading,
  onSelectSession,
  onOpenWorkspace,
  onNewAudit,
  onRefresh,
}: Props) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'completed' | 'attention'>('all')
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copySessionId = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(id)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const formatTimestamp = (isoString: string) => {
    try {
      const date = new Date(isoString)
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return isoString
    }
  }

  const formatDuration = (start: string, end: string | null) => {
    if (!end) return null
    try {
      const s = new Date(start).getTime()
      const e = new Date(end).getTime()
      const diffSec = Math.max(0, Math.round((e - s) / 1000))
      if (diffSec < 60) return `${diffSec}s`
      const min = Math.floor(diffSec / 60)
      const sec = diffSec % 60
      return `${min}m ${sec}s`
    } catch {
      return null
    }
  }

  // Aggregate metrics across sessions
  const totalDocs = sessions.reduce((acc, s) => acc + (s.document_count || 0), 0)
  const totalPassed = sessions.reduce(
    (acc, s) => acc + (s.summary?.documents_passed ?? 0),
    0
  )
  const totalAttention = sessions.reduce(
    (acc, s) =>
      acc +
      ((s.summary?.documents_failed ?? 0) +
        (s.summary?.documents_incomplete ?? 0)),
    0
  )
  const overallPassRate =
    totalDocs > 0 ? Math.round((totalPassed / totalDocs) * 100) : 0

  // Filtered sessions
  const filtered = sessions.filter((s) => {
    if (statusFilter === 'completed' && s.status !== 'COMPLETED') return false
    if (statusFilter === 'attention') {
      const hasIssues =
        (s.summary?.documents_failed ?? 0) > 0 ||
        (s.summary?.documents_review_required ?? 0) > 0
      if (!hasIssues) return false
    }

    if (!search.trim()) return true
    const q = search.toLowerCase()
    const matchesId = s.session_id.toLowerCase().includes(q)
    const matchesDocs =
      s.summary?.documents.some((d) =>
        d.document_name.toLowerCase().includes(q)
      ) ?? false
    const matchesSummary =
      s.summary?.executive_summary?.toLowerCase().includes(q) ?? false
    return matchesId || matchesDocs || matchesSummary
  })

  return (
    <div className="v2-sessions-view space-y-6">
      {/* Top Header */}
      <div className="v2-page-heading">
        <div>
          <p className="v2-eyebrow">AUDIT HISTORY & SESSIONS</p>
          <h1>Audit Sessions</h1>
          <p>
            Browse previous audit runs, inspect historical results, and switch between sessions.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="v2-icon-button border border-border bg-surface-1"
              title="Refresh sessions"
              aria-label="Refresh sessions"
            >
              <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} />
            </button>
          )}
          <button className="v2-primary" onClick={onNewAudit}>
            <Plus size={17} /> New audit
          </button>
        </div>
      </div>

      {/* Metric Cards Banner */}
      <div className="v2-metrics">
        <div className="v2-stat">
          <div>
            <span>Total Sessions</span>
            <History size={19} className="text-teal-600" />
          </div>
          <strong>{sessions.length.toString().padStart(2, '0')}</strong>
          <small>Recorded in ledger</small>
        </div>

        <div className="v2-stat">
          <div>
            <span>Audited Documents</span>
            <FileText size={19} className="text-cyan-600" />
          </div>
          <strong>{totalDocs.toString().padStart(2, '0')}</strong>
          <small>Across all sessions</small>
        </div>

        <div className="v2-stat passed">
          <div>
            <span>Overall Passed</span>
            <CheckCircle2 size={19} className="text-emerald-600" />
          </div>
          <strong>{totalPassed.toString().padStart(2, '0')}</strong>
          <small>{overallPassRate}% overall pass rate</small>
        </div>

        <div className="v2-stat attention">
          <div>
            <span>Needing Review</span>
            <AlertTriangle size={19} className="text-amber-600" />
          </div>
          <strong>{totalAttention.toString().padStart(2, '0')}</strong>
          <small>Discrepancies flagged</small>
        </div>
      </div>

      {/* Main Sessions Panel */}
      <section className="v2-panel">
        <div className="v2-panel-heading">
          <div>
            <h2>
              Previous Audit Sessions{' '}
              <span className="v2-count">{sessions.length}</span>
            </h2>
            <p>Select any session to view its overview, inspect documents, or review trace.</p>
          </div>
          <span className="v2-register-label">
            <Clock size={15} /> Durable session ledger
          </span>
        </div>

        {/* Filter and Search Bar */}
        <div className="v2-table-tools">
          <div className="v2-filter-tabs" aria-label="Filter sessions">
            <button
              className={statusFilter === 'all' ? 'active' : ''}
              onClick={() => setStatusFilter('all')}
            >
              All Sessions <small>{sessions.length}</small>
            </button>
            <button
              className={statusFilter === 'completed' ? 'active' : ''}
              onClick={() => setStatusFilter('completed')}
            >
              Completed{' '}
              <small>
                {sessions.filter((s) => s.status === 'COMPLETED').length}
              </small>
            </button>
            <button
              className={statusFilter === 'attention' ? 'active' : ''}
              onClick={() => setStatusFilter('attention')}
            >
              Needs Attention{' '}
              <small>
                {
                  sessions.filter(
                    (s) =>
                      (s.summary?.documents_failed ?? 0) > 0 ||
                      (s.summary?.documents_review_required ?? 0) > 0
                  ).length
                }
              </small>
            </button>
          </div>

          <div className="v2-search">
            <Search size={16} />
            <input
              placeholder="Search by session ID or document…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search sessions"
            />
          </div>
        </div>

        {/* Sessions List */}
        <div className="p-4 sm:p-6 space-y-4">
          {filtered.length === 0 ? (
            <div className="v2-empty-results">
              <History size={32} />
              <strong>No audit sessions found</strong>
              <p>
                {sessions.length === 0
                  ? 'No audit sessions have been completed yet. Run your first audit to see sessions here.'
                  : 'No sessions match your search criteria.'}
              </p>
              {sessions.length === 0 ? (
                <button className="v2-primary mt-2" onClick={onNewAudit}>
                  <Plus size={16} /> Start first audit
                </button>
              ) : (
                <button
                  className="v2-text-button"
                  onClick={() => {
                    setSearch('')
                    setStatusFilter('all')
                  }}
                >
                  Reset filters
                </button>
              )}
            </div>
          ) : (
            filtered.map((s, idx) => {
              const isCurrent = s.session_id === activeSessionId
              const isLatest = idx === 0
              const isExpanded = expandedSessionId === s.session_id
              const duration = formatDuration(s.created_at, s.completed_at)
              const summary = s.summary

              return (
                <div
                  key={s.session_id}
                  className={`v2-session-card transition-all ${
                    isCurrent ? 'v2-session-card-active' : ''
                  }`}
                >
                  {/* Card Header Row */}
                  <div className="v2-session-card-header">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="flex items-center gap-1.5 font-mono font-bold text-[13px] text-ink">
                        <span>{s.session_id}</span>
                        <button
                          onClick={(e) => copySessionId(s.session_id, e)}
                          className="text-muted hover:text-ink p-1 rounded"
                          title="Copy session ID"
                          aria-label="Copy session ID"
                        >
                          {copiedId === s.session_id ? (
                            <Check size={13} className="text-emerald-600" />
                          ) : (
                            <Copy size={13} />
                          )}
                        </button>
                      </div>

                      {isCurrent && (
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider bg-teal-500/15 text-teal-600 border border-teal-500/30">
                          ACTIVE IN OVERVIEW
                        </span>
                      )}

                      {isLatest && !isCurrent && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-surface-1 text-muted border border-border">
                          LATEST RUN
                        </span>
                      )}

                      <span
                        className={`v2-status ${
                          s.status === 'COMPLETED'
                            ? 'passed'
                            : s.status === 'RUNNING'
                              ? 'incomplete'
                              : 'attention'
                        }`}
                      >
                        <i />
                        {s.status}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-[11px] text-muted">
                      <span className="flex items-center gap-1">
                        <Calendar size={13} />
                        {formatTimestamp(s.created_at)}
                      </span>
                      {duration && (
                        <span className="flex items-center gap-1 font-mono">
                          <Clock size={13} />
                          {duration}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Summary Metric Badges */}
                  <div className="v2-session-stats-bar">
                    <div className="v2-session-stat-pill">
                      <FileText size={14} className="text-muted" />
                      <span>
                        <strong>{s.document_count}</strong> documents
                      </span>
                    </div>

                    {summary && (
                      <>
                        <div className="v2-session-stat-pill text-emerald-600">
                          <CheckCircle2 size={14} />
                          <span>
                            <strong>{summary.documents_passed}</strong> passed
                          </span>
                        </div>

                        {summary.documents_failed > 0 && (
                          <div className="v2-session-stat-pill text-coral-600">
                            <AlertTriangle size={14} />
                            <span>
                              <strong>{summary.documents_failed}</strong> failed
                            </span>
                          </div>
                        )}

                        {summary.documents_incomplete > 0 && (
                          <div className="v2-session-stat-pill text-sky-600">
                            <ScanLine size={14} />
                            <span>
                              <strong>{summary.documents_incomplete}</strong>{' '}
                              incomplete
                            </span>
                          </div>
                        )}

                        {summary.findings_count > 0 && (
                          <div className="v2-session-stat-pill text-amber-600">
                            <Layers size={14} />
                            <span>
                              <strong>{summary.findings_count}</strong> findings
                            </span>
                          </div>
                        )}
                      </>
                    )}
                  </div>

                  {/* Executive Summary Snippet */}
                  {summary?.executive_summary && (
                    <p className="v2-session-summary-text">
                      {summary.executive_summary}
                    </p>
                  )}

                  {/* Document Chips Preview */}
                  {summary?.documents && summary.documents.length > 0 && (
                    <div className="v2-session-docs-row">
                      <span className="text-[11px] font-semibold text-muted shrink-0">
                        Documents:
                      </span>
                      <div className="flex flex-wrap gap-1.5 flex-1 min-w-0">
                        {summary.documents.map((d) => {
                          const s = getDocumentStatus(d as any);
                          const scoreInfo = formatDocumentScore(d as any);
                          const chipClass =
                            s.variant === 'passed' ? 'v2-doc-chip-pass'
                            : s.variant === 'attention' ? 'v2-doc-chip-fail'
                            : s.variant === 'review' ? 'v2-doc-chip-review'
                            : s.variant === 'incomplete' ? 'v2-doc-chip-incomplete'
                            : 'v2-doc-chip-unsupported';
                          return (
                            <span
                              key={d.document_id}
                              className={`v2-doc-chip ${chipClass}`}
                              title={`${d.document_name} (${d.document_type}) · ${s.label}`}
                            >
                              <FileText size={11} />
                              <span className="truncate max-w-[170px]">
                                {d.document_name}
                              </span>
                              <span className="opacity-90 font-semibold text-[10px]">
                                [{s.label}]
                              </span>
                              {scoreInfo.isNumeric && (
                                <small className="opacity-80 font-mono">
                                  {scoreInfo.value}
                                </small>
                              )}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Actions Footer */}
                  <div className="v2-session-card-actions">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => onSelectSession(s.session_id)}
                        className="v2-primary py-1.5 px-3 text-[12px]"
                      >
                        <ArrowUpRight size={14} />
                        {isCurrent ? 'Viewing in Overview' : 'Open in Overview'}
                      </button>

                      <button
                        onClick={() =>
                          setExpandedSessionId(
                            isExpanded ? null : s.session_id
                          )
                        }
                        className="v2-text-button px-2.5 py-1.5 text-[12px] border border-border rounded-lg bg-surface-1 hover:bg-surface-2"
                      >
                        {isExpanded ? (
                          <>
                            <span>Hide Details</span>
                            <ChevronUp size={14} />
                          </>
                        ) : (
                          <>
                            <span>Inspect Session</span>
                            <ChevronDown size={14} />
                          </>
                        )}
                      </button>
                    </div>

                    <button
                      onClick={() => onOpenWorkspace(s.session_id)}
                      className="v2-text-button text-[11px] text-muted hover:text-ink"
                    >
                      <ExternalLink size={13} />
                      Document Workspace
                    </button>
                  </div>

                  {/* Expanded Session Inspector */}
                  {isExpanded && summary?.documents && (
                    <div className="v2-session-expanded-panel mt-4 pt-4 border-t border-border">
                      <div className="flex items-center justify-between mb-2.5">
                        <h4 className="text-[13px] font-bold text-ink">
                          Session Documents Breakdown ({summary.documents.length})
                        </h4>
                        <span className="text-[11px] text-muted font-mono">
                          Session {s.session_id}
                        </span>
                      </div>

                      <div className="overflow-x-auto">
                        <table className="v2-document-table text-[11.5px]">
                          <thead>
                            <tr>
                              <th>Document</th>
                              <th>Type</th>
                              <th>Status</th>
                              <th>Score</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {summary.documents.map((doc) => (
                              <tr key={doc.document_id}>
                                <td className="font-semibold text-ink">
                                  {doc.document_name}
                                </td>
                                <td className="capitalize text-muted">
                                  {doc.document_type.replaceAll('_', ' ')}
                                </td>
                                <td>
                                  {(() => {
                                    const s = getDocumentStatus(doc as any);
                                    return (
                                      <span className={`v2-status ${s.variant}`}>
                                        <i />
                                        {s.label}
                                      </span>
                                    );
                                  })()}
                                </td>
                                <td className="font-mono">
                                  {(() => {
                                    const scoreInfo = formatDocumentScore(doc as any);
                                    return (
                                      <span className={`font-semibold ${scoreInfo.colorClass}`}>
                                        {scoreInfo.value}
                                      </span>
                                    );
                                  })()}
                                </td>
                                <td>
                                  <button
                                    onClick={() =>
                                      onOpenWorkspace(
                                        s.session_id,
                                        doc.document_id
                                      )
                                    }
                                    className="v2-text-button text-[11px]"
                                  >
                                    Inspect document <ArrowUpRight size={13} />
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      </section>
    </div>
  )
}
