import { useState } from 'react'
import { uploadDocumentsV2 } from './api/api_v2'
import type { UploadResponse } from './api/api_v2'



import { useDarkMode } from './hooks/useDarkMode'
import { Header } from './components/Header'
import { FlatCard } from './components/FlatCard'
import { VlmStatusBadge } from './components/VlmStatusBadge'
import { ThreeWayMatchGraph } from './sections/ThreeWayMatchGraph'
import { AuditLogViewer } from './sections/AuditLogViewer'
import { ReviewQueueSection } from './sections/ReviewQueueSection'

type TabType = 'upload' | 'threeway' | 'findings' | 'review' | 'audit_log'

export function App() {
  const { dark, toggle } = useDarkMode()
  const [activeTab, setActiveTab] = useState<TabType>('upload')
  const [files, setFiles] = useState<FileList | null>(null)
  const [uploading, setUploading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null)
  const [allDocuments, setAllDocuments] = useState<any[]>([])
  const [allFindings, setAllFindings] = useState<any[]>([])

  async function handleUpload() {
    if (!files || files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      const res = await uploadDocumentsV2(files)
      setUploadResult(res)
      if (res.documents && res.documents.length > 0) {
        setAllDocuments((prev) => [...prev, ...res.documents!])
      } else if (res.document) {
        setAllDocuments((prev) => [...prev, res.document])
      }

      setAllFindings((prev) => [...prev, ...res.findings])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Document ingestion failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="min-h-dvh bg-surface-1">
      {/* V1 Shared Header with Dark Mode Toggle */}
      <Header dark={dark} onToggleDark={toggle} title="V2 Engine" />

      {/* Main V1 Container */}
      <main className="max-w-[960px] mx-auto px-6 py-8 space-y-8">
        {/* Navigation Bar */}
        <div className="flex flex-wrap gap-2 pb-2 border-b-[0.5px] border-border">
          {[
            { id: 'upload', label: 'Live Audit Ingestion' },
            { id: 'threeway', label: '3-Way Match Topology' },
            { id: 'findings', label: `Findings (${allFindings.length})` },
            { id: 'review', label: 'Review Queue' },
            { id: 'audit_log', label: 'Cryptographic Audit Log' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as TabType)}
              className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-colors cursor-pointer ${
                activeTab === tab.id
                  ? 'border-[0.5px] border-teal-600 text-teal-600 bg-teal-50/50'
                  : 'border-[0.5px] border-border text-muted hover:text-ink bg-surface-2'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab 1: Live Ingestion */}
        {activeTab === 'upload' && (
          <div className="space-y-6">
            <FlatCard>
              <h2 className="text-[18px] font-medium text-ink mb-1">
                Batch Ingest Documents (PDF, Scanned Image, PNG, JPG)
              </h2>
              <p className="text-[13px] text-muted mb-4">
                Select multiple documents at once (Invoices, Purchase Orders, Delivery Challans, Goods Receipts). Text layers are extracted deterministically; scanned or unreadable pages automatically transition to VLM Vision AI.
              </p>

              <div className="flex flex-col sm:flex-row gap-3 items-center">
                <input
                  type="file"
                  multiple
                  onChange={(e) => setFiles(e.target.files)}
                  className="flex-1 border-[0.5px] border-border rounded-lg px-4 py-2 text-[14px] text-ink bg-surface-2 outline-none focus:border-teal-600 transition-colors w-full"
                />

                <button
                  onClick={handleUpload}
                  disabled={uploading || !files || files.length === 0}
                  className="px-5 py-2.5 rounded-lg text-[13px] font-medium border-[0.5px] border-teal-600 text-teal-600 bg-transparent hover:bg-teal-50 disabled:opacity-40 disabled:pointer-events-none transition-colors cursor-pointer shrink-0 w-full sm:w-auto"
                >
                  {uploading ? 'Batch Extracting & Auditing\u2026' : `Run Batch Audit (${files ? files.length : 0})`}
                </button>
              </div>

              {files && files.length > 0 && (
                <div className="mt-3 text-[13px] text-teal-600 font-medium">
                  ✓ Selected {files.length} document(s): {Array.from(files).map((f) => f.name).join(', ')}
                </div>
              )}

              {error && (
                <div className="mt-4 p-3 rounded-lg bg-coral-50 border-[0.5px] border-coral-600/30 text-coral-600 text-[13px]">
                  {error}
                </div>
              )}


              {uploadResult && (
                <div className="mt-8 space-y-6 border-t-[0.5px] border-border pt-6">
                  <div className="flex items-center justify-between">
                    <h3 className="text-[16px] font-medium text-ink">
                      Ingestion Results for {uploadResult.document.document_id}
                    </h3>
                    <VlmStatusBadge
                      isVlm={uploadResult.is_vlm_fallback}
                      extractorVersion={uploadResult.document.extractor_version}
                    />
                  </div>

                  {/* Header Extracted Values */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="p-3 bg-surface-1 rounded-lg border-[0.5px] border-border">
                      <div className="text-[11px] text-muted uppercase font-medium">Doc Type</div>
                      <div className="text-[14px] font-medium text-teal-600">{uploadResult.document.doc_type}</div>
                    </div>
                    <div className="p-3 bg-surface-1 rounded-lg border-[0.5px] border-border">
                      <div className="text-[11px] text-muted uppercase font-medium">Vendor Name</div>
                      <div className="text-[14px] font-medium text-ink">{uploadResult.document.header.vendor_name?.value || 'N/A'}</div>
                    </div>
                    <div className="p-3 bg-surface-1 rounded-lg border-[0.5px] border-border">
                      <div className="text-[11px] text-muted uppercase font-medium">Grand Total</div>
                      <div className="text-[14px] font-medium text-teal-600">{uploadResult.document.header.grand_total?.value || 'N/A'}</div>
                    </div>
                    <div className="p-3 bg-surface-1 rounded-lg border-[0.5px] border-border">
                      <div className="text-[11px] text-muted uppercase font-medium">PO Reference</div>
                      <div className="text-[14px] font-medium text-ink">{uploadResult.document.header.po_reference?.value || 'N/A'}</div>
                    </div>
                  </div>

                  {/* Findings Table */}
                  <div>
                    <h4 className="text-[14px] font-medium text-ink mb-3">
                      Emitted Audit Findings ({uploadResult.findings.length})
                    </h4>
                    {uploadResult.findings.length === 0 ? (
                      <div className="p-4 bg-teal-50 border-[0.5px] border-teal-600/30 rounded-lg text-teal-600 text-[13px]">
                        No errors or discrepancies found. Document passed all deterministic checks cleanly.
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {uploadResult.findings.map((f: any) => (
                          <div
                            key={f.finding_id}
                            className="p-3 bg-surface-1 border-[0.5px] border-border rounded-lg flex items-center justify-between"
                          >
                            <div>
                              <div className="text-[12px] font-mono text-teal-600 font-medium">{f.check_id}</div>
                              <div className="text-[13px] text-ink mt-0.5">{f.message}</div>
                            </div>
                            <span
                              className={`px-2.5 py-1 rounded-lg text-[12px] font-medium ${
                                f.status === 'FAIL'
                                  ? 'bg-coral-50 text-coral-600 border-[0.5px] border-coral-600/30'
                                  : 'bg-teal-50 text-teal-600'
                              }`}
                            >
                              {f.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </FlatCard>
          </div>
        )}

        {/* Tab 2: 3-Way Match Graph */}
        {activeTab === 'threeway' && (
          <ThreeWayMatchGraph documents={allDocuments} findings={allFindings} />
        )}

        {/* Tab 3: Findings List */}
        {activeTab === 'findings' && (
          <div className="space-y-4">
            <FlatCard>
              <h3 className="text-[18px] font-medium text-ink mb-4">
                All Active Findings ({allFindings.length})
              </h3>
              {allFindings.length === 0 ? (
                <p className="text-[13px] text-muted py-4">
                  No findings active. Ingest documents to trigger checks.
                </p>
              ) : (
                <div className="space-y-3">
                  {allFindings.map((f: any) => (
                    <div
                      key={f.finding_id}
                      className="p-4 rounded-lg bg-surface-1 border-[0.5px] border-border space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-[13px]">
                        <span className="font-mono text-teal-600 font-medium">{f.check_id}</span>
                        <span className="text-muted font-mono text-[11px]">
                          Fingerprint: {f.decision_fingerprint?.slice(0, 24)}...
                        </span>
                      </div>
                      <div className="text-[14px] text-ink">{f.message}</div>
                      <div className="text-[13px] text-muted">
                        Document ID: {f.document_id} | Ruleset: {f.ruleset_version}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </FlatCard>
          </div>
        )}

        {/* Tab 4: Review Queue */}
        {activeTab === 'review' && <ReviewQueueSection />}

        {/* Tab 5: Audit Log */}
        {activeTab === 'audit_log' && <AuditLogViewer />}
      </main>
    </div>
  )
}

export default App
