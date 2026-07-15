import { useState } from 'react'
import type { AuditResponse, Status } from './types/audit'
import { runAudit } from './api/audit'
import { useDarkMode } from './hooks/useDarkMode'
import { Header } from './components/Header'
import { SummaryMetrics } from './sections/SummaryMetrics'
import { DocumentList } from './sections/DocumentList'
import { ReportSection } from './sections/ReportSection'
import { FlatCard } from './components/FlatCard'

function App() {
  const { dark, toggle } = useDarkMode()
  const [folderPath, setFolderPath] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [data, setData] = useState<AuditResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleRun() {
    if (!folderPath.trim()) return
    setStatus('loading')
    setError(null)
    setData(null)
    try {
      const res = await runAudit(folderPath.trim())
      setData(res)
      setStatus('success')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
      setStatus('error')
    }
  }

  return (
    <div className="min-h-dvh bg-surface-1">
      <Header dark={dark} onToggleDark={toggle} title={data?.report.audit_title} />

      <main className="max-w-[960px] mx-auto px-6 py-8 space-y-8">

        {/* Folder input */}
        <FlatCard>
          <label className="block text-[13px] text-muted mb-2 font-medium">
            Folder path
          </label>
          <div className="flex gap-2">
            <input
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              placeholder="C:\Users\...\sample_docs"
              className="flex-1 border-[0.5px] border-border rounded-lg px-4 py-2 text-[16px] text-ink bg-surface-2 placeholder:text-muted/50 outline-none focus:border-teal-600 transition-colors"
            />
            <button
              onClick={handleRun}
              disabled={status === 'loading' || !folderPath.trim()}
              className="px-5 py-2 rounded-lg text-[13px] font-medium border-[0.5px] border-teal-600 text-teal-600 bg-transparent hover:bg-teal-50 disabled:opacity-40 disabled:pointer-events-none transition-colors cursor-pointer shrink-0"
            >
              {status === 'loading' ? 'Running…' : 'Run audit'}
            </button>
          </div>
        </FlatCard>

        {/* Loading */}
        {status === 'loading' && (
          <p className="text-[13px] text-muted text-center">Audit in progress…</p>
        )}

        {/* Error */}
        {status === 'error' && (
          <FlatCard className="border-coral-600/30">
            <p className="text-[13px] text-coral-600">{error}</p>
          </FlatCard>
        )}

        {/* Results */}
        {data && (
          <>
            <ReportSection report={data.report} interval={data.prediction_interval} />

            <div className="space-y-4">
              <h2 className="text-[18px] font-medium text-ink">Summary</h2>
              <SummaryMetrics report={data.report} />
            </div>

            <div className="border-t-[0.5px] border-border" />

            <DocumentList
              documents={data.report.document_results}
              interval={data.prediction_interval}
            />
          </>
        )}
      </main>
    </div>
  )
}

export default App
