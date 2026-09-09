import React, { useEffect, useState } from 'react'
import {
  Users,
  RefreshCw,
  CheckCircle2,
  XCircle,
  ArrowUpRight,
  Sparkles,
  ShieldCheck,
  Clock
} from 'lucide-react'
import { fetchReviewQueueV2, submitReviewV2 } from '../api/api_v2'
import type { ReviewQueueResponse } from '../api/api_v2'
import { FlatCard } from '../components/FlatCard'

export const ReviewQueueSection: React.FC = () => {
  const [queueData, setQueueData] = useState<ReviewQueueResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [actionStatus, setActionStatus] = useState<string | null>(null)
  const [commentText, setCommentText] = useState('')

  useEffect(() => {
    loadQueue()
  }, [])

  async function loadQueue() {
    try {
      setLoading(true)
      const data = await fetchReviewQueueV2()
      setQueueData(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch review queue')
    } finally {
      setLoading(false)
    }
  }

  async function handleAction(
    itemId: string,
    action: 'confirm' | 'reject_as_false_positive' | 'escalate'
  ) {
    try {
      setActionStatus(`Processing ${action}...`)
      await submitReviewV2(itemId, action, 'auditor_lead', commentText || undefined, queueData?.pending_items.find(i => i.item_id === itemId)?.version || 0)
      setActionStatus(
        action === 'reject_as_false_positive'
          ? 'Review recorded as a feedback candidate. The original audit finding is preserved.'
          : `Action "${action}" recorded cleanly.`
      )
      setCommentText('')
      await loadQueue()
      setTimeout(() => setActionStatus(null), 4000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    }
  }

  return (
    <div className="space-y-6">
      <FlatCard>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-border/60">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-[18px] font-bold text-ink">
                Human Review Queue & Golden Set Feedback Engine
              </h2>
              <p className="text-[12.5px] text-muted">
                Disagreements and high-stakes variances triage with automated candidate golden-set regression loop.
              </p>
            </div>
          </div>

          <button
            onClick={loadQueue}
            disabled={loading}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-[12.5px] font-semibold border border-border bg-surface-1 hover:bg-surface-3 text-ink transition-all cursor-pointer shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh Queue
          </button>
        </div>

        {/* Priority Formula Explainer Banner */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
          <div className="p-3.5 rounded-xl bg-surface-1 border border-border">
            <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
              Triage Algorithm
            </span>
            <div className="font-mono text-[13px] font-semibold text-teal-600 dark:text-teal-400 mt-0.5">
              severity × value × age
            </div>
            <p className="text-[11px] text-muted mt-1">
              Prioritizes high financial exposure & aging items.
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-surface-1 border border-border">
            <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
              Pending Review Items
            </span>
            <div className="text-[20px] font-bold text-ink font-mono mt-0.5">
              {queueData?.count ?? 0} Item(s)
            </div>
            <p className="text-[11px] text-muted mt-1">Awaiting human sign-off</p>
          </div>

          <div className="p-3.5 rounded-xl bg-gradient-to-br from-teal-500/10 to-emerald-500/10 border border-teal-500/30">
            <span className="text-[11px] font-bold uppercase tracking-wider text-teal-700 dark:text-teal-300 flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> Candidate Golden Set
            </span>
            <div className="text-[20px] font-bold text-teal-600 dark:text-teal-400 font-mono mt-0.5">
              {queueData?.golden_set_candidates_count ?? 0} Fixture(s)
            </div>
            <p className="text-[11px] text-muted mt-1">
              False positives automatically fed into test suite
            </p>
          </div>
        </div>

        {actionStatus && (
          <div className="mb-4 p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300 text-[13px] flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{actionStatus}</span>
          </div>
        )}

        {error && (
          <div className="mb-4 p-3.5 rounded-xl bg-coral-500/10 border border-coral-500/30 text-coral-600 text-[13px]">
            {error}
          </div>
        )}

        {queueData && queueData.pending_items.length === 0 && (
          <div className="text-center py-14 border border-dashed border-border rounded-2xl">
            <ShieldCheck className="w-10 h-10 text-emerald-500/70 mx-auto mb-2" />
            <h4 className="text-[15px] font-bold text-ink">Review Queue Clear</h4>
            <p className="text-[13px] text-muted mt-1 max-w-sm mx-auto">
              All documents and cross-check rules passed deterministic validation with no triage flags.
            </p>
          </div>
        )}

        {/* Pending Items List */}
        {queueData && queueData.pending_items.length > 0 && (
          <div className="space-y-3.5">
            {queueData.pending_items.map((item) => (
              <div
                key={item.item_id}
                className="p-4.5 rounded-2xl bg-surface-1 border border-border hover:border-border-bright transition-all shadow-xs"
              >
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/30">
                        Priority: {item.priority_score.toFixed(1)}
                      </span>
                      <span className="font-mono font-semibold text-[12px] text-ink">
                        {item.finding?.check_id || 'CHK-TRIAGE-001'}
                      </span>
                      <span className="text-muted text-[11px] flex items-center gap-1 font-mono">
                        <Clock className="w-3 h-3" />
                        {new Date(item.created_at).toLocaleTimeString()}
                      </span>
                    </div>

                    <div className="text-[14px] font-semibold text-ink leading-snug">
                      {item.finding?.message || 'Extracted field disagreement flagged for verification'}
                    </div>

                    <div className="text-[12px] text-muted font-mono">
                      Target Document: <span className="text-ink font-medium">{item.document_id}</span>
                    </div>
                  </div>

                  {/* Decision Action Buttons */}
                  <div className="flex items-center gap-2 shrink-0 flex-wrap">
                    <button
                      onClick={() => handleAction(item.item_id, 'confirm')}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-[12px] font-semibold bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 transition-all cursor-pointer"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Confirm Violation
                    </button>

                    <button
                      onClick={() => handleAction(item.item_id, 'reject_as_false_positive')}
                      title="Mark as false positive and add to Golden Set fixtures"
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-[12px] font-semibold bg-coral-500/10 hover:bg-coral-500/20 text-coral-600 dark:text-coral-400 border border-coral-500/30 transition-all cursor-pointer"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      Reject (False Alarm)
                    </button>

                    <button
                      onClick={() => handleAction(item.item_id, 'escalate')}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-[12px] font-semibold bg-blue-500/10 hover:bg-blue-500/20 text-blue-600 dark:text-blue-400 border border-blue-500/30 transition-all cursor-pointer"
                    >
                      <ArrowUpRight className="w-3.5 h-3.5" />
                      Escalate
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </FlatCard>
    </div>
  )
}
