import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  FileSearch,
  Send,
  ShieldCheck,
  User,
  Search,
  Maximize2,
  X,
  Sparkles,
  FileText
} from 'lucide-react'
import type { DocumentAuditResult } from '../types/audit'
import { askAuditCopilotV2 } from '../api/api_v2'
import { ContradictionList } from '../components/ContradictionList'
import { EvidenceTrail } from '../components/EvidenceTrail'
import { FailedRulesList } from '../components/FailedRulesList'
import { FlatCard } from '../components/FlatCard'
import { ScoreDisplay } from '../components/ScoreDisplay'
import { StatusBadge } from '../components/StatusBadge'

import { CorrectionPanel } from '../components/CorrectionPanel'

interface AuditWorkspaceProps {
  documents: DocumentAuditResult[]
  selectedId: string | null
  onSelect: (documentId: string) => void
}

type ChatMessage = { role: 'user' | 'assistant'; content: string }

const COPILOT_SUGGESTIONS = [
  'Why does this document require review?',
  'Summarize the compliance findings',
  'What evidence supports the grand total?',
  'Were any grounding rejections detected?',
]

export function AuditWorkspace({ documents, selectedId, onSelect }: AuditWorkspaceProps) {
  const selected = documents.find((doc) => doc.document_id === selectedId) ?? documents[0]
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [asking, setAsking] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterMode, setFilterMode] = useState<'all' | 'attention' | 'passed'>('all')
  const [previewModalOpen, setPreviewModalOpen] = useState(false)

  useEffect(() => {
    setHistory([])
    setQuestion('')
  }, [selected?.document_id])

  if (!selected) {
    return (
      <FlatCard>
        <div className="py-16 text-center">
          <div className="w-12 h-12 rounded-2xl bg-teal-500/10 text-teal-600 dark:text-teal-400 mx-auto flex items-center justify-center mb-4">
            <FileSearch className="w-6 h-6" />
          </div>
          <h3 className="text-[17px] font-bold text-ink">No document selected</h3>
          <p className="text-[13px] text-muted mt-1.5 max-w-md mx-auto">
            Upload documents or load the sample audit dossier to inspect deep deterministic and vision evidence trails.
          </p>
        </div>
      </FlatCard>
    )
  }

  async function sendQuestion(promptText?: string) {
    const prompt = (promptText ?? question).trim()
    if (!prompt || asking) return
    const next = [...history, { role: 'user' as const, content: prompt }]
    setHistory(next)
    setQuestion('')
    setAsking(true)
    try {
      const result = await askAuditCopilotV2(selected.document_id, prompt, next)
      setHistory([...next, { role: 'assistant', content: result.answer }])
    } catch (error) {
      setHistory([
        ...next,
        {
          role: 'assistant',
          content: error instanceof Error ? error.message : 'Copilot is unavailable.',
        },
      ])
    } finally {
      setAsking(false)
    }
  }

  const coverageLabel = selected.coverage_complete
    ? `${selected.pages_examined}/${selected.page_count} pages examined`
    : `${selected.pages_examined}/${selected.page_count} pages examined`

  const filteredDocuments = documents.filter((doc) => {
    const matchesSearch =
      doc.document_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.document_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.document_type.toLowerCase().includes(searchQuery.toLowerCase())

    if (!matchesSearch) return false
    if (filterMode === 'attention') return doc.human_review_recommended || !doc.passed
    if (filterMode === 'passed') return doc.passed && !doc.human_review_recommended
    return true
  })

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[330px_minmax(0,1fr)] gap-6 items-start">
      {/* Left Dossier Sidebar */}
      <aside className="space-y-4 xl:sticky xl:top-20">
        <FlatCard className="p-4!">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-teal-600 dark:text-teal-400" />
              <h3 className="text-[13px] font-bold uppercase tracking-wider text-muted">
                Documents
              </h3>
            </div>
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-surface-1 border border-border font-mono font-medium text-ink">
              {documents.length} Files
            </span>
          </div>

          {/* Search bar inside dossier list */}
          <div className="relative mb-2.5">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Search documents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-lg text-[12px] bg-surface-1 border border-border text-ink placeholder:text-muted/60 focus:outline-none focus:border-teal-500"
            />
          </div>

          {/* Quick filter tabs */}
          <div className="flex items-center gap-1 mb-3 p-1 rounded-lg bg-surface-1 border border-border text-[11px]">
            <button
              onClick={() => setFilterMode('all')}
              className={`flex-1 py-1 rounded text-center font-medium transition-all cursor-pointer ${
                filterMode === 'all'
                  ? 'bg-surface-2 text-ink shadow-xs'
                  : 'text-muted hover:text-ink'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setFilterMode('attention')}
              className={`flex-1 py-1 rounded text-center font-medium transition-all cursor-pointer ${
                filterMode === 'attention'
                  ? 'bg-coral-500/15 text-coral-600 dark:text-coral-400 shadow-xs'
                  : 'text-muted hover:text-ink'
              }`}
            >
              Review
            </button>
            <button
              onClick={() => setFilterMode('passed')}
              className={`flex-1 py-1 rounded text-center font-medium transition-all cursor-pointer ${
                filterMode === 'passed'
                  ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 shadow-xs'
                  : 'text-muted hover:text-ink'
              }`}
            >
              Passed
            </button>
          </div>

          {/* Dossier Items List */}
          <div className="space-y-1.5 max-h-[300px] overflow-y-auto pr-1">
            {filteredDocuments.length === 0 ? (
              <p className="text-[12px] text-muted text-center py-6">No matching documents</p>
            ) : (
              filteredDocuments.map((doc) => (
                <button
                  key={doc.document_id}
                  onClick={() => onSelect(doc.document_id)}
                  className={`w-full flex items-center justify-between gap-2.5 rounded-xl border p-2.5 text-left transition-all cursor-pointer ${
                    selected.document_id === doc.document_id
                      ? 'border-teal-500/50 bg-teal-500/10 dark:bg-teal-500/15 text-ink shadow-xs'
                      : 'border-border/70 bg-surface-1/60 hover:bg-surface-1 text-muted hover:text-ink'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-ink">
                      {doc.document_name}
                    </span>
                    <span className="block text-[11px] text-muted font-mono truncate">
                      {doc.document_type.replaceAll('_', ' ')}
                    </span>
                  </div>
                  <StatusBadge passed={doc.passed} status={doc.document_status} />
                </button>
              ))
            )}
          </div>
        </FlatCard>

        {/* Score & Meta Summary Card */}
        <FlatCard className="p-4!">
          <div className="flex items-center justify-between gap-2 mb-3 pb-2.5 border-b border-border/60">
            <div>
              <span className="text-[10.5px] uppercase tracking-wider font-semibold text-muted">
                Document Type
              </span>
              <p className="text-[14.5px] font-bold text-ink capitalize mt-0.5">
                {selected.document_type.replaceAll('_', ' ')}
              </p>
            </div>
            <StatusBadge passed={selected.passed} status={selected.document_status} label={selected.audit_status?.replaceAll('_', ' ')} />
          </div>

          <ScoreDisplay score={selected.score} interval={selected.prediction_interval} />

          <dl className="grid grid-cols-2 gap-2.5 mt-4 text-[12px] p-3 rounded-xl bg-surface-1 border border-border">
            <div>
              <dt className="text-muted text-[11px]">Audit Coverage</dt>
              <dd className="text-ink font-medium mt-0.5">{coverageLabel}</dd>
            </div>
            <div>
              <dt className="text-muted text-[11px]">Risk Grade</dt>
              <dd className="text-ink font-medium mt-0.5">{selected.risk_level}</dd>
            </div>
            <div>
              <dt className="text-muted text-[11px]">Vision Backend</dt>
              <dd className="text-ink font-medium mt-0.5">{selected.vision_backend || 'Balanced'}</dd>
            </div>
            <div>
              <dt className="text-muted text-[11px]">Human Review</dt>
              <dd
                className={`font-medium mt-0.5 ${
                  selected.human_review_recommended ? 'text-amber-600 font-bold' : 'text-emerald-600'
                }`}
              >
                {selected.human_review_recommended ? 'Required' : 'Clear'}
              </dd>
            </div>
          </dl>
        </FlatCard>

        {/* First page visual preview thumbnail */}
        {selected.preview_base64 && (
          <FlatCard className="p-4!">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
                Source Document
              </span>
              <button
                onClick={() => setPreviewModalOpen(true)}
                className="text-teal-600 dark:text-teal-400 hover:text-teal-700 flex items-center gap-1 text-[11px] font-medium cursor-pointer"
              >
                <Maximize2 className="w-3 h-3" /> Expand
              </button>
            </div>
            <div
              onClick={() => setPreviewModalOpen(true)}
              className="h-64 rounded-xl overflow-hidden bg-white border border-border flex items-center justify-center cursor-pointer group relative"
            >
              <img
                src={`data:image/jpeg;base64,${selected.preview_base64}`}
                alt={`Page 1 of ${selected.document_name}`}
                className="w-full h-full object-contain transition-transform group-hover:scale-105 duration-200"
              />
              <div className="absolute inset-0 bg-slate-900/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <span className="px-3 py-1.5 rounded-full bg-slate-900/90 text-white text-[12px] font-semibold flex items-center gap-1.5 shadow-md">
                  <Maximize2 className="w-3.5 h-3.5" /> View High-Res
                </span>
              </div>
            </div>
          </FlatCard>
        )}
      </aside>

      {/* Right Main Dossier Content */}
      <section className="space-y-5 min-w-0">
        {selected.document_id.startsWith('doc_') && <CorrectionPanel key={selected.document_id} documentId={selected.document_id} pageCount={selected.page_count} />}
        {selected.decision && <section className="v2-panel p-5" aria-label="Audit decision">
          <h2 className="text-lg font-semibold">{selected.decision.status.replaceAll('_', ' ')}</h2>
          <p className="text-sm text-muted mt-2">{selected.decision.scope}</p>
          <p className="text-sm mt-3">Mandatory checks completed: {selected.decision.completed_checks} / {selected.decision.required_checks}</p>
          <ul className="mt-3 space-y-2 text-sm">{selected.decision.blockers.map((b,i) => <li key={i} className="border-l-2 border-amber-500 pl-3">{b}</li>)}</ul>
          {selected.cross_check && <p className="text-xs text-muted mt-4">Additional evidence cross-check: {selected.cross_check.execution_status.replaceAll('_',' ')}{selected.cross_check.partial ? ' (partial evidence inspected)' : ''}</p>}
          <details className="mt-4"><summary className="cursor-pointer text-sm">View every check</summary><div className="space-y-3 mt-3">{selected.check_results?.map(c => <div key={c.check_id} className="border-t border-border pt-3 text-xs"><strong>{c.check_id} · {c.status.replaceAll('_',' ')}</strong><p className="text-muted mt-1">{c.message}</p>{c.coverage?.required_lines !== undefined && <p>{c.coverage.matched_lines} / {c.coverage.required_lines} lines matched</p>}</div>)}</div></details>
        </section>}
        {/* Classification Gate Alert */}
        <div
          className={`rounded-2xl border p-4.5 flex items-start gap-3.5 shadow-xs ${
            selected.classification_status === 'CONFIRMED'
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200'
              : selected.classification_status === 'UNSUPPORTED'
                ? 'border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300'
                : 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-200'
          }`}
        >
          {selected.classification_status === 'CONFIRMED' ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          )}
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] uppercase tracking-widest font-bold">
                Classification Gate
              </span>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-surface-2/80 border border-current/20">
                {selected.classification_status}
              </span>
            </div>
            <p className="text-[13px] mt-1 leading-relaxed">
              {selected.classification_status === 'CONFIRMED'
                ? `${selected.document_type.replaceAll('_', ' ')} verified from ${
                    selected.classification_method ?? 'deterministic evidence'
                  } at ${Math.round((selected.classification_confidence ?? 0) * 100)}% confidence.`
                : `Deterministic checks held: classification is ${(
                    selected.classification_status ?? 'unconfirmed'
                  ).toLowerCase()}. Human review required.`}
            </p>
            {(selected.alternative_types?.length ?? 0) > 0 && (
              <p className="text-[12px] mt-1 opacity-85 font-mono">
                Alternate candidates: {selected.alternative_types?.join(', ')}
              </p>
            )}
          </div>
        </div>

        {/* Document Overview Card */}
        <FlatCard>
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div className="min-w-0">
              <span className="text-[11px] uppercase tracking-widest font-semibold text-muted">
                Document overview
              </span>
              <h2 className="text-[22px] font-bold text-ink mt-0.5 break-words">
                {selected.document_name}
              </h2>
            </div>
          </div>
          <p className="text-[14px] leading-relaxed text-ink mt-4 bg-surface-1 p-4 rounded-xl border border-border/70">
            {selected.summary_text}
          </p>

          <div className="mt-4 pt-3.5 border-t border-border/60">
            <span className="text-[11px] uppercase tracking-wider font-semibold text-muted block mb-1">
              What needs attention
            </span>
            <p className="text-[13px] leading-relaxed text-muted">
              {selected.risk_explanation}
            </p>
          </div>
        </FlatCard>

        {/* Compliance Findings */}
        <FlatCard>
          <div className="flex items-center justify-between border-b border-border/60 pb-3 mb-4">
            <div>
              <span className="text-[11px] uppercase tracking-wider font-semibold text-muted">
                Audit Findings Engine
              </span>
              <h3 className="text-[18px] font-bold text-ink mt-0.5">Rule Compliance Results</h3>
            </div>
            <span className="text-[12px] font-medium px-2.5 py-1 rounded-full bg-surface-1 border border-border text-ink">
              {selected.failed_rules.length} finding(s)
            </span>
          </div>
          <FailedRulesList rules={selected.failed_rules} />
        </FlatCard>

        {/* Grounding Rejections */}
        {(selected.grounding_rejections?.length ?? 0) > 0 && (
          <FlatCard glow="coral">
            <details open className="group">
              <summary className="cursor-pointer text-[14.5px] font-semibold text-coral-600 dark:text-coral-400 flex items-center justify-between">
                <span>Grounding Rejections ({selected.grounding_rejection_count})</span>
                <span className="text-[11px] text-muted group-open:rotate-180 transition-transform">▼</span>
              </summary>
              <ul className="mt-3.5 space-y-2 text-[13px] text-muted">
                {selected.grounding_rejections?.map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <span className="text-coral-500 mt-0.5">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </details>
          </FlatCard>
        )}

        {/* Extraction Disagreements */}
        {Object.keys(selected.extraction_disagreements ?? {}).length > 0 && (
          <FlatCard glow="blue">
            <details open className="group">
              <summary className="cursor-pointer text-[14.5px] font-semibold text-blue-600 dark:text-blue-400 flex items-center justify-between">
                <span>
                  Dual-Extraction Field Disagreements (
                  {Object.keys(selected.extraction_disagreements ?? {}).length})
                </span>
                <span className="text-[11px] text-muted group-open:rotate-180 transition-transform">▼</span>
              </summary>
              <div className="mt-3.5 grid grid-cols-1 sm:grid-cols-2 gap-3">
                {Object.entries(selected.extraction_disagreements ?? {}).map(([field, detail]) => (
                  <div key={field} className="rounded-xl border border-border bg-surface-1 p-3">
                    <span className="font-mono text-[11px] text-teal-600 dark:text-teal-400 font-semibold block">
                      {field}
                    </span>
                    <span className="text-ink text-[12.5px] mt-1 block">{String(detail)}</span>
                  </div>
                ))}
              </div>
            </details>
          </FlatCard>
        )}

        {/* Contradictions */}
        <ContradictionList contradictions={selected.contradictions ?? []} />

        {/* Evidence Trail */}
        <EvidenceTrail evidences={selected.evidences ?? []} />

        {/* Auditor Copilot */}
        <FlatCard glow="teal">
          <div className="flex items-center justify-between border-b border-border/60 pb-3 mb-3">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-gradient-to-br from-teal-500 to-emerald-600 text-white shadow-xs">
                <Bot className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-[15px] font-bold text-ink">Auditor Forensic Copilot</h3>
                <p className="text-[11px] text-muted">
                  Grounded strictly in this document dossier and verified cross-checks
                </p>
              </div>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-teal-500/10 text-teal-600 font-semibold border border-teal-500/20">
              Deterministic V2 Mode
            </span>
          </div>

          {/* Quick suggestions chips */}
          <div className="flex flex-wrap gap-1.5 mb-3">
            {COPILOT_SUGGESTIONS.map((sug) => (
              <button
                key={sug}
                onClick={() => void sendQuestion(sug)}
                disabled={asking}
                className="text-[11px] px-2.5 py-1 rounded-lg bg-surface-1 hover:bg-surface-3 border border-border text-muted hover:text-ink transition-all cursor-pointer"
              >
                {sug}
              </button>
            ))}
          </div>

          {/* Chat messages */}
          <div className="h-72 overflow-y-auto py-3 space-y-3 pr-1" aria-live="polite">
            {history.length === 0 && (
              <div className="text-center py-16 text-muted">
                <Sparkles className="w-6 h-6 mx-auto mb-2 text-teal-500/60" />
                <p className="text-[13px] font-medium text-ink">How can Copilot assist your audit?</p>
                <p className="text-[12px] mt-1 text-muted">
                  Click a suggested prompt above or query extracted math, rules, and grounding.
                </p>
              </div>
            )}
            {history.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`flex gap-2.5 ${
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                {message.role === 'assistant' && (
                  <div className="w-6 h-6 rounded-lg bg-teal-500/15 text-teal-600 flex items-center justify-center shrink-0 mt-1">
                    <Bot className="w-3.5 h-3.5" />
                  </div>
                )}
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed ${
                    message.role === 'user'
                      ? 'bg-gradient-to-r from-teal-600 to-emerald-600 text-white shadow-xs'
                      : 'bg-surface-1 border border-border text-ink'
                  }`}
                >
                  {message.content}
                </div>
                {message.role === 'user' && (
                  <div className="w-6 h-6 rounded-lg bg-blue-500/15 text-blue-600 flex items-center justify-center shrink-0 mt-1">
                    <User className="w-3.5 h-3.5" />
                  </div>
                )}
              </div>
            ))}
            {asking && (
              <div className="flex items-center gap-2 text-[12px] text-muted animate-pulse">
                <Bot className="w-3.5 h-3.5 text-teal-600" />
                <span>Auditing dossier and cross-referencing rule evidence…</span>
              </div>
            )}
          </div>

          {/* Input field */}
          <div className="flex gap-2 pt-3 border-t border-border/60">
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void sendQuestion()
              }}
              maxLength={500}
              placeholder="Ask Copilot about any line item, variance, or rule decision..."
              className="flex-1 rounded-xl border border-border bg-surface-1 px-3.5 py-2 text-[13px] text-ink outline-none focus:border-teal-500 transition-colors"
            />
            <button
              onClick={() => void sendQuestion()}
              disabled={!question.trim() || asking}
              className="rounded-xl bg-gradient-to-r from-teal-500 to-emerald-600 text-white px-4 py-2 disabled:opacity-40 cursor-pointer shadow-xs active:scale-95 transition-all"
              aria-label="Send query"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </FlatCard>
      </section>

      {/* High-Res Preview Modal */}
      {previewModalOpen && selected.preview_base64 && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
          <div className="bg-surface-2 border border-border rounded-2xl max-w-4xl w-full max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-border">
              <span className="font-semibold text-[15px] text-ink truncate mr-3">
                {selected.document_name} — High Resolution Source Preview
              </span>
              <button
                onClick={() => setPreviewModalOpen(false)}
                className="p-1.5 rounded-lg hover:bg-surface-3 text-muted hover:text-ink cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4 bg-slate-900/10 flex items-center justify-center">
              <img
                src={`data:image/jpeg;base64,${selected.preview_base64}`}
                alt={`First page of ${selected.document_name}`}
                className="max-h-[75vh] w-auto object-contain rounded-lg shadow-lg border border-border"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
