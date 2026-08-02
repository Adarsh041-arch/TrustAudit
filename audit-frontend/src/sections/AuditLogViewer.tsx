import React, { useEffect, useState } from 'react'
import { fetchAuditLogV2 } from '../api/api_v2'
import type { AuditLogResponse } from '../api/api_v2'


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
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur-md">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-emerald-400"></span>
            Cryptographic Hash-Chained Audit Log (Phase 2 Governance)
          </h3>
          <button
            onClick={loadLog}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors"
          >
            Refresh Log
          </button>
        </div>

        {logData && (
          <div className="mb-6 p-4 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className={`w-3 h-3 rounded-full ${logData.chain_valid ? 'bg-emerald-400 animate-ping' : 'bg-rose-500'}`}></span>
              <div>
                <div className="text-sm font-semibold text-slate-200">
                  Chain Status: {logData.chain_valid ? 'VERIFIED INTACT' : 'TAMPERED / BROKEN'}
                </div>
                <div className="text-xs text-slate-400">
                  {logData.entries.length} Hash-Chained Entries Recorded
                </div>
              </div>
            </div>

            <span className={`px-3 py-1 rounded-full text-xs font-bold border ${
              logData.chain_valid 
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
            }`}>
              {logData.chain_valid ? 'SHA-256 Validated' : 'Validation Failed'}
            </span>
          </div>
        )}

        {loading && <div className="text-sm text-slate-400">Loading audit log entries...</div>}
        {error && <div className="text-sm text-rose-400">{error}</div>}

        {logData && logData.entries.length === 0 && (
          <div className="text-sm text-slate-400 py-8 text-center">
            No audit log entries recorded yet. Ingest documents to trigger log activity.
          </div>
        )}

        {logData && logData.entries.length > 0 && (
          <div className="space-y-4">
            {logData.entries.map((entry, idx) => (
              <div key={entry.entry_id} className="p-4 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span className="font-mono text-cyan-400 font-bold">#{idx + 1} {entry.entry_id}</span>
                  <span>{new Date(entry.timestamp).toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded text-xs font-semibold bg-slate-800 text-slate-200">
                    {entry.action}
                  </span>
                  <span className="text-xs text-slate-400">by {entry.actor_id} on {entry.resource_type}:{entry.resource_id}</span>
                </div>
                <div className="grid grid-cols-1 font-mono text-[11px] bg-slate-900 p-2.5 rounded border border-slate-800/50 gap-1 text-slate-400">
                  <div><span className="text-slate-500">prev_hash:</span> {entry.prev_hash}</div>
                  <div><span className="text-emerald-500/80">hash_chain:</span> {entry.hash_chain}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
