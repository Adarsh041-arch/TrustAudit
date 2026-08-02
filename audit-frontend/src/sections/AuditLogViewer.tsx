import React, { useEffect, useState } from 'react'
import { fetchAuditLogV2 } from '../api/api_v2'
import type { AuditLogResponse } from '../api/api_v2'
import { FlatCard } from '../components/FlatCard'

export const AuditLogViewer: React.FC = () => {
  const [logData, setLogData] = useState<AuditLogResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadLog()
  }, [])

  async function loadLog() {
    try {
      setLoading(true)
      const data = await fetchAuditLogV2()
      setLogData(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch audit log')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <FlatCard>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[18px] font-medium text-ink flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-teal-600"></span>
            Cryptographic Hash-Chained Audit Log (Phase 2 Governance)
          </h3>
          <button
            onClick={loadLog}
            className="px-3 py-1.5 rounded-lg text-[13px] font-medium border-[0.5px] border-border text-muted hover:text-ink transition-colors bg-transparent hover:bg-surface-1"
          >
            Refresh Log
          </button>
        </div>

        {logData && (
          <div className="mb-6 p-4 rounded-xl bg-surface-1 border-[0.5px] border-border flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className={`w-2.5 h-2.5 rounded-full ${logData.chain_valid ? 'bg-teal-600' : 'bg-coral-600'}`}></span>
              <div>
                <div className="text-[14px] font-medium text-ink">
                  Chain Status: {logData.chain_valid ? 'VERIFIED INTACT' : 'TAMPERED / BROKEN'}
                </div>
                <div className="text-[13px] text-muted">
                  {logData.entries.length} Hash-Chained Entries Recorded
                </div>
              </div>
            </div>

            <span className={`px-3 py-1 rounded-lg text-[13px] font-medium border-[0.5px] ${
              logData.chain_valid 
                ? 'bg-teal-50 text-teal-600 border-teal-600/30'
                : 'bg-coral-50 text-coral-600 border-coral-600/30'
            }`}>
              {logData.chain_valid ? 'SHA-256 Validated' : 'Validation Failed'}
            </span>
          </div>
        )}

        {loading && <div className="text-[13px] text-muted">Loading audit log entries...</div>}
        {error && <div className="text-[13px] text-coral-600">{error}</div>}

        {logData && logData.entries.length === 0 && (
          <div className="text-[13px] text-muted py-8 text-center">
            No audit log entries recorded yet. Ingest documents to trigger log activity.
          </div>
        )}

        {logData && logData.entries.length > 0 && (
          <div className="space-y-3">
            {logData.entries.map((entry, idx) => (
              <div key={entry.entry_id} className="p-4 rounded-xl bg-surface-1 border-[0.5px] border-border space-y-2">
                <div className="flex items-center justify-between text-[13px] text-muted">
                  <span className="font-mono text-ink font-medium">#{idx + 1} {entry.entry_id}</span>
                  <span>{new Date(entry.timestamp).toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-0.5 rounded-lg text-[13px] font-medium bg-teal-50 text-teal-600 border-[0.5px] border-teal-600/30">
                    {entry.action}
                  </span>
                  <span className="text-[13px] text-muted">by {entry.actor_id} on {entry.resource_type}:{entry.resource_id}</span>
                </div>
                <div className="grid grid-cols-1 font-mono text-[12px] bg-surface-2 p-3 rounded-lg border-[0.5px] border-border gap-1 text-muted">
                  <div><span className="text-muted">prev_hash:</span> {entry.prev_hash}</div>
                  <div><span className="text-teal-600">hash_chain:</span> {entry.hash_chain}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </FlatCard>
    </div>
  )
}
