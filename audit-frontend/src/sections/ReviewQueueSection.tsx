import React, { useEffect, useState } from 'react'
import { fetchReviewQueueV2, submitReviewV2 } from '../api/api_v2'
import type { ReviewQueueResponse } from '../api/api_v2'
import { FlatCard } from '../components/FlatCard'

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
      <FlatCard>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[18px] font-medium text-ink flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-600"></span>
            Human Review Queue & Candidate Golden Set Feedback Loop (Phase 10)
          </h3>
          <button
            onClick={loadQueue}
            className="px-3 py-1.5 rounded-lg text-[13px] font-medium border-[0.5px] border-border text-muted hover:text-ink transition-colors bg-transparent hover:bg-surface-1"
          >
            Refresh Queue
          </button>
        </div>

        <p className="text-[13px] text-muted mb-6">
          Items are prioritized by <code className="text-teal-600 bg-surface-1 px-1.5 py-0.5 rounded font-mono text-[12px]">severity × value × age</code>. Rejection of false positives automatically enqueues the document into candidate golden-set evaluation fixtures.
        </p>

        {queueData && (
          <div className="mb-6 p-4 rounded-xl bg-surface-1 border-[0.5px] border-border flex items-center justify-between">
            <div>
              <span className="text-[14px] font-medium text-ink">
                Pending Review Count: {queueData.count}
              </span>
              <div className="text-[13px] text-muted">
                Candidate Golden Set Fixtures Created: {queueData.golden_set_candidates_count}
              </div>
            </div>
          </div>
        )}

        {actionStatus && <div className="text-[13px] text-teal-600 font-medium mb-4">{actionStatus}</div>}
        {loading && <div className="text-[13px] text-muted">Loading queue items...</div>}
        {error && <div className="text-[13px] text-coral-600">{error}</div>}

        {queueData && queueData.pending_items.length === 0 && (
          <div className="text-[13px] text-muted py-8 text-center">
            Review queue is empty. All active findings are resolved or auto-passed cleanly.
          </div>
        )}

        {queueData && queueData.pending_items.length > 0 && (
          <div className="space-y-3">
            {queueData.pending_items.map((item) => (
              <div key={item.item_id} className="p-4 rounded-xl bg-surface-1 border-[0.5px] border-border flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-1 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-blue-50 text-blue-600 border-[0.5px] border-blue-600/30">
                      Priority Score: {item.priority_score.toFixed(1)}
                    </span>
                    <span className="text-[13px] text-muted font-mono">{item.finding.check_id}</span>
                  </div>
                  <div className="text-[14px] font-medium text-ink">{item.finding.message}</div>
                  <div className="text-[13px] text-muted">Document: {item.document_id} | Created: {new Date(item.created_at).toLocaleTimeString()}</div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => handleAction(item.item_id, 'confirm')}
                    className="px-3 py-1.5 rounded-lg text-[13px] font-medium bg-transparent border-[0.5px] border-teal-600 text-teal-600 hover:bg-teal-50 transition-colors"
                  >
                    Confirm
                  </button>

                  <button
                    onClick={() => handleAction(item.item_id, 'reject_as_false_positive')}
                    className="px-3 py-1.5 rounded-lg text-[13px] font-medium bg-transparent border-[0.5px] border-coral-600 text-coral-600 hover:bg-coral-50 transition-colors"
                  >
                    Reject (False Alarm)
                  </button>

                  <button
                    onClick={() => handleAction(item.item_id, 'escalate')}
                    className="px-3 py-1.5 rounded-lg text-[13px] font-medium bg-transparent border-[0.5px] border-blue-600 text-blue-600 hover:bg-blue-50 transition-colors"
                  >
                    Escalate
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </FlatCard>
    </div>
  )
}
