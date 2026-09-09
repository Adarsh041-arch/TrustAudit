import { useState, useRef, useEffect } from 'react'
import {
  fetchWorkspaceV2,
  uploadDocumentsV2,
  uploadDocumentsStreamV2,
  subscribePipeline,
  V2_BASE,
} from './api/api_v2'
import { apiFetch } from './api/http'
import type { UploadResponse } from './api/api_v2'
import type { DocumentAuditResult, StepEvent } from './types/audit'
import { useDarkMode } from './hooks/useDarkMode'
import { WorkspaceShell } from './components/WorkspaceShell'
import './v2.css'
import { FlatCard } from './components/FlatCard'
import { VlmStatusBadge } from './components/VlmStatusBadge'
import { ThreeWayMatchGraph } from './sections/ThreeWayMatchGraph'
import { ReconciliationSection } from './sections/ReconciliationSection'
import { AuditLogViewer } from './sections/AuditLogViewer'
import { ReviewQueueSection } from './sections/ReviewQueueSection'
import { DashboardSection } from './sections/DashboardSection'
import { AuditWorkspace } from './sections/AuditWorkspace'
import { PipelineProgress, type DocProgress } from './components/PipelineProgress'
import { ReportSection } from './sections/ReportSection'
import { SettingsSection } from './sections/SettingsSection'
import {
  LayoutDashboard,
  UploadCloud,
  FileSearch,
  Layers,
  Banknote,
  AlertTriangle,
  Users,
  Lock,
  FileText,
  Settings,
  Sparkles,
  FileCheck,
  X,
  Radio,
  Clock
} from 'lucide-react'

type TabType =
  | 'dashboard'
  | 'upload'
  | 'results'
  | 'threeway'
  | 'recon'
  | 'findings'
  | 'review'
  | 'audit_log'
  | 'reports'
  | 'settings'

