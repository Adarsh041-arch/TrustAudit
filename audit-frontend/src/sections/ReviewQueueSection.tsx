import React, { useEffect, useState } from 'react'
import { fetchReviewQueueV2, submitReviewV2 } from '../api/api_v2'
import type { ReviewQueueResponse } from '../api/api_v2'


export const ReviewQueueSection: React.FC = () => {
  const [queueData, setQueueData] = useState<ReviewQueueResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [actionStatus, setActionStatus] = useState<string | null>(null)

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

  async function handleAction(itemId: string, action: 'confirm' | 'reject_as_false_positive' | 'escalate') {
    try {
      setActionStatus(`Submitting ${action}...`)
      await submitReviewV2(itemId, action)
      setActionStatus(`Action ${action} recorded cleanly!`)
      await loadQueue()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur-md">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-amber-400"></span>
            Human Review Queue & Candidate Golden Set Feedback Loop (Phase 10)
          </h3>
          <button
            onClick={loadQueue}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors"
          >
            Refresh Queue
          </button>
        </div>

        <p className="text-sm text-slate-400 mb-6">
          Items are prioritized by <code className="text-amber-400 bg-slate-950 px-1.5 py-0.5 rounded">severity × value × age</code>. Rejection of false positives automatically enqueues the document into candidate golden-set evaluation fixtures.
        </p>


        {queueData && (
          <div className="mb-6 p-4 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
            <div>
              <span className="text-sm font-semibold text-slate-200">
                Pending Review Count: {queueData.count}
              </span>
              <div className="text-xs text-slate-400">
                Candidate Golden Set Fixtures Created: {queueData.golden_set_candidates_count}
              </div>
            </div>
          </div>
        )}

        {actionStatus && <div className="text-xs text-cyan-400 font-semibold mb-4">{actionStatus}</div>}
        {loading && <div className="text-sm text-slate-400">Loading queue items...</div>}
        {error && <div className="text-sm text-rose-400">{error}</div>}

        {queueData && queueData.pending_items.length === 0 && (
          <div className="text-sm text-slate-400 py-8 text-center">
            Review queue is empty. All active findings are resolved or auto-passed cleanly.
          </div>
        )}

        {queueData && queueData.pending_items.length > 0 && (
          <div className="space-y-4">
            {queueData.pending_items.map((item) => (
              <div key={item.item_id} className="p-4 rounded-lg bg-slate-950/60 border border-slate-800/80 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-1 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                      Priority Score: {item.priority_score.toFixed(1)}
                    </span>
                    <span className="text-xs text-slate-400 font-mono">{item.finding.check_id}</span>
                  </div>
                  <div className="text-sm font-semibold text-slate-200">{item.finding.message}</div>
                  <div className="text-xs text-slate-400">Document: {item.document_id} | Created: {new Date(item.created_at).toLocaleTimeString()}</div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => handleAction(item.item_id, 'confirm')}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-600/30 transition-colors"
                  >
                    Confirm
                  </button>

                  <button
                    onClick={() => handleAction(item.item_id, 'reject_as_false_positive')}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-rose-600/20 text-rose-300 border border-rose-500/30 hover:bg-rose-600/30 transition-colors"
                  >
                    Reject (False Alarm)
                  </button>

                  <button
                    onClick={() => handleAction(item.item_id, 'escalate')}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-600/20 text-amber-300 border border-amber-500/30 hover:bg-amber-600/30 transition-colors"
                  >
                    Escalate
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
