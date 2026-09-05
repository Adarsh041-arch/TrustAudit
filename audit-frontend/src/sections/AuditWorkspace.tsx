import { useEffect, useState } from 'react'
import { AlertTriangle, Bot, CheckCircle2, FileSearch, Send, ShieldCheck, User } from 'lucide-react'
import type { DocumentAuditResult } from '../types/audit'
import { askAuditCopilotV2 } from '../api/api_v2'
import { ContradictionList } from '../components/ContradictionList'
import { EvidenceTrail } from '../components/EvidenceTrail'
import { FailedRulesList } from '../components/FailedRulesList'
import { FlatCard } from '../components/FlatCard'
import { ScoreDisplay } from '../components/ScoreDisplay'
import { StatusBadge } from '../components/StatusBadge'

interface AuditWorkspaceProps {
  documents: DocumentAuditResult[]
  selectedId: string | null
  onSelect: (documentId: string) => void
}

type ChatMessage = { role: 'user' | 'assistant'; content: string }

export function AuditWorkspace({ documents, selectedId, onSelect }: AuditWorkspaceProps) {
  const selected = documents.find((doc) => doc.document_id === selectedId) ?? documents[0]
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [asking, setAsking] = useState(false)

  useEffect(() => {
    setHistory([])
    setQuestion('')
  }, [selected?.document_id])

  if (!selected) {
    return (
      <FlatCard>
        <div className="py-14 text-center">
          <FileSearch className="w-8 h-8 mx-auto text-muted mb-3" />
          <p className="text-[14px] text-ink font-medium">No audit dossier yet</p>
          <p className="text-[13px] text-muted mt-1">Upload documents to inspect their evidence and findings.</p>
        </div>
      </FlatCard>
    )
  }

  async function sendQuestion() {
    const prompt = question.trim()
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
        { role: 'assistant', content: error instanceof Error ? error.message : 'Copilot is unavailable.' },
      ])
    } finally {
      setAsking(false)
    }
  }

  const coverageLabel = selected.coverage_complete
    ? `${selected.pages_examined}/${selected.page_count} pages verified`
    : `${selected.pages_examined}/${selected.page_count} pages examined`

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-5 items-start">
      <aside className="space-y-4 xl:sticky xl:top-4">
        <FlatCard>
          <div className="flex items-center justify-between mb-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">Audit dossier</p>
            <span className="text-[11px] text-muted">{documents.length} files</span>
          </div>
          <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
            {documents.map((doc) => (
              <button
                key={doc.document_id}
                onClick={() => onSelect(doc.document_id)}
                className={`w-full flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-teal-600/30 ${
                  selected.document_id === doc.document_id
                    ? 'border-teal-600/40 bg-teal-50/70'
                    : 'border-border bg-surface-1 hover:bg-surface-2'
                }`}
              >
                <span className="truncate text-[12.5px] text-ink">{doc.document_name}</span>
                <StatusBadge passed={doc.passed} status={doc.document_status} />
              </button>
            ))}
          </div>
        </FlatCard>

        <FlatCard>
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted">Decision</p>
              <p className="text-[14px] font-medium text-ink mt-0.5">{selected.document_type.replaceAll('_', ' ')}</p>
            </div>
            <StatusBadge passed={selected.passed} status={selected.document_status} />
          </div>
          <ScoreDisplay score={selected.score} interval={selected.prediction_interval} />
          <dl className="grid grid-cols-2 gap-x-3 gap-y-3 mt-5 text-[12px]">
            <div><dt className="text-muted">Coverage</dt><dd className="text-ink mt-0.5">{coverageLabel}</dd></div>
            <div><dt className="text-muted">Risk</dt><dd className="text-ink mt-0.5">{selected.risk_level}</dd></div>
            <div><dt className="text-muted">Vision</dt><dd className="text-ink mt-0.5">{selected.vision_backend || 'None'}</dd></div>
            <div><dt className="text-muted">Review</dt><dd className="text-ink mt-0.5">{selected.human_review_recommended ? 'Required' : 'Not required'}</dd></div>
          </dl>
        </FlatCard>

        {selected.preview_base64 && (
          <FlatCard>
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted mb-3">Source preview</p>
            <div className="h-72 rounded-lg overflow-hidden bg-white border border-border flex items-center justify-center">
              <img
                src={`data:image/jpeg;base64,${selected.preview_base64}`}
                alt={`First page of ${selected.document_name}`}
                className="w-full h-full object-contain"
              />
            </div>
          </FlatCard>
        )}
      </aside>

      <section className="space-y-5 min-w-0">
        <div className={`rounded-xl border px-4 py-3 flex items-start gap-3 ${
          selected.classification_status === 'CONFIRMED'
            ? 'border-teal-600/25 bg-teal-50/70 text-teal-800'
            : selected.classification_status === 'UNSUPPORTED'
              ? 'border-slate-300 bg-slate-100 text-slate-700'
              : 'border-amber-500/30 bg-amber-50 text-amber-800'
        }`}>
          {selected.classification_status === 'CONFIRMED'
            ? <CheckCircle2 className="w-5 h-5 mt-0.5 shrink-0" />
            : <AlertTriangle className="w-5 h-5 mt-0.5 shrink-0" />}
          <div>
            <p className="text-[11px] uppercase tracking-[0.14em] font-semibold">Classification gate</p>
            <p className="text-[13px] mt-1">
              {selected.classification_status === 'CONFIRMED'
                ? `${selected.document_type.replaceAll('_', ' ')} confirmed from ${selected.classification_method ?? 'document evidence'} at ${Math.round((selected.classification_confidence ?? 0) * 100)}% confidence.`
                : `Compliance checks are paused: classification is ${(selected.classification_status ?? 'unconfirmed').toLowerCase()}. Human review must confirm the document type.`}
            </p>
            {(selected.alternative_types?.length ?? 0) > 0 && <p className="text-[12px] mt-1 opacity-80">Possible types: {selected.alternative_types?.join(', ')}</p>}
          </div>
        </div>
        <FlatCard>
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-teal-50 text-teal-600"><ShieldCheck className="w-5 h-5" /></div>
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Document overview</p>
              <h2 className="text-[21px] font-medium text-ink mt-1 break-words">{selected.document_name}</h2>
            </div>
          </div>
          <p className="text-[14px] leading-6 text-ink mt-5">{selected.summary_text}</p>
          <div className="mt-4 pt-4 border-t border-border/60">
            <p className="text-[11px] uppercase tracking-[0.12em] text-muted mb-1">Deterministic risk notes</p>
            <p className="text-[13px] leading-5 text-muted">{selected.risk_explanation}</p>
          </div>
        </FlatCard>

        <FlatCard>
          <div className="flex items-center justify-between border-b border-border/60 pb-3 mb-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Decision record</p>
              <h3 className="text-[17px] font-medium text-ink mt-1">Compliance findings</h3>
            </div>
            <span className="text-[12px] text-muted">{selected.failed_rules.length} finding(s)</span>
          </div>
          <FailedRulesList rules={selected.failed_rules} />
        </FlatCard>

        {(selected.grounding_rejections?.length ?? 0) > 0 && (
          <FlatCard>
            <details open>
              <summary className="cursor-pointer text-[14px] font-medium text-amber-700">
                Grounding rejections ({selected.grounding_rejection_count})
              </summary>
              <ul className="mt-3 space-y-2 text-[12.5px] text-muted">
                {selected.grounding_rejections?.map((item) => <li key={item}>• {item}</li>)}
              </ul>
            </details>
          </FlatCard>
        )}

        {Object.keys(selected.extraction_disagreements ?? {}).length > 0 && (
          <FlatCard>
            <details>
              <summary className="cursor-pointer text-[14px] font-medium text-amber-700">
                Extraction disagreements ({Object.keys(selected.extraction_disagreements ?? {}).length})
              </summary>
              <dl className="mt-3 space-y-2 text-[12.5px]">
                {Object.entries(selected.extraction_disagreements ?? {}).map(([field, detail]) => (
                  <div key={field} className="rounded-lg border border-border bg-surface-1 p-3">
                    <dt className="font-mono text-[11px] text-ink">{field}</dt>
                    <dd className="text-muted mt-1">{detail}</dd>
                  </div>
                ))}
              </dl>
            </details>
          </FlatCard>
        )}

        <ContradictionList contradictions={selected.contradictions ?? []} />
        <FlatCard>
          <details>
            <summary className="cursor-pointer text-[14px] font-medium text-ink">
              Extraction performance
            </summary>
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 text-[12px]">
              <div><dt className="text-muted">Strategy</dt><dd className="text-ink mt-1">{selected.extraction_strategy?.replaceAll('_', ' ') ?? 'Unavailable'}</dd></div>
              <div><dt className="text-muted">Vision calls</dt><dd className="text-ink mt-1">{selected.vision_call_count ?? selected.glm_call_count ?? 0}</dd></div>
              <div><dt className="text-muted">Elapsed</dt><dd className="text-ink mt-1">{((selected.extraction_latency_ms ?? 0) / 1000).toFixed(2)}s</dd></div>
              <div><dt className="text-muted">Transcript cache</dt><dd className="text-ink mt-1">{selected.transcript_cache_hit ? 'Hit' : 'Miss'}</dd></div>
            </dl>
            {(selected.fallback_reasons?.length ?? 0) > 0 && (
              <p className="mt-3 text-[12px] text-amber-700">Fallback: {selected.fallback_reasons?.join(', ')}</p>
            )}
          </details>
        </FlatCard>
        <EvidenceTrail evidences={selected.evidences ?? []} />

        <FlatCard>
          <div className="flex items-center gap-3 border-b border-border/60 pb-3">
            <div className="p-2 rounded-lg bg-blue-50 text-blue-600"><Bot className="w-4 h-4" /></div>
            <div><h3 className="text-[14px] font-medium text-ink">Auditor Copilot</h3><p className="text-[11px] text-muted">Answers from this dossier only</p></div>
          </div>
          <div className="h-64 overflow-y-auto py-4 space-y-3" aria-live="polite">
            {history.length === 0 && <p className="text-[13px] text-muted text-center py-16">Ask about a finding, extracted value, or review requirement.</p>}
            {history.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`flex gap-2 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {message.role === 'assistant' && <Bot className="w-4 h-4 text-teal-600 mt-2 shrink-0" />}
                <p className={`max-w-[82%] rounded-xl px-3 py-2 text-[13px] leading-5 ${message.role === 'user' ? 'bg-teal-600 text-white' : 'bg-surface-1 border border-border text-ink'}`}>{message.content}</p>
                {message.role === 'user' && <User className="w-4 h-4 text-blue-600 mt-2 shrink-0" />}
              </div>
            ))}
            {asking && <p className="text-[12px] text-muted">Reviewing the dossier…</p>}
          </div>
          <div className="flex gap-2 pt-3 border-t border-border/60">
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') void sendQuestion() }}
              maxLength={500}
              placeholder="Why does this document need review?"
              className="flex-1 rounded-lg border border-border bg-surface-1 px-3 py-2 text-[13px] text-ink outline-none focus:border-teal-600"
            />
            <button onClick={() => void sendQuestion()} disabled={!question.trim() || asking} className="rounded-lg bg-teal-600 text-white px-3 py-2 disabled:opacity-40 cursor-pointer" aria-label="Send question"><Send className="w-4 h-4" /></button>
          </div>
        </FlatCard>
      </section>
    </div>
  )
}
