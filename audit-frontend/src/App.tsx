import { useState } from 'react'
import { uploadDocumentsV2 } from './api/api_v2'
import type { UploadResponse } from './api/api_v2'
import type { DocumentAuditResult } from './types/audit'


import { useDarkMode } from './hooks/useDarkMode'
import { Header } from './components/Header'
import { FlatCard } from './components/FlatCard'
import { VlmStatusBadge } from './components/VlmStatusBadge'
import { ThreeWayMatchGraph } from './sections/ThreeWayMatchGraph'
import { AuditLogViewer } from './sections/AuditLogViewer'
import { ReviewQueueSection } from './sections/ReviewQueueSection'
import { DashboardSection } from './sections/DashboardSection'
import { DocumentCard } from './components/DocumentCard'
import { StatusBadge } from './components/StatusBadge'
import { ProcessingAnimation } from './components/ProcessingAnimation'

type TabType = 'dashboard' | 'upload' | 'threeway' | 'findings' | 'review' | 'audit_log' | 'reports' | 'settings'

export function App() {
  const { dark, toggle } = useDarkMode()
  const [activeTab, setActiveTab] = useState<TabType>('dashboard')
  const [files, setFiles] = useState<FileList | null>(null)
  const [uploading, setUploading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null)
  const [allDocuments, setAllDocuments] = useState<any[]>([])
  const [allFindings, setAllFindings] = useState<any[]>([])
  const [allReportDocs, setAllReportDocs] = useState<DocumentAuditResult[]>([])
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)

  async function handleUpload() {
    if (!files || files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      const res = await uploadDocumentsV2(files)
      setUploadResult(res)
      if (res.document_results?.length) {
        setSelectedDocId(res.document_results[0].document_id)
      }
      if (res.documents && res.documents.length > 0) {
        setAllDocuments((prev) => [...prev, ...res.documents!])
      } else if (res.document) {
        setAllDocuments((prev) => [...prev, res.document])
      }

      setAllFindings((prev) => [...prev, ...res.findings])
      if (res.document_results) {
        setAllReportDocs((prev) => [...prev, ...res.document_results])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Document ingestion failed')
    } finally {
      setUploading(false)
    }
  }

  const selectedDoc =
    uploadResult?.document_results?.find((d) => d.document_id === selectedDocId) ??
    uploadResult?.document_results?.[0] ??
    null

  return (
    <div className="min-h-dvh bg-surface-1">
      {/* V1 Shared Header with Dark Mode Toggle */}
      <Header dark={dark} onToggleDark={toggle} title="V2 Engine" />

      {/* Main V1 Container */}
      <main className="max-w-[960px] mx-auto px-6 py-8 space-y-8">
        {/* Navigation Bar */}
        <div className="flex flex-wrap gap-2 pb-2 border-b-[0.5px] border-border">
          {[
            { id: 'dashboard', label: 'Dashboard' },
            { id: 'upload', label: 'Live Audit Ingestion' },
            { id: 'threeway', label: '3-Way Match Topology' },
            { id: 'findings', label: `Findings (${allFindings.length})` },
            { id: 'review', label: 'Review Queue' },
            { id: 'audit_log', label: 'Cryptographic Audit Log' },
            { id: 'reports', label: 'Reports' },
            { id: 'settings', label: 'Settings' },
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

        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && <DashboardSection documents={allReportDocs} />}

        {/* Tab 1: Live Ingestion */}
        {activeTab === 'upload' && (
          <div className="space-y-6">
            <FlatCard>
              <h2 className="text-[18px] font-medium text-ink mb-1">
                Batch Ingest Documents (PDF, Scanned Image, PNG, JPG)
              </h2>
              <p className="text-[13px] text-muted mb-4">
                Invoices, Purchase Orders, Delivery Challans and Goods Receipts run dual extraction (deterministic regex
                in parallel with VLM Vision AI; field-level disagreements are queued for human review). Contracts and
                letters are text-only documents extracted by VLM with a narrative report.
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

              {uploading && <ProcessingAnimation message="Extracting & auditing documents\u2026" />}

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
                      mode={
                        uploadResult.extraction_results?.[0]?.extraction_mode ??
                        (uploadResult.document.extractor_version?.startsWith('dual')
                          ? 'dual'
                          : uploadResult.document.extractor_version?.startsWith('vlm_text')
                            ? 'vlm_text'
                            : uploadResult.document.extractor_version?.startsWith('vlm')
                              ? 'vlm'
                              : 'regex')
                      }
                      extractorVersion={uploadResult.document.extractor_version}
                    />
                  </div>

                  {/* Extraction disagreement -> human review */}
                  {uploadResult.requires_human_review && (
                    <div className="p-3 rounded-lg bg-amber-50 border-[0.5px] border-amber-600/30 text-amber-700 text-[13px]">
                      Regex and VLM extraction disagreed on some fields in this batch.
                      Disagreements are queued in the Review Queue for human review.
                    </div>
                  )}

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

                  {/* Disagreed fields (dual extraction) */}
                  {uploadResult.document.extraction_disagreements &&
                    Object.keys(uploadResult.document.extraction_disagreements).length > 0 && (
                      <div className="p-3 bg-amber-50 rounded-lg border-[0.5px] border-amber-600/30">
                        <div className="text-[11px] text-amber-700 uppercase font-medium mb-1">
                          Regex vs VLM disagreements ({Object.keys(uploadResult.document.extraction_disagreements).length})
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(uploadResult.document.extraction_disagreements).map(([field, diff]) => (
                            <span
                              key={field}
                              className="px-2 py-1 rounded-lg bg-white border-[0.5px] border-amber-600/30 text-amber-700 text-[12px] font-mono"
                            >
                              {field}: {String(diff)}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                  {/* VLM narrative report (contracts/letters) */}
                  {uploadResult.document.narrative_report && (
                    <div className="p-3 bg-surface-1 rounded-lg border-[0.5px] border-border">
                      <div className="text-[11px] text-muted uppercase font-medium mb-1">
                        VLM Narrative Report
                      </div>
                      <p className="text-[13px] text-ink leading-relaxed">
                        {uploadResult.document.narrative_report}
                      </p>
                    </div>
                  )}

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

                {/* Document Inspector */}
                {uploadResult.document_results && uploadResult.document_results.length > 0 && (
                  <FlatCard>
                    <h3 className="text-[18px] font-medium text-ink mb-4">Document Inspector</h3>
                    {uploadResult.document_results.length > 1 && (
                      <div className="flex flex-col gap-1.5 mb-4 max-h-56 overflow-y-auto">
                        {uploadResult.document_results.map((d) => (
                          <button
                            key={d.document_id}
                            onClick={() => setSelectedDocId(d.document_id)}
                            className={`flex items-center justify-between px-3 py-2 rounded-lg border-[0.5px] text-left text-[13px] transition-colors cursor-pointer ${
                              selectedDocId === d.document_id
                                ? 'border-teal-600 bg-teal-50 text-ink'
                                : 'border-border bg-surface-1 text-muted hover:bg-surface-2'
                            }`}
                          >
                            <span className="truncate mr-2">{d.document_name}</span>
                            <StatusBadge passed={d.passed} />
                          </button>
                        ))}
                      </div>
                    )}
                    {selectedDoc && (
                      <>
                        {selectedDoc.human_review_recommended && (
                          <div className="mb-3 p-3 rounded-lg bg-amber-50 border-[0.5px] border-amber-600/30 text-amber-700 text-[13px]">
                            Human review recommended (confidence {selectedDoc.confidence_score.toFixed(1)}%).
                          </div>
                        )}
                        <DocumentCard doc={selectedDoc} interval={uploadResult.prediction_interval} />
                      </>
                    )}
                  </FlatCard>
                )}
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

        {/* Tab 6: Reports */}
        {activeTab === 'reports' && (
          <FlatCard>
            <p className="text-[13px] text-muted py-6">Reports tab - coming soon.</p>
          </FlatCard>
        )}

        {/* Tab 7: Settings */}
        {activeTab === 'settings' && (
          <FlatCard>
            <p className="text-[13px] text-muted py-6">Settings tab - coming soon.</p>
          </FlatCard>
        )}
      </main>
    </div>
  )
}

export default App
