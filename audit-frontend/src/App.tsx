import { useState } from 'react'
import { uploadDocumentV2 } from './api/api_v2'
import type { UploadResponse } from './api/api_v2'


import { VlmStatusBadge } from './components/VlmStatusBadge'
import { ThreeWayMatchGraph } from './sections/ThreeWayMatchGraph'
import { AuditLogViewer } from './sections/AuditLogViewer'
import { ReviewQueueSection } from './sections/ReviewQueueSection'

type TabType = 'upload' | 'threeway' | 'findings' | 'review' | 'audit_log'

export function App() {
  const [activeTab, setActiveTab] = useState<TabType>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null)
  const [allDocuments, setAllDocuments] = useState<any[]>([])
  const [allFindings, setAllFindings] = useState<any[]>([])

  async function handleUpload() {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const res = await uploadDocumentV2(file)
      setUploadResult(res)
      setAllDocuments(prev => [...prev, res.document])
      setAllFindings(prev => [...prev, ...res.findings])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Document ingestion failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-cyan-500 selection:text-slate-950">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-slate-950 text-lg shadow-lg shadow-cyan-500/20">
              V2
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-100 tracking-tight">TrustAudit V2 Engine</h1>
              <p className="text-xs text-slate-400">Multimodal VLM · 3-Way Match · Hash-Chained Governance</p>

            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
              API :8100 Active
            </span>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="max-w-7xl mx-auto px-6 flex gap-1 border-t border-slate-800/60 pt-2 pb-0">
          {[
            { id: 'upload', label: 'Live Audit Ingestion' },
            { id: 'threeway', label: '3-Way Match Topology' },
            { id: 'findings', label: `Findings (${allFindings.length})` },
            { id: 'review', label: 'Review Queue' },
            { id: 'audit_log', label: 'Cryptographic Audit Log' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as TabType)}
              className={`px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
                activeTab === tab.id
                  ? 'border-cyan-400 text-cyan-400 bg-slate-800/60'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      {/* Main Content Body */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Tab 1: Live Ingestion */}
        {activeTab === 'upload' && (
          <div className="space-y-6">
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur-md">
              <h2 className="text-lg font-bold text-slate-100 mb-2">Ingest Document (PDF, Scanned Image, PNG, JPG)</h2>
              <p className="text-sm text-slate-400 mb-6">
                Upload Invoices, Purchase Orders, Delivery Challans, or Goods Receipt Notes. Text layers are extracted deterministically; scanned or unreadable pages automatically transition to VLM Vision AI.
              </p>

              <div className="flex flex-col md:flex-row gap-4 items-center">
                <input
                  type="file"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="block w-full text-sm text-slate-300 file:mr-4 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-cyan-400 hover:file:bg-slate-700 bg-slate-950 p-2 rounded-xl border border-slate-800"
                />

                <button
                  onClick={handleUpload}
                  disabled={uploading || !file}
                  className="w-full md:w-auto px-6 py-3 rounded-xl font-semibold text-xs bg-gradient-to-r from-cyan-500 to-blue-600 text-slate-950 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-40 disabled:pointer-events-none transition-all shadow-lg shadow-cyan-500/20 shrink-0"
                >
                  {uploading ? 'Extracting & Auditing...' : 'Run Audit V2 Ingestion'}
                </button>
              </div>

              {error && <div className="mt-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">{error}</div>}

              {uploadResult && (
                <div className="mt-8 space-y-6 border-t border-slate-800 pt-6">
                  <div className="flex items-center justify-between">
                    <h3 className="text-base font-bold text-slate-200">Ingestion Results for {uploadResult.document.document_id}</h3>
                    <VlmStatusBadge
                      isVlm={uploadResult.is_vlm_fallback}
                      extractorVersion={uploadResult.document.extractor_version}
                    />
                  </div>

                  {/* Header Extracted Values */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                      <div className="text-xs text-slate-500 uppercase font-semibold">Doc Type</div>
                      <div className="text-sm font-bold text-cyan-400">{uploadResult.document.doc_type}</div>
                    </div>
                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                      <div className="text-xs text-slate-500 uppercase font-semibold">Vendor Name</div>
                      <div className="text-sm font-bold text-slate-200">{uploadResult.document.header.vendor_name?.value || 'N/A'}</div>
                    </div>
                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                      <div className="text-xs text-slate-500 uppercase font-semibold">Grand Total</div>
                      <div className="text-sm font-bold text-emerald-400">{uploadResult.document.header.grand_total?.value || 'N/A'}</div>
                    </div>
                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                      <div className="text-xs text-slate-500 uppercase font-semibold">PO Reference</div>
                      <div className="text-sm font-bold text-slate-200">{uploadResult.document.header.po_reference?.value || 'N/A'}</div>
                    </div>
                  </div>

                  {/* Findings Table */}
                  <div>
                    <h4 className="text-sm font-bold text-slate-300 mb-3">Emitted Audit Findings ({uploadResult.findings.length})</h4>
                    {uploadResult.findings.length === 0 ? (
                      <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-emerald-300 text-xs">
                        No errors or discrepancies found. Document passed all deterministic checks cleanly.
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {uploadResult.findings.map((f: any) => (
                          <div key={f.finding_id} className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex items-center justify-between">
                            <div>
                              <div className="text-xs font-mono text-cyan-400 font-bold">{f.check_id}</div>
                              <div className="text-xs text-slate-300 mt-0.5">{f.message}</div>
                            </div>
                            <span className={`px-2.5 py-1 rounded text-xs font-bold ${
                              f.status === 'FAIL' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' : 'bg-amber-500/20 text-amber-300'
                            }`}>
                              {f.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: 3-Way Match Graph */}
        {activeTab === 'threeway' && (
          <ThreeWayMatchGraph documents={allDocuments} findings={allFindings} />
        )}

        {/* Tab 3: Findings List */}
        {activeTab === 'findings' && (
          <div className="space-y-4">
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur-md">
              <h3 className="text-lg font-bold text-slate-100 mb-4">All Active Findings ({allFindings.length})</h3>
              {allFindings.length === 0 ? (
                <p className="text-sm text-slate-400 py-4">No findings active. Ingest documents to trigger checks.</p>
              ) : (
                <div className="space-y-3">
                  {allFindings.map((f: any) => (
                    <div key={f.finding_id} className="p-4 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-mono text-cyan-400 font-bold">{f.check_id}</span>
                        <span className="text-slate-500 font-mono text-[10px]">Fingerprint: {f.decision_fingerprint?.slice(0, 24)}...</span>
                      </div>
                      <div className="text-sm text-slate-200">{f.message}</div>
                      <div className="text-xs text-slate-400">Document ID: {f.document_id} | Ruleset: {f.ruleset_version}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 4: Review Queue */}
        {activeTab === 'review' && (
          <ReviewQueueSection />
        )}

        {/* Tab 5: Audit Log */}
        {activeTab === 'audit_log' && (
          <AuditLogViewer />
        )}
      </main>
    </div>
  )
}
export default App