export function AppV2() {
  const { dark, toggle } = useDarkMode()
  const [activeTab, setActiveTab] = useState<TabType>('dashboard')
  const [isDemo, setIsDemo] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState<boolean>(false)
  const [streamingMode, setStreamingMode] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null)
  const [allDocuments, setAllDocuments] = useState<any[]>([])
  const [allFindings, setAllFindings] = useState<any[]>([])
  const [allReportDocs, setAllReportDocs] = useState<DocumentAuditResult[]>([])
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)
  const [executiveSummary, setExecutiveSummary] = useState('')
  const [threshold, setThreshold] = useState<number>(() =>
    Number(localStorage.getItem('confidence_threshold') ?? 75)
  )
  const [docProgressList, setDocProgressList] = useState<DocProgress[]>([])
  const [activeJobId, setActiveJobId] = useState<string | null>(() => sessionStorage.getItem('audit_active_job'))
  const workspaceGeneration = useRef(0)
  const stopStream = useRef<(() => void) | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleThresholdChange = (t: number) => {
    setThreshold(t)
    localStorage.setItem('confidence_threshold', String(t))
  }

  useEffect(() => {
    let active = true
    const generation = workspaceGeneration.current
    fetchWorkspaceV2().then(res => {
      if (!active || generation !== workspaceGeneration.current) return
      setAllReportDocs(res.document_results)
      setAllFindings(res.findings)
      setAllDocuments(res.document_results.map(d => ({document_id: d.document_id, doc_type: d.document_type})))
    }).catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!activeJobId) return
    setUploading(true)
    const stop = subscribePipeline(activeJobId, {
      onStep: () => {},
      onResult: (result) => { processUploadResult(result); setUploading(false) },
      onError: (message) => { setError(message); setUploading(false) },
    })
    stopStream.current = stop
    return stop
  }, [])

  async function controlJob(action: 'retry' | 'cancel') {
    if (!activeJobId) return
    try {
      const response = await apiFetch(`${V2_BASE}/audit/jobs/${encodeURIComponent(activeJobId)}/${action}`, { method: 'POST' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Job action failed')
      if (action === 'retry') {
        sessionStorage.setItem('audit_active_job', body.job_id)
        window.location.reload()
      } else {
        stopStream.current?.()
        sessionStorage.removeItem('audit_active_job')
        setActiveJobId(null); setUploading(false)
        setError('Audit cancelled before commit. Existing saved audits are retained.')
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Job action failed') }
  }

  function loadSampleDataset() {
    workspaceGeneration.current += 1
    setIsDemo(true)
    setActiveTab('dashboard')
    const sampleDocs: DocumentAuditResult[] = [
      {
        document_id: 'DOC-INV-2026-0001',
        document_name: 'INV-2026-0001_Enterprise_Hardware.pdf',
        document_type: 'invoice',
        passed: false,
        document_status: 'READY',
        audit_status: 'FAIL',
        score: 84.5,
        risk_level: 'Medium Risk',
        risk_explanation:
          'Line item unit price for 10GbE network cards ($215/ea) exceeds pre-authorized PO rate ($180/ea). Quantity billed matches delivered shipment.',
        failed_rules: [
          {
            rule_id: 'CHK-XDOC-PRICE-001',
            rule_title: 'Unit Price Authorization Cap Exceeded',
            finding:
              'Invoiced unit price $215.00 exceeds PO-2026-0007 authorization ceiling of $180.00 (+19.4% variance)',
            evidence: 'PO Line 3: $180.00 vs Invoice Line 3: $215.00',
            impact: 'Unauthorized procurement price leakage of $140.00',
            recommendation:
              'Hold payment disbursement until vendor reissues credit note or procurement approves price delta.',
            severity: 'high',
            page_number: 1,
          },
        ],
        ml_prediction: null,
        confidence_score: 91.2,
        prediction_interval: { lower: 81.0, upper: 88.0 },
        human_review_recommended: true,
        remarks: 'Price mismatch requires human review sign-off.',
        preview_base64: '',
        page_count: 2,
        summary_text:
          'Commercial tax invoice billed by Dell Enterprise Solutions against PO-2026-0007 for IT server cluster components totaling $17,580.00.',
        vision_backend: 'Dual Engine (Regex + VLM Vision)',
        vision_model: 'nemotron-4-340b',
        coverage_complete: true,
        pages_examined: 2,
        pages_unreadable: [],
        grounding_rejection_count: 0,
        extraction_disagreements: {
          tax_rate: 'Regex parsed 18% vs VLM parsed 18.00% CGST/SGST split',
        },
        extraction_strategy: 'transcript_plus_structured_fallback',
        classification_status: 'CONFIRMED',
        classification_confidence: 0.98,
        classification_method: 'deterministic_header_regex',
        metadata: { vendor_name: 'Dell Enterprise Solutions', total: '$17,580.00' },
        evidences: [
          {
            evidence_id: 'EV-001',
            document_id: 'DOC-INV-2026-0001',
            nature: 'extracted_fields',
            source: 'deterministic_regex',
            payload: { grand_total: 17580.0 },
            summary: 'Grand total extracted from header table with valid tax calculation',
            confidence: 0.99,
            page: 1,
            created_at: new Date().toISOString(),
          },
        ],
      },
      {
        document_id: 'DOC-DC-2026-0011',
        document_name: 'DC-2026-0011_Proof_Of_Delivery.pdf',
        document_type: 'delivery_challan',
        passed: true,
        document_status: 'READY',
        audit_status: 'PASS',
        score: 96.5,
        risk_level: 'Low Risk',
        risk_explanation:
          'Warehouse receiving dock verified 28/32 items received intact. Delivery receipt signed with stamp.',
        failed_rules: [],
        ml_prediction: null,
        confidence_score: 95.0,
        prediction_interval: { lower: 94.0, upper: 99.0 },
        human_review_recommended: false,
        remarks: 'Physical proof of delivery verified cleanly.',
        preview_base64: '',
        page_count: 1,
        summary_text:
          'Goods receipt note and signed delivery challan verifying physical arrival of server chassis, network cards, and power supplies.',
        vision_backend: 'Dual Engine',
        vision_model: null,
        coverage_complete: true,
        pages_examined: 1,
        pages_unreadable: [],
        grounding_rejection_count: 0,
        classification_status: 'CONFIRMED',
        classification_confidence: 0.96,
        classification_method: 'deterministic_header_regex',
        metadata: { received_by: 'Warehouse Gate 4 Dock Officer' },
      },
      {
        document_id: 'DOC-PO-2026-0007',
        document_name: 'PO-2026-0007_Approved_Purchase_Order.pdf',
        document_type: 'purchase_order',
        passed: true,
        document_status: 'READY',
        audit_status: 'PASS',
        score: 98.0,
        risk_level: 'Low Risk',
        risk_explanation:
          'Pre-authorized spend ceiling approved by Chief Information Officer. Valid vendor tax registration.',
        failed_rules: [],
        ml_prediction: null,
        confidence_score: 99.0,
        prediction_interval: { lower: 96.0, upper: 100.0 },
        human_review_recommended: false,
        remarks: 'Baseline spending authorization verified.',
        preview_base64: '',
        page_count: 2,
        summary_text:
          'Pre-authorized corporate purchase order issued to Dell Enterprise Solutions with authorized ceiling of $18,640.00.',
        vision_backend: 'Dual Engine',
        vision_model: null,
        coverage_complete: true,
        pages_examined: 2,
        pages_unreadable: [],
        grounding_rejection_count: 0,
        classification_status: 'CONFIRMED',
        classification_confidence: 0.99,
        classification_method: 'deterministic_header_regex',
        metadata: { authorized_ceiling: '$18,640.00' },
      },
      {
        document_id: 'DOC-SC-2026-0041',
        document_name: 'SC-2026-0041_Master_Services_Agreement.pdf',
        document_type: 'contract',
        passed: false,
        document_status: 'READY',
        audit_status: 'FAIL',
        score: 68.0,
        risk_level: 'High Risk',
        risk_explanation:
          'Master agreement contains unbounded liability indemnification and missing governing jurisdiction clause.',
        failed_rules: [
          {
            rule_id: 'CHK-CONTRACT-LIAB-001',
            rule_title: 'Uncapped Liability Exposure Clause',
            finding:
              'Section 14.2 omits 12-month trailing fees aggregate liability limitation cap.',
            evidence: 'Section 14.2: "...shall indemnify and hold harmless without limitation..."',
            impact: 'Legal liability exposure beyond standard enterprise insurance coverage.',
            recommendation:
              'Require vendor legal counsel to execute Amendment A inserting standard 2x annual fee liability cap.',
            severity: 'critical',
            page_number: 4,
          },
        ],
        ml_prediction: null,
        confidence_score: 87.5,
        prediction_interval: { lower: 64.0, upper: 72.0 },
        human_review_recommended: true,
        remarks: 'Critical legal clauses breached.',
        preview_base64: '',
        page_count: 5,
        summary_text:
          'Vendor Master Services Agreement governing hardware warranty, SLAs, and operational indemnities.',
        vision_backend: 'VLM Vision Text & Semantic Extractor',
        vision_model: 'nemotron-4-340b',
        coverage_complete: true,
        pages_examined: 5,
        pages_unreadable: [],
        grounding_rejection_count: 1,
        grounding_rejections: ['Uncited SLA credit payout formula on page 3 paragraph 2'],
        classification_status: 'CONFIRMED',
        classification_confidence: 0.92,
        classification_method: 'vlm_narrative_classifier',
        metadata: { parties: 'Enterprise Corp & Dell Solutions' },
      },
    ]

    const sampleFindings = [
      {
        finding_id: 'FIND-001',
        check_id: 'CHK-XDOC-PRICE-001',
        document_id: 'DOC-INV-2026-0001',
        message: 'Invoiced Unit Price $215.00 exceeds PO-2026-0007 Authorization ($180.00)',
        status: 'FAIL',
        ruleset_version: '2.0.0-temporal',
        decision_fingerprint: 'sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069',
      },
      {
        finding_id: 'FIND-002',
        check_id: 'CHK-XDOC-QTY-001',
        document_id: 'DOC-INV-2026-0001',
        message: 'Invoiced RAM Quantity (16 Units) exceeds GRN Delivery Sign-off (12 Units)',
        status: 'FAIL',
        ruleset_version: '2.0.0-temporal',
        decision_fingerprint: 'sha256:4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a',
      },
      {
        finding_id: 'FIND-003',
        check_id: 'CHK-CONTRACT-LIAB-001',
        document_id: 'DOC-SC-2026-0041',
        message: 'Master Services Agreement Section 14.2 omits mandatory aggregate liability ceiling',
        status: 'FAIL',
        ruleset_version: '2.0.0-temporal',
        decision_fingerprint: 'sha256:ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d',
      },
    ]

    setAllReportDocs(sampleDocs)
    setAllFindings(sampleFindings)
    setAllDocuments([
      { doc_type: 'invoice', document_id: 'DOC-INV-2026-0001' },
      { doc_type: 'delivery_challan', document_id: 'DOC-DC-2026-0011' },
      { doc_type: 'purchase_order', document_id: 'DOC-PO-2026-0007' },
      { doc_type: 'contract', document_id: 'DOC-SC-2026-0041' },
    ])
    setSelectedDocId(sampleDocs[0].document_id)
    setExecutiveSummary(
      'Audit V2 evaluated 4 enterprise procurement documents against 18 deterministic compliance rules. A 3-way match price escalation of +19.4% on network cards and an uncapped liability clause in the Master Agreement were flagged for human triage.'
    )
  }

  // Handle Drag & Drop
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => {
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(Array.from(e.dataTransfer.files))
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(Array.from(e.target.files))
    }
  }

  const addFiles = (newFiles: File[]) => {
    setFiles((prev) => [...prev, ...newFiles])
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  async function handleUpload() {
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    setDocProgressList([])

    if (streamingMode) {
      try {
        const { job_id } = await uploadDocumentsStreamV2(files)
        sessionStorage.setItem('audit_active_job', job_id)
        setActiveJobId(job_id)
        // Setup SSE subscription
        const unsubscribe = subscribePipeline(job_id, {
          onStep: (event: StepEvent) => {
            setDocProgressList((prev) => {
              const docId = event.document_id || 'batch'
              const existingIdx = prev.findIndex((d) => d.document_id === docId)
              if (existingIdx >= 0) {
                const next = [...prev]
                next[existingIdx] = {
                  ...next[existingIdx],
                  steps: {
                    ...next[existingIdx].steps,
                    [event.step]: event.status,
                  },
                }
                return next
              } else {
                return [
                  ...prev,
                  {
                    document_id: docId,
                    filename: event.document_id || 'Document',
                    steps: { [event.step]: event.status },
                  },
                ]
              }
            })
          },
          onResult: (res: UploadResponse) => {
            unsubscribe()
            processUploadResult(res)
            setUploading(false)
          },
          onError: (errMsg: string) => {
            unsubscribe()
            setError(errMsg)
            setUploading(false)
          },
        })
        stopStream.current = unsubscribe
      } catch (err: any) {
        setError(err?.message || 'Upload connection failed. Check the workspace before retrying.')
        setUploading(false)
      }
    } else {
      try {
        const res = await uploadDocumentsV2(files)
        processUploadResult(res)
      } catch (e: any) {
        setError(e instanceof Error ? e.message : 'Document ingestion failed')
      } finally {
        setUploading(false)
      }
    }
  }

  function processUploadResult(res: UploadResponse) {
    workspaceGeneration.current += 1
    sessionStorage.removeItem('audit_active_job')
    setActiveJobId(null)
    if (isDemo) {
      setAllDocuments([])
      setAllFindings([])
      setAllReportDocs([])
      setExecutiveSummary('')
      setIsDemo(false)
    }
    setUploadResult(res)
    if (res.document_results?.length) {
      setSelectedDocId(res.document_results[0].document_id)
    }
    if (res.documents && res.documents.length > 0) {
      setAllDocuments((prev) => [...new Map([...prev, ...res.documents!].map(d => [d.document_id, d])).values()])
    } else if (res.document) {
      setAllDocuments((prev) => [...new Map([...prev, res.document].map(d => [d.document_id, d])).values()])
    }

    if (res.findings) {
      setAllFindings((prev) => {
        const updated = new Set([...(res.document_results || []), ...(res.updated_document_results || [])].map(d => d.document_id))
        return [...prev.filter(f => !updated.has(f.document_id)), ...res.findings]
      })
    }
    if (res.document_results) {
      setAllReportDocs((prev) => [...new Map([...prev, ...(res.updated_document_results || []), ...res.document_results].map(d => [d.document_id, d])).values()])
    }
    if (res.executive_summary) {
      setExecutiveSummary(res.executive_summary)
    }
    if (res.failed_uploads?.length) setError(res.failed_uploads.map(f => `${f.filename}: ${f.error}`).join('; '))
    setFiles([])
    setActiveTab('dashboard')
  }

  const navItems = [
    { id: 'dashboard', label: 'Overview', icon: <LayoutDashboard className="w-4 h-4" /> },
    { id: 'upload', label: 'Upload documents', icon: <UploadCloud className="w-4 h-4" /> },
    {
      id: 'results',
      label: 'Document workspace',
      icon: <FileSearch className="w-4 h-4" />,
      badge: allReportDocs.length > 0 ? allReportDocs.length : undefined,
    },
    { id: 'threeway', label: 'Cross-verification', icon: <Layers className="w-4 h-4" /> },
    { id: 'recon', label: 'Reconciliation', icon: <Banknote className="w-4 h-4" /> },
    {
      id: 'findings',
      label: 'Findings',
      icon: <AlertTriangle className="w-4 h-4" />,
      badge: allFindings.length > 0 ? allFindings.length : undefined,
      badgeColor: 'coral',
    },
    { id: 'review', label: 'Review Queue', icon: <Users className="w-4 h-4" /> },
    { id: 'audit_log', label: 'Audit Log', icon: <Lock className="w-4 h-4" /> },
    { id: 'reports', label: 'Reports', icon: <FileText className="w-4 h-4" /> },
    { id: 'settings', label: 'Settings', icon: <Settings className="w-4 h-4" /> },
  ]

  return (
    <WorkspaceShell dark={dark} onToggleDark={toggle} activeTab={activeTab}
      onNavigate={(id) => setActiveTab(id as TabType)} navItems={navItems}
      isDemo={isDemo} uploading={uploading} onLoadDemo={loadSampleDataset}
      onExitDemo={() => { setIsDemo(false); setAllDocuments([]); setAllFindings([]); setAllReportDocs([]); setSelectedDocId(null); setExecutiveSummary(''); setActiveTab('dashboard') }}>
        {error && activeTab !== 'upload' && <div role="alert" className="v2-demo-banner"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => setError(null)} aria-label="Dismiss message"><X size={14} /></button></div>}
        {activeJobId && <div className="v2-demo-banner" role="status"><Clock size={16} /><span>{uploading ? 'Audit in progress. You can return to this workspace while it runs.' : 'A retained audit job is available for recovery.'}</span><button onClick={() => controlJob(uploading ? 'cancel' : 'retry')}>{uploading ? 'Cancel audit' : 'Recover / retry'}</button></div>}
        {/* 1. Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <DashboardSection
            documents={allReportDocs}
            executiveSummary={executiveSummary}
            onOpenDocument={(documentId) => {
              setSelectedDocId(documentId)
              setActiveTab('results')
            }}
            onLoadDemoData={loadSampleDataset}
            onUpload={() => setActiveTab('upload')}
          />
        )}

        {/* 2. Audit Workspace / Results Tab */}
        {activeTab === 'results' && (
          <AuditWorkspace
            documents={allReportDocs}
            selectedId={selectedDocId}
            onSelect={setSelectedDocId}
          />
        )}

        {/* 3. Live Ingestion Tab */}
        {activeTab === 'upload' && (
          <div className="space-y-6">
            <FlatCard glow="teal">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-border/60">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="p-2 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400">
                      <UploadCloud className="w-5 h-5" />
                    </div>
                    <h2 className="text-[19px] font-bold text-ink">
                      Start a new audit
                    </h2>
                  </div>
                  <p className="text-[12.5px] text-muted mt-1 max-w-2xl">
                    Upload related documents together. Follow their progress, inspect discrepancies, and see the evidence behind each result.
                  </p>
                </div>

                {/* Streaming vs Fast Batch Toggle */}
                <div className="flex items-center gap-2 bg-surface-1 p-1.5 rounded-xl border border-border text-[12px]">
                  <button
                    onClick={() => setStreamingMode(true)}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded-lg font-semibold transition-all cursor-pointer ${
                      streamingMode
                        ? 'bg-surface-2 text-teal-600 dark:text-teal-400 shadow-xs'
                        : 'text-muted hover:text-ink'
                    }`}
                  >
                    <Radio className="w-3.5 h-3.5 text-teal-500" />
                    <span>Live progress</span>
                  </button>
                  <button
                    onClick={() => setStreamingMode(false)}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded-lg font-semibold transition-all cursor-pointer ${
                      !streamingMode
                        ? 'bg-surface-2 text-teal-600 dark:text-teal-400 shadow-xs'
                        : 'text-muted hover:text-ink'
                    }`}
                  >
                    <Clock className="w-3.5 h-3.5" />
                    <span>Batch mode</span>
                  </button>
                </div>
              </div>

              {/* Drag & Drop Hero Zone */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                role="button"
                tabIndex={0}
                aria-label="Choose documents to upload"
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInputRef.current?.click() } }}
                onClick={() => fileInputRef.current?.click()}
                className={`relative border-2 border-dashed rounded-2xl p-8 text-center transition-all cursor-pointer duration-200 ${
                  isDragging
                    ? 'border-teal-500 bg-teal-500/10 scale-[1.01]'
                    : 'border-border hover:border-teal-500/50 bg-surface-1/50 hover:bg-surface-1'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  onChange={handleFileSelect}
                  className="hidden"
                  accept=".pdf,.png,.jpg,.jpeg"
                />

                <div className="w-12 h-12 rounded-2xl bg-teal-500/10 text-teal-600 dark:text-teal-400 mx-auto flex items-center justify-center mb-3">
                  <UploadCloud className="w-6 h-6" />
                </div>

                <h4 className="text-[15px] font-bold text-ink">
                  Drag and drop audit documents here, or{' '}
                  <span className="text-teal-600 dark:text-teal-400 underline">browse files</span>
                </h4>
                <p className="text-[12px] text-muted mt-1">
                  Supported formats: PDF, Scanned Images (JPG, PNG), Delivery Challans, POs, Invoices, Contracts
                </p>

                {/* File format pills */}
                <div className="flex flex-wrap justify-center gap-2 mt-4">
                  {['Invoices', 'Purchase Orders', 'Delivery Challans (GRN)', 'Service Contracts'].map(
                    (tag) => (
                      <span
                        key={tag}
                        className="px-2.5 py-0.5 rounded-full text-[11px] bg-surface-2 border border-border text-muted font-medium"
                      >
                        {tag}
                      </span>
                    )
                  )}
                </div>
              </div>

              {/* Staged files preview */}
              {files.length > 0 && (
                <div className="mt-4 space-y-2">
                  <div className="flex items-center justify-between text-[12.5px] font-semibold text-ink">
                    <span>Staged for Audit ({files.length} documents)</span>
                    <button
                      onClick={() => setFiles([])}
                      className="text-coral-600 hover:underline text-[11px] cursor-pointer"
                    >
                      Clear All
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 max-h-48 overflow-y-auto">
                    {files.map((file, idx) => (
                      <div
                        key={`${file.name}-${idx}`}
                        className="flex items-center justify-between p-2.5 rounded-xl bg-surface-1 border border-border text-[12px]"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <FileCheck className="w-4 h-4 text-teal-600 shrink-0" />
                          <span className="truncate font-medium text-ink">{file.name}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-muted font-mono text-[11px]">
                            {(file.size / 1024).toFixed(0)} KB
                          </span>
                          <button
                            aria-label={`Remove ${file.name}`}
                            onClick={(e) => {
                              e.stopPropagation()
                              removeFile(idx)
                            }}
                            className="text-muted hover:text-coral-600 cursor-pointer"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="mt-5 flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-border/60">
                <div className="text-[12px] text-muted">
                  {files.length > 0
                    ? `Ready to audit ${files.length} document(s)`
                    : 'Add invoices and related purchase orders or receipts together.'}
                </div>

                <div className="flex items-center gap-2.5 w-full sm:w-auto">
                  <button
                    onClick={loadSampleDataset}
                    className="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl text-[13px] font-semibold border border-border bg-surface-1 hover:bg-surface-3 text-ink transition-all cursor-pointer"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-teal-500" />
                    <span>Load 3-Way Sample</span>
                  </button>

                  <button
                    onClick={handleUpload}
                    disabled={uploading || files.length === 0}
                    className="flex-1 sm:flex-none inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl text-[13px] font-semibold bg-gradient-to-r from-teal-500 to-emerald-600 hover:from-teal-600 hover:to-emerald-700 text-white disabled:opacity-40 disabled:pointer-events-none shadow-md shadow-teal-500/20 active:scale-95 transition-all cursor-pointer"
                  >
                    {uploading ? (
                      <span>Auditing ({files.length})…</span>
                    ) : (
                      <span>Start audit ({files.length})</span>
                    )}
                  </button>
                </div>
              </div>

              {/* Live Streaming Step Progress */}
              {uploading && docProgressList.length > 0 && (
                <PipelineProgress docs={docProgressList} />
              )}

              {error && (
                <div className="mt-4 p-3.5 rounded-xl bg-coral-500/10 border border-coral-500/30 text-coral-600 text-[13px]">
                  {error}
                </div>
              )}
            </FlatCard>

            {/* Ingestion Results Details if Available */}
            {uploadResult && (
              <FlatCard>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-[17px] font-bold text-ink">
                    Ingestion Dossier Summary for {uploadResult.document?.document_id}
                  </h3>
                  <VlmStatusBadge
                    mode={
                      uploadResult.extraction_results?.[0]?.extraction_mode ??
                      (uploadResult.document?.extractor_version?.startsWith('dual')
                        ? 'dual'
                        : uploadResult.document?.extractor_version?.startsWith('vlm_text')
                          ? 'vlm_text'
                          : uploadResult.document?.extractor_version?.startsWith('vlm')
                            ? 'vlm'
                            : 'regex')
                    }
                    extractorVersion={uploadResult.document?.extractor_version}
                  />
                </div>

                {uploadResult.document_results && uploadResult.document_results.length > 0 && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      {uploadResult.document_results.map((d) => (
                        <button
                          key={d.document_id}
                          onClick={() => {
                            setSelectedDocId(d.document_id)
                            setActiveTab('results')
                          }}
                          className="p-3 rounded-xl border border-border bg-surface-1 hover:border-teal-500 text-left transition-all cursor-pointer"
                        >
                          <span className="block truncate text-[13px] font-semibold text-ink">
                            {d.document_name}
                          </span>
                          <span className="block text-[11px] text-muted font-mono mt-0.5">
                            Score: {d.score?.toFixed(1) ?? '—'}%
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </FlatCard>
            )}
          </div>
        )}

        {/* 4. 3-Way Match Topology Tab */}
        {activeTab === 'threeway' && (
          <ThreeWayMatchGraph documents={allDocuments} findings={allFindings} />
        )}

        {/* 5. Payment Reconciliation Tab */}
        {activeTab === 'recon' && <ReconciliationSection />}

        {/* 6. Findings Tab */}
        {activeTab === 'findings' && (
          <FlatCard>
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-border/60">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-coral-500/10 text-coral-600 dark:text-coral-400">
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-[18px] font-bold text-ink">
                    Findings to investigate ({allFindings.length})
                  </h3>
                  <p className="text-[12.5px] text-muted">
                    Deterministic checks, cross-document discrepancies, and grounding conflicts.
                  </p>
                </div>
              </div>
            </div>

            {allFindings.length === 0 ? (
              <div className="text-center py-12 text-muted">
                <FileCheck className="w-8 h-8 mx-auto mb-2 text-emerald-500/60" />
                <p className="text-[13px] font-medium text-ink">No findings to display</p>
                <p className="text-[12px] text-muted mt-0.5">
                  Upload documents to see their check results here.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {allFindings.map((f: any) => (
                  <div
                    key={f.finding_id}
                    className="p-4 rounded-2xl bg-surface-1 border border-border hover:border-border-bright transition-all space-y-1.5 shadow-xs"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[13px]">
                      <span className="font-mono font-bold text-teal-600 dark:text-teal-400">
                        {f.check_id}
                      </span>
                      <span className="text-muted font-mono text-[11px] truncate max-w-sm">
                        Fingerprint: {f.decision_fingerprint?.slice(0, 32)}…
                      </span>
                    </div>
                    <div className="text-[14px] font-medium text-ink">{f.message}</div>
                    <div className="text-[12px] text-muted font-mono">
                      Target: <span className="text-ink">{f.document_id}</span> | Ruleset: {f.ruleset_version}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </FlatCard>
        )}

        {/* 7. Review Queue Tab */}
        {activeTab === 'review' && <ReviewQueueSection />}

        {/* 8. Cryptographic Audit Log Tab */}
        {activeTab === 'audit_log' && <AuditLogViewer />}

        {/* 9. Reports Tab */}
        {activeTab === 'reports' && (
          <ReportSection
            documents={allReportDocs}
            findings={allFindings}
            executiveSummary={executiveSummary}
          />
        )}

        {/* 10. Settings Tab */}
        {activeTab === 'settings' && (
          <SettingsSection threshold={threshold} onThresholdChange={handleThresholdChange} />
        )}
    </WorkspaceShell>
  )
}

export default AppV2
