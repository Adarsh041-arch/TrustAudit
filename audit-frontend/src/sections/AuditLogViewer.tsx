import React, { useEffect, useState } from 'react'
import {
  ShieldCheck,
  RefreshCw,
  Copy,
  Check,
  Search,
  AlertOctagon,
  Lock,
  Layers
} from 'lucide-react'
import { fetchAuditLogV2 } from '../api/api_v2'
import type { AuditLogResponse } from '../api/api_v2'
import { FlatCard } from '../components/FlatCard'

export const AuditLogViewer: React.FC = () => {
  const [logData, setLogData] = useState<AuditLogResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [copiedHash, setCopiedHash] = useState<string | null>(null)
  const [filterAction, setFilterAction] = useState<string>('ALL')
  const [searchFilter, setSearchFilter] = useState<string>('')

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

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text)
    setCopiedHash(text)
    setTimeout(() => setCopiedHash(null), 2000)
  }

  const entries = logData?.entries ?? []
  const filteredEntries = entries.filter((e) => {
    if (filterAction !== 'ALL' && e.action !== filterAction) return false
    if (searchFilter) {
      const q = searchFilter.toLowerCase()
      return (
        e.entry_id.toLowerCase().includes(q) ||
        e.action.toLowerCase().includes(q) ||
        e.resource_id.toLowerCase().includes(q) ||
        e.hash_chain.toLowerCase().includes(q)
      )
    }
    return true
  })

  const uniqueActions = ['ALL', ...Array.from(new Set(entries.map((e) => e.action)))]

  return (
    <div className="space-y-6">
      <FlatCard>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-border/60">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-[18px] font-bold text-ink">
                Cryptographic Hash-Chained Audit Ledger
              </h2>
              <p className="text-[12.5px] text-muted">
                Immutable, tamper-evident SHA-256 blockchain-style log proving zero retroactive manipulation.
              </p>
            </div>
          </div>

          <button
            onClick={loadLog}
            disabled={loading}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-[12.5px] font-semibold border border-border bg-surface-1 hover:bg-surface-3 text-ink transition-all cursor-pointer shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh Log
          </button>
        </div>

        {/* Verification Status Banner */}
        {logData && (
          <div
            className={`p-4 rounded-2xl border mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
              logData.chain_valid
                ? 'bg-emerald-500/10 border-emerald-500/30'
                : 'bg-coral-500/10 border-coral-500/30'
            }`}
          >
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                  logData.chain_valid
                    ? 'bg-emerald-500 text-white'
                    : 'bg-coral-500 text-white animate-pulse'
                }`}
              >
                {logData.chain_valid ? (
                  <ShieldCheck className="w-5 h-5" />
                ) : (
                  <AlertOctagon className="w-5 h-5" />
                )}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[15px] font-bold text-ink">
                    {logData.chain_valid
                      ? 'Cryptographic Chain Integrity: VERIFIED INTACT'
                      : 'WARNING: Cryptographic Chain Broken / Altered'}
                  </span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider bg-surface-2 border border-current/20 text-ink">
                    SHA-256
                  </span>
                </div>
                <p className="text-[12.5px] text-muted mt-0.5">
                  {logData.entries.length} chained entry blocks verified sequentially from genesis root.
                </p>
              </div>
            </div>

            <span
              className={`px-3 py-1.5 rounded-xl text-[12px] font-bold self-start sm:self-auto ${
                logData.chain_valid
                  ? 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300'
                  : 'bg-coral-500/20 text-coral-700 dark:text-coral-300'
              }`}
            >
              {logData.chain_valid ? '✓ Mathematically Valid' : '✕ Verification Error'}
            </span>
          </div>
        )}

        {/* Filters and search */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
          <div className="relative flex-1 w-full sm:max-w-xs">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Search ledger entries..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-xl text-[12.5px] bg-surface-1 border border-border text-ink focus:outline-none focus:border-teal-500"
            />
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
            {uniqueActions.map((action) => (
              <button
                key={action}
                onClick={() => setFilterAction(action)}
                className={`px-3 py-1 rounded-lg text-[11px] font-semibold transition-all cursor-pointer whitespace-nowrap ${
                  filterAction === action
                    ? 'bg-teal-500/15 text-teal-600 dark:text-teal-400 border border-teal-500/30'
                    : 'bg-surface-1 text-muted hover:text-ink border border-border'
                }`}
              >
                {action}
              </button>
            ))}
          </div>
        </div>

        {loading && <div className="text-[13px] text-muted py-6">Validating cryptographic ledger...</div>}
        {error && <div className="text-[13px] text-coral-600 py-4">{error}</div>}

        {entries.length === 0 && !loading && (
          <div className="text-center py-12 text-muted">
            <Layers className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p className="text-[13px]">No audit log entries recorded yet.</p>
          </div>
        )}

        {/* Visual Chained Block Ledger */}
        <div className="space-y-3">
          {filteredEntries.map((entry, idx) => (
            <div
              key={entry.entry_id}
              className="p-4 rounded-2xl bg-surface-1 border border-border hover:border-border-bright transition-all shadow-xs"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[12.5px] mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-teal-600 dark:text-teal-400">
                    Block #{idx + 1}
                  </span>
                  <span className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-500/20">
                    {entry.action}
                  </span>
                  <span className="text-muted font-mono text-[11.5px] truncate max-w-[180px]">
                    {entry.entry_id}
                  </span>
                </div>
                <span className="text-[11px] text-muted font-mono">
                  {new Date(entry.timestamp).toLocaleString()}
                </span>
              </div>

              <div className="text-[12.5px] text-ink mb-2">
                Triggered by <span className="font-semibold">{entry.actor_id}</span> on target{' '}
                <span className="font-mono font-medium text-teal-700 dark:text-teal-300">
                  {entry.resource_type}:{entry.resource_id}
                </span>
              </div>

              {/* Hash Chain Block Values */}
              <div className="p-3 rounded-xl bg-surface-2 border border-border/70 font-mono text-[11.5px] space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="truncate">
                    <span className="text-muted mr-2">prev_hash:</span>
                    <span className="text-muted/80">{entry.prev_hash}</span>
                  </div>
                  <button
                    onClick={() => copyToClipboard(entry.prev_hash)}
                    className="text-muted hover:text-ink cursor-pointer shrink-0"
                    title="Copy prev_hash"
                  >
                    {copiedHash === entry.prev_hash ? (
                      <Check className="w-3.5 h-3.5 text-emerald-500" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>

                <div className="flex items-center justify-between gap-2 pt-1 border-t border-border/50">
                  <div className="truncate">
                    <span className="text-teal-600 dark:text-teal-400 font-semibold mr-2">
                      hash_chain:
                    </span>
                    <span className="text-teal-700 dark:text-teal-300 font-semibold">
                      {entry.hash_chain}
                    </span>
                  </div>
                  <button
                    onClick={() => copyToClipboard(entry.hash_chain)}
                    className="text-teal-600 hover:text-teal-700 cursor-pointer shrink-0"
                    title="Copy hash_chain"
                  >
                    {copiedHash === entry.hash_chain ? (
                      <Check className="w-3.5 h-3.5 text-emerald-500" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </FlatCard>
    </div>
  )
}
