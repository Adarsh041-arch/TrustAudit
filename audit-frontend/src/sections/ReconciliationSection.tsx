import { useMemo, useState } from 'react'
import {
  askAi,
  downloadReconReport,
  fetchForecast,
  runReconciliation,
  saveBlob,
} from '../api/recon'
import type { CashForecast, MatchResult, ReconciliationRun } from '../api/recon'
import { FlatCard } from '../components/FlatCard'

const EXCEPTION_TYPES = [
  'AMOUNT_MISMATCH',
  'MISSING_BANK_CREDIT',
  'MISSING_LEDGER',
  'DUPLICATE_TXN_ID',
  'DATE_DRIFT',
  'CURRENCY_MISMATCH',
] as const

export function ReconciliationSection() {
  const [payoutFile, setPayoutFile] = useState<File | null>(null)
  const [bankFile, setBankFile] = useState<File | null>(null)
  const [ledgerFile, setLedgerFile] = useState<File | null>(null)
  const [truthFile, setTruthFile] = useState<File | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [run, setRun] = useState<ReconciliationRun | null>(null)
  const [forecast, setForecast] = useState<CashForecast | null>(null)
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [expandedTxn, setExpandedTxn] = useState<string | null>(null)
  const [chatTxn, setChatTxn] = useState<string | null>(null)
  const [chatThreads, setChatThreads] = useState<Record<string, { q: string; a: string }[]>>({})
  const [chatQuestion, setChatQuestion] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)

  const exceptions = useMemo(
    () => (run?.results ?? []).filter((r) => r.status === 'EXCEPTION'),
    [run],
  )
  const visibleExceptions = useMemo(
    () =>
      typeFilter
        ? exceptions.filter((r) => r.exception_type === typeFilter)
        : exceptions,
    [exceptions, typeFilter],
  )
  const ratePct = run ? (Number(run.match_rate) * 100).toFixed(1) : null

  async function handleAsk(txnId: string) {
    const question = chatQuestion.trim()
    if (!question || !run || chatBusy) return
    setChatBusy(true)
    setChatError(null)
    try {
      const answer = await askAi(run.run_id, txnId, question)
      setChatThreads((prev) => ({
        ...prev,
        [txnId]: [...(prev[txnId] ?? []), { q: question, a: answer }],
      }))
      setChatQuestion('')
    } catch (e) {
      setChatError(e instanceof Error ? e.message : 'Ask AI failed')
    } finally {
      setChatBusy(false)
    }
  }

  function riskChip(level: string | null) {
    if (!level) return null
    const styles: Record<string, string> = {
      critical: 'bg-coral-600 text-white border-coral-600',
      high: 'bg-coral-50 text-coral-600 border-coral-600/30',
      medium: 'bg-amber-50 text-amber-700 border-amber-600/30',
      low: 'bg-surface-2 text-muted border-border',
    }
    return (
      <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium uppercase border-[0.5px] ${styles[level]}`}>
        {level}
      </span>
    )
  }

  async function handleRun() {
    if (!payoutFile || !bankFile || !ledgerFile) return
    setRunning(true)
    setError(null)
    try {
      const r = await runReconciliation(payoutFile, bankFile, ledgerFile, truthFile)
      setRun(r)
      setForecast(await fetchForecast(r.run_id).catch(() => null))
      setTypeFilter('')
      setExpandedTxn(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reconciliation failed')
    } finally {
      setRunning(false)
    }
  }

  function fileInput(label: string, file: File | null, onChange: (f: File) => void, accept = '.csv') {
    return (
      <label className="flex-1 min-w-[180px]">
        <div className="text-[11px] text-muted uppercase font-medium mb-1">{label}</div>
        <input
          type="file"
          accept={accept}
          onChange={(e) => onChange(e.target.files?.[0] as File)}
          className="w-full border-[0.5px] border-border rounded-lg px-3 py-2 text-[13px] text-ink bg-surface-2 outline-none focus:border-teal-600 transition-colors cursor-pointer"
        />
        {file && <div className="mt-1 text-[12px] text-teal-600 font-mono truncate">{file.name}</div>}
      </label>
    )
  }

  function drilldown(r: MatchResult) {
    return (
      <tr key={`${r.txn_id}-detail`}>
        <td colSpan={8} className="p-0 border-[0.5px] border-border">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-3 bg-surface-2">
            {[
              r.payout && {
                title: 'Payout Report',
                rows: [
                  ['Ref', r.payout.txn_id],
                  ['Amount', `${r.payout.payout_amount} ${r.payout.currency}`],
                  ['Date', r.payout.payout_date],
                ],
              },
              r.bank && {
                title: 'Bank Statement',
                rows: [
                  ['Ref', r.bank.bank_ref],
                  ['Amount', `${r.bank.credited_amount} ${r.bank.currency}`],
                  ['Date', r.bank.value_date],
                ],
              },
              r.ledger && {
                title: 'Ledger',
                rows: [
                  ['Invoice', r.ledger.invoice_id],
                  ['Expected', `${r.ledger.expected_amount} ${r.ledger.currency}`],
                  ['Due', r.ledger.due_date],
                ],
              },
            ]
              .filter(Boolean)
              .map((src) => {
                const s = src as { title: string; rows: string[][] }
                return (
                  <div key={s.title} className="p-3 rounded-lg bg-surface-1 border-[0.5px] border-border">
                    <div className="text-[11px] uppercase font-medium text-muted mb-2">{s.title}</div>
                    {s.rows.map(([k, v]) => (
                      <div key={k} className="flex justify-between text-[13px] py-0.5">
                        <span className="text-muted">{k}</span>
                        <span className="text-ink font-mono">{v}</span>
                      </div>
                    ))}
                  </div>
                )
              })}
            {r.llm_explanation && (
              <div className="md:col-span-3 p-3 rounded-lg bg-surface-1 border-[0.5px] border-border">
                <div className="text-[11px] uppercase font-medium text-muted mb-1">AI-generated explanation</div>
                <p className="text-[13px] text-ink">{r.llm_explanation}</p>
              </div>
            )}
            <div className="md:col-span-3 text-[11px] text-muted font-mono">
              Fingerprint: {r.decision_fingerprint.slice(0, 32)}…
            </div>

            {/* Ask AI */}
            <div className="md:col-span-3 flex items-center justify-between gap-3">
              <p className="text-[11px] text-muted italic">
                Answers are generated from the deterministic verdicts above — the AI cannot change them.
              </p>
              <button
                onClick={() => { setChatTxn(r.txn_id); setChatError(null) }}
                className="px-4 py-2 rounded-lg text-[12px] font-medium border-[0.5px] border-teal-600 text-teal-600 hover:bg-teal-50 transition-colors cursor-pointer shrink-0"
              >
                Ask AI
              </button>
            </div>
          </div>
        </td>
      </tr>
    )
  }

  return (
    <div className="space-y-6">
      {/* Run controls */}
      <FlatCard>
        <h2 className="text-[18px] font-medium text-ink mb-1">Three-Way Payment Reconciliation</h2>
        <p className="text-[13px] text-muted mb-4">
          Matches payout reports against bank credits and ledger expectations with deterministic Decimal arithmetic.
          Exceptions are machine-classified; plain-language explanations are AI-generated but never change a verdict.
        </p>

        <div className="flex flex-wrap items-end gap-3">
          {fileInput('Payout Report CSV', payoutFile, setPayoutFile)}
          {fileInput('Bank Statement CSV', bankFile, setBankFile)}
          {fileInput('Ledger CSV', ledgerFile, setLedgerFile)}
          <label className="flex-1 min-w-[180px]">
            <div className="text-[11px] text-muted uppercase font-medium mb-1">
              Ground Truth JSON <span className="normal-case">(optional — enables Demo Mode)</span>
            </div>
            <input
              type="file"
              accept=".json"
              onChange={(e) => setTruthFile(e.target.files?.[0] ?? null)}
              className="w-full border-[0.5px] border-border rounded-lg px-3 py-2 text-[13px] text-ink bg-surface-2 outline-none focus:border-teal-600 transition-colors cursor-pointer"
            />
            {truthFile && <div className="mt-1 text-[12px] text-teal-600 font-mono truncate">{truthFile.name}</div>}
          </label>
          <button
            onClick={handleRun}
            disabled={running || !payoutFile || !bankFile || !ledgerFile}
            className="px-5 py-2.5 rounded-lg text-[13px] font-medium border-[0.5px] border-teal-600 text-teal-600 hover:bg-teal-50 disabled:opacity-40 disabled:pointer-events-none transition-colors cursor-pointer shrink-0"
          >
            {running ? 'Reconciling…' : 'Run Reconciliation'}
          </button>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-lg bg-coral-50 border-[0.5px] border-coral-600/30 text-coral-600 text-[13px]">
            {error}
          </div>
        )}
      </FlatCard>

      {/* Results */}
      {run && (
        <>
          <FlatCard>
            <div className="flex justify-center mb-3">
              <span
                className={`px-3 py-1 rounded-lg text-[12px] font-medium border-[0.5px] ${
                  run.mode === 'demo'
                    ? 'bg-teal-50 text-teal-600 border-teal-600/30'
                    : 'bg-surface-2 text-muted border-border'
                }`}
              >
                {run.mode === 'demo' ? 'DEMO MODE — validated against known breaks' : 'LIVE MODE — no ground truth, accuracy unverified'}
              </span>
            </div>
            <div className="text-center py-2">
              <div className="text-[44px] font-semibold text-teal-600 leading-tight">
                {run.matched} / {run.total}{' '}
                <span className="text-[20px] text-ink align-middle">MATCHED</span>
              </div>
              <div className="text-[15px] text-muted mt-1">{ratePct}% match rate</div>
              <div className="flex flex-wrap justify-center gap-x-6 gap-y-1 mt-3 text-[13px] text-muted">
                <span>
                  Exceptions: <b className="text-ink">{run.exceptions}</b>
                </span>
                <span>
                  Unapplied bank credits:{' '}
                  <b className={run.unmatched_bank_credits > 0 ? 'text-coral-600' : 'text-ink'}>
                    {run.unmatched_bank_credits}
                  </b>
                </span>
                <span className="font-mono text-[12px]">run {run.run_id}</span>
              </div>

              {run.validation ? (
                (() => {
                  const v = run.validation
                  return (
                    <div
                      className={`mt-4 p-3 rounded-lg border-[0.5px] text-[13px] inline-block ${
                        v.passed
                          ? 'bg-teal-50 border-teal-600/30 text-teal-600'
                          : 'bg-coral-50 border-coral-600/30 text-coral-600'
                      }`}
                    >
                      <b>Validated:</b> {v.detected}/{v.total_breaks} injected breaks detected ·{' '}
                      {v.fee_matches_confirmed}/{v.fee_total} fee-tolerance matches confirmed ·{' '}
                      {v.drift_matches_confirmed}/{v.drift_total} drift matches ·{' '}
                      {v.false_positives.length} false positives →{' '}
                      <b>{v.passed ? 'PASS' : 'FAIL'}</b>
                      {(v.false_negatives.length > 0 || v.false_positives.length > 0) && (
                        <div className="mt-1 font-mono text-[11px]">
                          {v.false_negatives.length > 0 && <div>missed: {v.false_negatives.join(', ')}</div>}
                          {v.false_positives.length > 0 && <div>flagged wrongly: {v.false_positives.join(', ')}</div>}
                        </div>
                      )}
                    </div>
                  )
                })()
              ) : (
                <p className="mt-4 text-[13px] text-muted">
                  No ground truth available — accuracy shown reflects the engine's internal confidence only.
                </p>
              )}
              {run.mode_note && (
                <p className="mt-2 text-[12px] text-amber-700">{run.mode_note}</p>
              )}
            </div>

            {run.llm_summary ? (
              <div className="border-t-[0.5px] border-border pt-4">
                <p className="text-[14px] text-ink leading-relaxed">{run.llm_summary}</p>
                <p className="text-[11px] text-muted mt-1 italic">
                  AI-generated summary — verified by deterministic engine
                </p>
              </div>
            ) : (
              <div className="border-t-[0.5px] border-border pt-4">
                <p className="text-[13px] text-muted">
                  AI summary unavailable (no NVIDIA_API_KEY configured on the server) — all verdicts above remain fully
                  deterministic.
                </p>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-4">
              {(['pdf', 'docx'] as const).map((fmt) => (
                <button
                  key={fmt}
                  onClick={() =>
                    downloadReconReport(run, fmt).then((blob) => saveBlob(blob, `recon-${run.run_id}.${fmt}`))
                  }
                  className="px-4 py-2 rounded-lg text-[12px] font-medium border-[0.5px] border-border text-muted hover:text-ink hover:bg-surface-2 transition-colors cursor-pointer"
                >
                  Download .{fmt}
                </button>
              ))}
            </div>
          </FlatCard>

          {/* Projected cash position */}
          {forecast && (
            <FlatCard>
              <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
                <h3 className="text-[16px] font-medium text-ink">Projected Cash Position</h3>
                <span
                  className={`px-2 py-0.5 rounded-md text-[11px] font-medium border-[0.5px] ${
                    forecast.lag_source === 'derived'
                      ? 'bg-teal-50 text-teal-600 border-teal-600/30'
                      : 'bg-amber-50 text-amber-700 border-amber-600/30'
                  }`}
                >
                  settlement lag: median {forecast.median_lag_days}d ({forecast.lag_source}
                  {forecast.lag_source === 'fallback' ? ' estimate' : ''})
                </span>
              </div>

              {(() => {
                const lanes = [
                  { key: 'settled', label: 'Settled', color: 'bg-teal-600' },
                  { key: 'in_transit', label: 'In transit', color: 'bg-amber-500' },
                  { key: 'expected', label: 'Expected', color: 'bg-teal-300' },
                  { key: 'at_risk', label: 'At risk', color: 'bg-coral-600' },
                ] as const
                const totals = lanes.map((l) => ({
                  ...l,
                  value: forecast.buckets.reduce((s, b) => s + Number(b[l.key]), 0),
                }))

                return (
                  <>
                    <div className="flex flex-wrap gap-x-6 gap-y-1 mb-4">
                      {totals.map((t) => (
                        <div key={t.key} className="flex items-center gap-2 text-[13px]">
                          <span className={`w-2.5 h-2.5 rounded-sm ${t.color}`} />
                          <span className="text-muted">{t.label}</span>
                          <b className="text-ink font-mono">
                            {t.value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                          </b>
                        </div>
                      ))}
                    </div>

                    <div className="space-y-1.5">
                      {forecast.buckets.map((b) => {
                        const vals = lanes.map((l) => Number(b[l.key]))
                        const total = vals.reduce((s, v) => s + v, 0)
                        return (
                          <div key={b.week_start} className="flex items-center gap-3">
                            <span className="w-20 shrink-0 text-[12px] text-muted font-mono">
                              {new Date(b.week_start).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                            </span>
                            <div className="flex-1 h-4 rounded-md overflow-hidden bg-surface-2 flex">
                              {total > 0 &&
                                vals.map((v, i) =>
                                  v > 0 ? (
                                    <div
                                      key={lanes[i].key}
                                      className={`${lanes[i].color} h-full`}
                                      style={{ width: `${(v / total) * 100}%` }}
                                      title={`${lanes[i].label}: ${v.toLocaleString('en-IN')}`}
                                    />
                                  )
                                : null)}
                            </div>
                            <span className="w-28 shrink-0 text-right text-[12px] font-mono text-ink">
                              {total.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                    <p className="text-[11px] text-muted mt-2">
                      Weekly buckets, Monday start · as of {new Date(forecast.as_of).toLocaleDateString('en-IN')} ·
                      deterministic Decimal projection over recon verdicts
                    </p>

                    {forecast.llm_summary ? (
                      <div className="border-t-[0.5px] border-border pt-3 mt-3">
                        <p className="text-[14px] text-ink leading-relaxed">{forecast.llm_summary}</p>
                        <p className="text-[11px] text-muted mt-1 italic">AI-generated summary — figures computed deterministically</p>
                      </div>
                    ) : (
                      <p className="text-[12px] text-muted mt-3 italic">
                        AI summary unavailable — all figures above are computed by the deterministic engine.
                      </p>
                    )}
                  </>
                )
              })()}
            </FlatCard>
          )}

          {/* Exception table */}
          <FlatCard>
            <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
              <h3 className="text-[16px] font-medium text-ink">Exception Table ({visibleExceptions.length})</h3>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="border-[0.5px] border-border rounded-lg px-3 py-1.5 text-[13px] text-ink bg-surface-2 outline-none focus:border-teal-600"
              >
                <option value="">All types</option>
                {EXCEPTION_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>

            {visibleExceptions.length === 0 ? (
              <div className="p-4 bg-teal-50 border-[0.5px] border-teal-600/30 rounded-lg text-teal-600 text-[13px]">
                No exceptions{typeFilter ? ` of type ${typeFilter}` : ''}. All records reconciled cleanly.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-left text-[11px] uppercase text-muted border-b-[0.5px] border-border">
                      <th className="py-2 pr-3 font-medium">Txn ID</th>
                      <th className="py-2 pr-3 font-medium">Type</th>
                      <th className="py-2 pr-3 font-medium">Risk</th>
                      <th className="py-2 pr-3 font-medium text-right">Payout</th>
                      <th className="py-2 pr-3 font-medium text-right">Bank</th>
                      <th className="py-2 pr-3 font-medium text-right">Delta</th>
                      <th className="py-2 pr-3 font-medium">Drift</th>
                      <th className="py-2 font-medium">AI Explanation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleExceptions.map((r) => [
                      <tr
                        key={r.txn_id + String(visibleExceptions.indexOf(r))}
                        onClick={() => setExpandedTxn(expandedTxn === r.txn_id ? null : r.txn_id)}
                        className={`cursor-pointer transition-colors ${
                          expandedTxn === r.txn_id ? 'bg-teal-50/60' : 'hover:bg-surface-2'
                        }`}
                      >
                        <td className="py-2.5 pr-3 font-mono text-teal-600">{r.txn_id}</td>
                        <td className="py-2.5 pr-3">
                          <span className="px-2 py-0.5 rounded-md bg-coral-50 text-coral-600 border-[0.5px] border-coral-600/30 text-[12px]">
                            {r.exception_type}
                          </span>
                        </td>
                        <td className="py-2.5 pr-3">{riskChip(r.risk_level)}</td>
                        <td className="py-2.5 pr-3 text-right font-mono">{r.payout?.payout_amount ?? '—'}</td>
                        <td className="py-2.5 pr-3 text-right font-mono">{r.bank?.credited_amount ?? '—'}</td>
                        <td className="py-2.5 pr-3 text-right font-mono">{r.amount_delta ?? '—'}</td>
                        <td className="py-2.5 pr-3">{r.date_drift_days != null ? `${r.date_drift_days}d` : ''}</td>
                        <td className="py-2.5 text-muted max-w-[260px] truncate">
                          {r.llm_explanation ?? <span className="italic text-[12px]">unavailable</span>}
                        </td>
                      </tr>,
                      ...(expandedTxn === r.txn_id ? [drilldown(r)] : []),
                    ])}
                  </tbody>
                </table>
              </div>
            )}
            <p className="text-[11px] text-muted mt-3">Click a row for the side-by-side source drilldown.</p>
          </FlatCard>
        </>
      )}

      {/* Ask AI slide-over panel */}
      {chatTxn && run && (
        <>
          <div
            className="fixed inset-0 bg-black/30 z-40"
            onClick={() => setChatTxn(null)}
          />
          <aside className="fixed right-0 top-0 h-dvh w-full max-w-md bg-surface-2 border-l-[0.5px] border-border z-50 flex flex-col shadow-xl">
            <div className="flex items-center justify-between px-5 py-4 border-b-[0.5px] border-border">
              <div>
                <div className="text-[15px] font-medium text-ink">Ask AI</div>
                <div className="text-[12px] text-muted font-mono">{chatTxn}</div>
              </div>
              <button
                onClick={() => setChatTxn(null)}
                className="w-8 h-8 rounded-lg text-muted hover:text-ink hover:bg-surface-1 transition-colors cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
              {(chatThreads[chatTxn] ?? []).length === 0 && (
                <p className="text-[13px] text-muted">
                  Ask anything about this transaction — why it failed, what to do next, what the numbers mean.
                </p>
              )}
              {(chatThreads[chatTxn] ?? []).map((turn, i) => (
                <div key={i} className="space-y-2">
                  <div className="flex justify-end">
                    <span className="max-w-[85%] px-3 py-2 rounded-lg bg-teal-600 text-white text-[13px]">
                      {turn.q}
                    </span>
                  </div>
                  <div className="flex justify-start">
                    <span className="max-w-[85%] px-3 py-2 rounded-lg bg-surface-1 border-[0.5px] border-border text-ink text-[13px] whitespace-pre-wrap">
                      {turn.a}
                    </span>
                  </div>
                </div>
              ))}
              {chatBusy && (
                <div className="flex justify-start">
                  <span className="px-3 py-2 rounded-lg bg-surface-1 border-[0.5px] border-border text-muted text-[13px] italic">
                    Thinking…
                  </span>
                </div>
              )}
              {chatError && (
                <p className="text-[12px] text-coral-600">{chatError} (AI answers need NVIDIA_API_KEY on the server)</p>
              )}
            </div>

            <div className="px-5 py-4 border-t-[0.5px] border-border space-y-2">
              <div className="flex gap-2">
                <input
                  autoFocus
                  value={chatQuestion}
                  onChange={(e) => setChatQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && chatTxn && handleAsk(chatTxn)}
                  maxLength={500}
                  placeholder="e.g. Should I escalate this?"
                  className="flex-1 border-[0.5px] border-border rounded-lg px-3 py-2.5 text-[13px] text-ink bg-surface-1 outline-none focus:border-teal-600 transition-colors"
                />
                <button
                  onClick={() => chatTxn && handleAsk(chatTxn)}
                  disabled={chatBusy || !chatQuestion.trim()}
                  className="px-4 rounded-lg text-[12px] font-medium border-[0.5px] border-teal-600 text-teal-600 hover:bg-teal-50 disabled:opacity-40 disabled:pointer-events-none transition-colors cursor-pointer"
                >
                  Send
                </button>
              </div>
              <p className="text-[11px] text-muted">
                Answers come from the deterministic verdicts for this run — the AI cannot change them.
              </p>
            </div>
          </aside>
        </>
      )}
    </div>
  )
}
