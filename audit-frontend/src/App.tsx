import { useState, useEffect } from 'react'
import {
  Shield,
  FileText,
  CheckCircle,
  AlertTriangle,
  AlertOctagon,
  Download,
  RefreshCw,
  BarChart2,
  BookOpen,
  Settings,
  Send,
  User,
  Bot,
  Layers,
  TrendingUp,
  Brain,
  Activity,
  FileSpreadsheet
} from 'lucide-react'


import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  LineChart,
  Line,
  CartesianGrid,
  Legend
} from 'recharts'

import type { AuditResponse, Status, DocumentAuditResult } from './types/audit'
import {
  runAudit,
  downloadReport,
  copilotChat,
  trainMLClassifier,
  getEvaluationData
} from './api/audit'
import { useDarkMode } from './hooks/useDarkMode'

function App() {
  const { dark, toggle } = useDarkMode()
  const [folderPath, setFolderPath] = useState('C:\\Users\\SHREYAS DESAI\\TrustAudit')
  const [status, setStatus] = useState<Status>('idle')
  const [data, setData] = useState<AuditResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'dashboard' | 'upload' | 'results' | 'policies' | 'analytics' | 'reports' | 'settings'>('upload')
  
  // States for Audit Results Detail
  const [selectedDocIndex, setSelectedDocIndex] = useState<number>(0)
  
  // States for Copilot
  const [chatQuery, setChatQuery] = useState('')
  const [chatHistory, setChatHistory] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([])
  const [chatLoading, setChatLoading] = useState(false)
  
  // Settings configs
  const [confidenceThreshold, setConfidenceThreshold] = useState(75)
  const [trainingStatus, setTrainingStatus] = useState<string | null>(null)
  const [evalData, setEvalData] = useState<any>(null)
  const [downloading, setDownloading] = useState<string | null>(null)

  // Load eval data on startup
  useEffect(() => {
    getEvaluationData()
      .then((res) => setEvalData(res))
      .catch(() => {});
  }, [])

  async function handleRun() {
    if (!folderPath.trim()) return
    setStatus('loading')
    setError(null)
    setData(null)
    setChatHistory([])
    try {
      const res = await runAudit(folderPath.trim())
      setData(res)
      setStatus('success')
      setActiveTab('dashboard') // Redirect to dashboard once audit completes
      setSelectedDocIndex(0)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
      setStatus('error')
      setActiveTab('upload')
    }
  }

  async function handleDownload(format: 'docx' | 'pdf') {
    if (!folderPath.trim()) return
    setDownloading(format)
    try {
      await downloadReport(folderPath.trim(), data?.report.audit_title, format)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed')
    } finally {
      setDownloading(null)
    }
  }

  async function handleSendChat() {
    if (!chatQuery.trim() || !data) return
    const userMsg = chatQuery.trim()
    setChatQuery('')
    const updatedHistory = [...chatHistory, { role: 'user' as const, content: userMsg }]
    setChatHistory(updatedHistory)
    setChatLoading(true)
    
    try {
      const answer = await copilotChat(
        userMsg,
        data.report.document_results,
        data.cross_verification,
        updatedHistory
      )
      setChatHistory([...updatedHistory, { role: 'assistant' as const, content: answer }])
    } catch (e) {
      setChatHistory([...updatedHistory, { role: 'assistant' as const, content: 'Failed to communicate with Auditor Copilot.' }])
    } finally {
      setChatLoading(false)
    }
  }

  async function handleTrainML() {
    setTrainingStatus('Training in progress...')
    try {
      const msg = await trainMLClassifier()
      setTrainingStatus(msg)
      // Refresh evaluations
      const ev = await getEvaluationData()
      setEvalData(ev)
    } catch (e) {
      setTrainingStatus(e instanceof Error ? e.message : 'Training failed')
    }
  }

  const currentDoc = data?.report.document_results[selectedDocIndex] as DocumentAuditResult | undefined

  // KPI Calculations helper
  const kpis = data?.analytics?.kpis || {
    total_audited: 0,
    compliance_rate: 100.0,
    average_score: 100.0,
    violations_detected: 0,
    high_risk_count: 0
  }

  const charts = data?.analytics?.charts || {
    risk_distribution: [],
    violation_frequency: [],
    compliance_trends: [],
    document_types: []
  }

  return (
    <div className="min-h-screen bg-surface-1 flex flex-col font-sans antialiased text-ink transition-colors duration-300">
      
      {/* 1. Brand Navigation Header */}
      <header className="sticky top-0 z-50 bg-surface-2 border-b border-border/80 backdrop-blur-md px-6 py-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <div className="bg-teal-600 p-2 rounded-xl text-white shadow-md shadow-teal-600/20">
            <Shield className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <h1 className="text-[19px] font-bold tracking-tight bg-gradient-to-r from-teal-600 to-emerald-500 bg-clip-text text-transparent">TrustAudit 🛡️</h1>
            <p className="text-[11px] text-muted -mt-0.5">Enterprise Compliance Platform</p>
          </div>
        </div>

        {/* Global Nav Tabs */}
        <nav className="hidden md:flex items-center gap-1 bg-surface-1 p-1 rounded-xl border border-border/60">
          {[
            { id: 'upload', label: 'Upload & Run', icon: Layers },
            { id: 'dashboard', label: 'Dashboard', icon: BarChart2, disabled: !data },
            { id: 'results', label: 'Audit Results', icon: FileText, disabled: !data },
            { id: 'policies', label: 'Policy Center', icon: BookOpen },
            { id: 'analytics', label: 'Analytics', icon: TrendingUp, disabled: !data },
            { id: 'reports', label: 'Reports', icon: FileSpreadsheet, disabled: !data },
            { id: 'settings', label: 'Settings & ML', icon: Settings }
          ].map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                disabled={tab.disabled}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-[13px] font-medium transition-all duration-200 cursor-pointer ${
                  isActive
                    ? 'bg-surface-2 text-teal-600 shadow-sm border border-border/40 font-semibold'
                    : 'text-muted hover:text-ink disabled:opacity-40 disabled:pointer-events-none'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-teal-600' : 'text-muted'}`} />
                {tab.label}
              </button>
            )
          })}
        </nav>

        {/* Dark Mode toggle & Status Indicators */}
        <div className="flex items-center gap-4">
          {data && (
            <div className="hidden lg:flex items-center gap-2 bg-teal-50 dark:bg-teal-500/10 px-3 py-1 rounded-full border border-teal-600/20">
              <span className="w-2.5 h-2.5 bg-teal-600 rounded-full animate-ping" />
              <span className="text-[11px] text-teal-600 font-semibold uppercase tracking-wider">Audit Active</span>
            </div>
          )}
          <button
            onClick={toggle}
            className="p-2 rounded-xl hover:bg-ink-50 border border-border/60 text-muted hover:text-ink cursor-pointer transition-colors"
            title="Toggle theme"
          >
            {dark ? '☀️' : '🌙'}
          </button>
        </div>
      </header>

      {/* 2. Main Workspace Layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-6">
        
        {/* Loading Spinner / Progress overlay */}
        {status === 'loading' && (
          <div className="bg-surface-2/90 border border-border/80 rounded-2xl p-8 flex flex-col items-center justify-center space-y-6 shadow-xl relative overflow-hidden backdrop-blur-sm min-h-[350px]">
            <div className="absolute top-0 left-0 w-full h-1 bg-ink-50 overflow-hidden">
              <div className="h-full bg-gradient-to-r from-teal-600 to-emerald-500 w-1/3 animate-[scan_2s_infinite]" />
            </div>
            <div className="bg-teal-50 dark:bg-teal-600/10 p-5 rounded-full text-teal-600 border border-teal-600/20 animate-spin">
              <Activity className="w-10 h-10" />
            </div>
            <div className="text-center space-y-2 max-w-md">
              <h3 className="text-[18px] font-bold text-ink">Running AI Compliance Agent</h3>
              <p className="text-[13px] text-muted">
                Parsing documents, indexing RAG database, checking math accuracy, running ML Random Forest classification, and validating compliance rules...
              </p>
            </div>
          </div>
        )}

        {/* Error Notification */}
        {status === 'error' && error && (
          <div className="bg-coral-50 border border-coral-600/30 text-coral-600 p-4 rounded-xl flex items-start gap-3">
            <AlertOctagon className="w-5 h-5 shrink-0 mt-0.5" />
            <div>
              <p className="text-[14px] font-semibold">Audit Execution Mismatch</p>
              <p className="text-[12px] opacity-90">{error}</p>
            </div>
          </div>
        )}

        {/* TAB CONTENTS */}

        {/* UPLOAD & INITIALIZATION TAB */}
        {activeTab === 'upload' && status !== 'loading' && (
          <div className="max-w-2xl mx-auto space-y-6">
            <div className="bg-surface-2 border border-border/70 rounded-2xl p-8 shadow-sm space-y-6">
              <div className="text-center space-y-2">
                <div className="bg-teal-50 dark:bg-teal-600/10 w-12 h-12 rounded-xl flex items-center justify-center text-teal-600 mx-auto border border-teal-600/10">
                  <Shield className="w-6 h-6" />
                </div>
                <h2 className="text-[20px] font-bold text-ink">Compliance Platform Orchestrator</h2>
                <p className="text-[13px] text-muted max-w-md mx-auto">
                  Provide the local path of the directory containing your business documents (Invoice, Purchase Order, Receipt) to run explainable audits and RAG evaluations.
                </p>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-[12px] font-bold uppercase tracking-wider text-muted mb-1.5">
                    Target Workspace Folder Path
                  </label>
                  <input
                    value={folderPath}
                    onChange={(e) => setFolderPath(e.target.value)}
                    placeholder="e.g. C:\Users\...\sample_docs"
                    className="w-full border border-border rounded-xl px-4 py-3 text-[14px] text-ink bg-surface-1 placeholder:text-muted/40 outline-none focus:ring-2 focus:ring-teal-600/20 focus:border-teal-600 transition-all font-mono"
                  />
                </div>

                <button
                  onClick={handleRun}
                  disabled={!folderPath.trim()}
                  className="w-full bg-teal-600 hover:bg-teal-700 text-white py-3.5 rounded-xl text-[14px] font-bold tracking-wide transition-all shadow-md shadow-teal-600/10 hover:shadow-teal-700/20 disabled:opacity-40 disabled:pointer-events-none cursor-pointer flex items-center justify-center gap-2"
                >
                  <RefreshCw className="w-4 h-4 animate-spin-slow" />
                  Initialize Compliance Audit
                </button>
              </div>
            </div>

            {/* Quick Helper Notes */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                { title: 'Three-Way Match', desc: 'Auto-align Invoice, PO, and Receipts to verify cross-document gaps.', icon: Layers },
                { title: 'Explainable RAG', desc: 'Cites legal and corporate rules retrieved from vector database.', icon: BookOpen },
                { title: 'RF Prediction', desc: 'Classifies compliance via Random Forest risk predictive models.', icon: Brain }
              ].map((item, i) => {
                const Icon = item.icon
                return (
                  <div key={i} className="bg-surface-2 border border-border/50 rounded-xl p-4 flex gap-3 items-start">
                    <div className="bg-teal-50 dark:bg-teal-600/10 text-teal-600 p-2 rounded-lg border border-teal-600/10 shrink-0">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-[13px] font-semibold text-ink">{item.title}</h4>
                      <p className="text-[11px] text-muted mt-0.5 leading-relaxed">{item.desc}</p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* DASHBOARD TAB */}
        {activeTab === 'dashboard' && data && (
          <div className="space-y-6">
            
            {/* KPI Cards row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
              {[
                { label: 'Audited Files', val: kpis.total_audited, desc: 'Total processed', icon: FileText, color: 'text-blue-600 bg-blue-50 dark:bg-blue-500/10 border-blue-600/10' },
                { label: 'Compliance Rate', val: `${kpis.compliance_rate}%`, desc: 'Docs passed rules', icon: CheckCircle, color: 'text-teal-600 bg-teal-50 dark:bg-teal-500/10 border-teal-600/10' },
                { label: 'Average Score', val: `${kpis.average_score.toFixed(1)}%`, desc: 'Weighted average', icon: TrendingUp, color: 'text-indigo-600 bg-indigo-50 dark:bg-indigo-500/10 border-indigo-600/10' },
                { label: 'Violations Detected', val: kpis.violations_detected, desc: 'Failed audit rules', icon: AlertTriangle, color: 'text-amber-600 bg-amber-50 dark:bg-amber-500/10 border-amber-600/10' },
                { label: 'High Risk Documents', val: kpis.high_risk_count, desc: 'Require review', icon: AlertOctagon, color: 'text-coral-600 bg-coral-50 dark:bg-coral-500/10 border-coral-600/10' }
              ].map((kpi, idx) => {
                const Icon = kpi.icon
                return (
                  <div key={idx} className="bg-surface-2 border border-border/70 rounded-xl p-5 shadow-sm space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] text-muted font-medium">{kpi.label}</span>
                      <div className={`p-2 rounded-lg border ${kpi.color}`}>
                        <Icon className="w-4 h-4" />
                      </div>
                    </div>
                    <div>
                      <h3 className="text-[22px] font-bold text-ink tracking-tight">{kpi.val}</h3>
                      <p className="text-[11px] text-muted mt-0.5">{kpi.desc}</p>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Three-Way Matching Alert Banner */}
            {data.cross_verification && (
              <div className={`border rounded-xl p-5 shadow-sm flex items-start gap-4 ${
                data.cross_verification.is_consistent 
                  ? 'bg-teal-50/50 dark:bg-teal-500/5 border-teal-600/20 text-teal-600'
                  : 'bg-coral-50/50 dark:bg-coral-500/5 border-coral-600/20 text-coral-600'
              }`}>
                <div className={`p-2 rounded-lg ${
                  data.cross_verification.is_consistent ? 'bg-teal-600/10' : 'bg-coral-600/10'
                }`}>
                  <Layers className="w-5 h-5" />
                </div>
                <div className="flex-1 space-y-1">
                  <h4 className="text-[14px] font-bold uppercase tracking-wider">
                    Three-Way Match Verification Result: {data.cross_verification.status}
                  </h4>
                  <p className="text-[12px] text-muted leading-relaxed">
                    {data.cross_verification.reconciliation_summary}
                  </p>
                  
                  {/* List Discrepancies if any */}
                  {!data.cross_verification.is_consistent && (
                    <div className="mt-3 space-y-2 border-t border-border/40 pt-3">
                      {data.cross_verification.discrepancies
                        .filter((d: any) => d.status === 'mismatch')
                        .map((d: any, i: number) => (
                          <div key={i} className="flex gap-2 text-[11px] text-coral-600 bg-coral-50 dark:bg-coral-500/10 px-3 py-1.5 rounded-lg border border-coral-600/10">
                            <span className="font-bold uppercase shrink-0">[{d.check_type}]</span>
                            <span>{d.details}</span>
                          </div>
                        ))
                      }
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Visual Charts Overview */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              
              {/* Risk Distribution Chart */}
              <div className="bg-surface-2 border border-border/70 rounded-2xl p-5 shadow-sm">
                <h3 className="text-[14px] font-bold uppercase tracking-wider text-muted mb-4">Risk Distribution</h3>
                <div className="h-64 flex items-center justify-center">
                  {charts.risk_distribution.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={charts.risk_distribution}
                          cx="50%"
                          cy="50%"
                          innerRadius={60}
                          outerRadius={90}
                          paddingAngle={5}
                          dataKey="value"
                        >
                          {charts.risk_distribution.map((entry: any, index: number) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--ink)' }} />
                        <Legend verticalAlign="bottom" height={36} />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-[12px] text-muted">No distribution data available</p>
                  )}
                </div>
              </div>

              {/* Compliance Trends Chart */}
              <div className="bg-surface-2 border border-border/70 rounded-2xl p-5 shadow-sm">
                <h3 className="text-[14px] font-bold uppercase tracking-wider text-muted mb-4">Compliance History Trend</h3>
                <div className="h-64">
                  {charts.compliance_trends.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={charts.compliance_trends} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.3} />
                        <XAxis dataKey="period" stroke="var(--ink-muted)" fontSize={11} />
                        <YAxis stroke="var(--ink-muted)" fontSize={11} domain={[0, 100]} />
                        <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--ink)' }} />
                        <Legend verticalAlign="bottom" height={36} />
                        <Line type="monotone" dataKey="compliance_rate" name="Compliance Rate (%)" stroke="#0F6E56" strokeWidth={2.5} activeDot={{ r: 8 }} />
                        <Line type="monotone" dataKey="average_score" name="Avg Score (%)" stroke="#185FA5" strokeWidth={2} strokeDasharray="5 5" />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-[12px] text-muted">No trend data available</p>
                  )}
                </div>
              </div>

            </div>

            {/* High-Risk Documents Alerts list */}
            <div className="bg-surface-2 border border-border/70 rounded-2xl p-6 shadow-sm space-y-4">
              <h3 className="text-[14px] font-bold uppercase tracking-wider text-muted">Workspace Documents Compliance</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-border/80 text-[12px] text-muted font-semibold">
                      <th className="pb-3 pr-4">File Name</th>
                      <th className="pb-3 px-4">Doc Type</th>
                      <th className="pb-3 px-4">Score</th>
                      <th className="pb-3 px-4">Risk Category</th>
                      <th className="pb-3 px-4">ML Prediction</th>
                      <th className="pb-3 px-4 text-right">Confidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40 text-[13px]">
                    {data.report.document_results.map((doc, idx) => {
                      return (
                        <tr key={idx} className="hover:bg-ink-50/35 transition-colors cursor-pointer" onClick={() => {

                          setSelectedDocIndex(idx)
                          setActiveTab('results')
                        }}>
                          <td className="py-3.5 pr-4 font-semibold text-ink max-w-[220px] truncate">{doc.document_name}</td>
                          <td className="py-3.5 px-4 text-muted uppercase text-[11px] tracking-wider">{doc.document_type.replace('_', ' ')}</td>
                          <td className="py-3.5 px-4 font-mono font-bold text-ink">{doc.score === null ? 'Not audited' : `${doc.score.toFixed(1)}%`}</td>
                          <td className="py-3.5 px-4">
                            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide border ${
                              doc.risk_level === 'High Risk' 
                                ? 'bg-coral-50 border-coral-600/20 text-coral-600'
                                : (doc.risk_level === 'Medium Risk' ? 'bg-amber-50 border-amber-600/20 text-amber-600' : 'bg-teal-50 border-teal-600/20 text-teal-600')
                            }`}>
                              {doc.risk_level}
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-muted">
                            {doc.ml_prediction?.prediction || 'N/A'}
                          </td>
                          <td className="py-3.5 px-4 text-right font-mono text-ink">
                            {doc.confidence_score.toFixed(1)}%
                            {doc.human_review_recommended && (
                              <span className="text-coral-600 ml-1.5" title="Human Review Recommended">⚠️</span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>

          </div>
        )}

        {/* AUDIT RESULTS TAB */}
        {activeTab === 'results' && data && currentDoc && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            
            {/* Left Sidebar Document selector & ML metrics */}
            <div className="lg:col-span-4 space-y-6">
              
              {/* Selector */}
              <div className="bg-surface-2 border border-border/70 rounded-2xl p-5 shadow-sm space-y-4">
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-muted mb-1.5">
                    Select Document
                  </label>
                  <select
                    value={selectedDocIndex}
                    onChange={(e) => setSelectedDocIndex(Number(e.target.value))}
                    className="w-full border border-border rounded-xl px-3 py-2.5 text-[13px] text-ink bg-surface-1 outline-none focus:border-teal-600 cursor-pointer"
                  >
                    {data.report.document_results.map((doc, idx) => (
                      <option key={idx} value={idx}>
                        {idx + 1}. {doc.document_name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="border-t border-border/50 pt-4 space-y-2 text-[12px]">
                  <div className="flex justify-between">
                    <span className="text-muted">Inferred Format:</span>
                    <span className="font-semibold uppercase tracking-wider text-[11px]">{currentDoc.document_type}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Total Pages:</span>
                    <span className="font-semibold text-ink">{currentDoc.page_count} page(s)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Audit Score:</span>
                    <span className="font-mono font-bold text-ink">{currentDoc.score === null ? 'Not audited' : `${currentDoc.score.toFixed(1)}%`}</span>
                  </div>
                </div>
              </div>

              {/* ML Risk Prediction Panel */}
              <div className="bg-surface-2 border border-border/70 rounded-2xl p-5 shadow-sm space-y-4">
                <div className="flex items-center gap-2">
                  <Brain className="w-5 h-5 text-indigo-600" />
                  <h3 className="text-[13px] font-bold uppercase tracking-wider text-muted">ML Classification Analysis</h3>
                </div>

                {currentDoc.ml_prediction ? (
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between items-baseline mb-1">
                        <span className="text-[12px] text-muted">Predicted Category:</span>
                        <span className="text-[14px] font-bold text-indigo-600">{currentDoc.ml_prediction.prediction}</span>
                      </div>
                      <p className="text-[10px] text-muted">Computed via Random Forest Model.</p>
                    </div>

                    {/* Progress bars */}
                    <div className="space-y-2 pt-2 border-t border-border/50">
                      {[
                        { label: 'Compliant', val: currentDoc.ml_prediction.probabilities.compliant, color: 'bg-teal-600' },
                        { label: 'Partially Compliant', val: currentDoc.ml_prediction.probabilities.partially_compliant, color: 'bg-amber-500' },
                        { label: 'Non-Compliant', val: currentDoc.ml_prediction.probabilities.non_compliant, color: 'bg-coral-600' }
                      ].map((item, idx) => (
                        <div key={idx} className="space-y-1">
                          <div className="flex justify-between text-[11px]">
                            <span className="text-muted">{item.label}</span>
                            <span className="font-mono font-semibold text-ink">{item.val.toFixed(1)}%</span>
                          </div>
                          <div className="w-full bg-ink-50 rounded-full h-1.5">
                            <div className={`h-1.5 rounded-full ${item.color}`} style={{ width: `${item.val}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-[12px] text-muted italic">Random Forest predictive logs unavailable.</p>
                )}
              </div>

              {/* Confidence Score Warning card */}
              <div className={`border rounded-2xl p-5 shadow-sm space-y-3 ${
                currentDoc.human_review_recommended 
                  ? 'bg-coral-50/50 dark:bg-coral-500/5 border-coral-600/20 text-coral-600' 
                  : 'bg-teal-50/50 dark:bg-teal-500/5 border-teal-600/20 text-teal-600'
              }`}>
                <div className="flex justify-between items-center">
                  <span className="text-[12px] font-bold uppercase tracking-wider text-muted">Audit Confidence</span>
                  <span className="font-mono font-bold text-ink">{currentDoc.confidence_score.toFixed(1)}%</span>
                </div>
                {currentDoc.human_review_recommended ? (
                  <div className="space-y-2">
                    <p className="text-[11px] text-muted leading-relaxed">
                      ⚠️ **Human Review Recommended**: The aggregated AI parsing confidence or predictive certainty falls below the {confidenceThreshold}% limit, or the risk score indicates compliance mismatch. Manual review of the document details is highly recommended.
                    </p>
                  </div>
                ) : (
                  <p className="text-[11px] text-muted leading-relaxed">
                    ✅ **High Confidence**: The automated audit is highly consistent with standard compliance patterns.
                  </p>
                )}
              </div>

              {/* Image Evidence Viewer */}
              {currentDoc.preview_base64 && (
                <div className="bg-surface-2 border border-border/70 rounded-2xl p-5 shadow-sm space-y-3">
                  <h4 className="text-[12px] font-bold uppercase tracking-wider text-muted">Visual Evidence Source</h4>
                  <div className="w-full h-48 rounded-lg border border-border overflow-hidden bg-surface-1 flex items-center justify-center relative group">
                    <img
                      src={`data:image/jpeg;base64,${currentDoc.preview_base64}`}
                      alt="Evidence Document First Page"
                      className="max-w-full max-h-full object-contain cursor-zoom-in hover:scale-110 transition-transform duration-300"
                    />
                  </div>
                  <p className="text-[10px] text-muted text-center italic">Document Page 1 Thumbnail</p>
                </div>
              )}

            </div>

            {/* Right Workstation: Explainable Findings & Copilot */}
            <div className="lg:col-span-8 space-y-6">
              
              {/* Document Overview card */}
              <div className="bg-surface-2 border border-border/70 rounded-2xl p-6 shadow-sm space-y-3">
                <h2 className="text-[18px] font-bold text-ink">{currentDoc.document_name}</h2>
                <p className="text-[13px] text-muted italic">"{currentDoc.summary_text}"</p>
                <div className="border-t border-border/50 pt-3">
                  <h4 className="text-[11px] font-bold uppercase tracking-wider text-muted mb-1">Risk Scorer Notes</h4>
                  <p className="text-[12px] text-muted leading-relaxed">{currentDoc.risk_explanation}</p>
                </div>
              </div>

              {/* Explainable Findings Panel */}
              <div className="bg-surface-2 border border-border/70 rounded-2xl p-6 shadow-sm space-y-4">
                <div className="flex justify-between items-center border-b border-border/50 pb-3">
                  <h3 className="text-[14px] font-bold uppercase tracking-wider text-muted">Compliance Findings & Citations</h3>
                  <span className="text-[12px] text-muted font-medium">{currentDoc.failed_rules.length} failures found</span>
                </div>

                {currentDoc.failed_rules.length > 0 ? (
                  <div className="space-y-4">
                    {currentDoc.failed_rules.map((rule, index) => (
                      <div key={index} className="border border-border/60 rounded-xl overflow-hidden shadow-sm">
                        
                        {/* Header bar */}
                        <div className="bg-surface-1 border-b border-border/60 px-4 py-3 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide border ${
                              rule.severity === 'critical' || rule.severity === 'high' 
                                ? 'bg-coral-50 border-coral-600/25 text-coral-600' 
                                : 'bg-amber-50 border-amber-600/25 text-amber-600'
                            }`}>
                              {rule.severity}
                            </span>
                            <span className="text-[13px] font-bold text-ink">
                              {rule.rule_id}: {rule.rule_title}
                            </span>
                          </div>
                          {rule.page_number !== null && (
                            <span className="text-[11px] text-muted font-medium">Page {rule.page_number}</span>
                          )}
                        </div>

                        {/* Expandable details */}
                        <div className="p-4 space-y-3 text-[12.5px] leading-relaxed">
                          <div className="bg-surface-1 px-3 py-2 rounded-lg border border-border/30">
                            <p className="text-muted font-medium uppercase text-[10px] tracking-wider mb-0.5">Finding & Observed Evidence</p>
                            <p className="text-ink font-semibold">{rule.finding}</p>
                            <p className="text-coral-600 font-mono mt-1 text-[12px] bg-coral-50/50 p-2 rounded border border-coral-600/10">Evidence: {rule.evidence}</p>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div className="bg-surface-1/40 px-3 py-2 rounded-lg border border-border/20">
                              <p className="text-muted font-medium uppercase text-[10px] tracking-wider mb-0.5">Policy Citation & Impact</p>
                              <p className="text-muted">{rule.impact}</p>
                            </div>
                            <div className="bg-surface-1/40 px-3 py-2 rounded-lg border border-border/20">
                              <p className="text-muted font-medium uppercase text-[10px] tracking-wider mb-0.5">Remediation Action</p>
                              <p className="text-teal-600 font-medium">{rule.recommendation}</p>
                            </div>
                          </div>
                        </div>

                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center p-8 text-center space-y-2">
                    <CheckCircle className="w-10 h-10 text-teal-600" />
                    <h4 className="text-[14px] font-bold text-ink">Perfect Policy Compliance</h4>
                    <p className="text-[12px] text-muted max-w-sm">
                      This document passes all checked standard parameters from RAG vector store and checklists without any compliance discrepancies.
                    </p>
                  </div>
                )}
              </div>

              {/* Auditor Copilot panel */}
              <div className="bg-surface-2 border border-border/70 rounded-2xl p-6 shadow-sm flex flex-col h-[400px]">
                
                {/* Header */}
                <div className="flex items-center gap-3 border-b border-border/50 pb-3 mb-4 shrink-0">
                  <div className="bg-teal-600 p-1.5 rounded-lg text-white">
                    <Bot className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-[13px] font-bold uppercase tracking-wider text-muted">Auditor Copilot</h4>
                    <p className="text-[10px] text-muted">Grounded conversational compliance model</p>
                  </div>
                </div>

                {/* Conversation Box */}
                <div className="flex-1 overflow-y-auto space-y-4 pr-1 mb-4 text-[12.5px]">
                  {chatHistory.length === 0 && (
                    <div className="text-center text-muted p-8 italic">
                      Ask me questions about the audit results, matching mismatches, or violation parameters.
                    </div>
                  )}
                  {chatHistory.map((msg, index) => {
                    const isUser = msg.role === 'user'
                    return (
                      <div key={index} className={`flex items-start gap-2.5 ${isUser ? 'justify-end' : 'justify-start'}`}>
                        {!isUser && (
                          <div className="bg-teal-50 text-teal-600 p-1.5 rounded border border-teal-600/10 shrink-0">
                            <Bot className="w-3.5 h-3.5" />
                          </div>
                        )}
                        <div className={`p-3 rounded-xl max-w-[80%] leading-relaxed ${
                          isUser 
                            ? 'bg-teal-600 text-white rounded-br-none' 
                            : 'bg-surface-1 border border-border/50 text-ink rounded-bl-none'
                        }`}>
                          {msg.content}
                        </div>
                        {isUser && (
                          <div className="bg-blue-50 text-blue-600 p-1.5 rounded border border-blue-600/10 shrink-0">
                            <User className="w-3.5 h-3.5" />
                          </div>
                        )}
                      </div>
                    )
                  })}
                  {chatLoading && (
                    <div className="flex items-start gap-2.5">
                      <div className="bg-teal-50 text-teal-600 p-1.5 rounded border border-teal-600/10 shrink-0 animate-bounce">
                        <Bot className="w-3.5 h-3.5" />
                      </div>
                      <div className="bg-surface-1 border border-border/50 text-muted p-3 rounded-xl rounded-bl-none">
                        Copilot is retrieving policy details...
                      </div>
                    </div>
                  )}
                </div>

                {/* Input form */}
                <div className="flex gap-2 shrink-0">
                  <input
                    value={chatQuery}
                    onChange={(e) => setChatQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSendChat()}
                    placeholder="Ask why a rule failed, or how to mitigate the risk..."
                    className="flex-1 border border-border rounded-xl px-4 py-2.5 text-[13px] text-ink bg-surface-1 outline-none focus:border-teal-600"
                  />
                  <button
                    onClick={handleSendChat}
                    className="bg-teal-600 hover:bg-teal-700 text-white px-4 py-2.5 rounded-xl transition-all cursor-pointer shadow shadow-teal-600/10"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>

              </div>

            </div>

          </div>
        )}

        {/* POLICY CENTER TAB */}
        {activeTab === 'policies' && (
          <div className="max-w-4xl mx-auto space-y-6">
            <div className="bg-surface-2 border border-border/70 rounded-2xl p-6 shadow-sm flex items-center justify-between">
              <div>
                <h2 className="text-[18px] font-bold text-ink">Compliance Policies Registry (RAG Store)</h2>
                <p className="text-[13px] text-muted">
                  These regulatory compliance policies are ingested in the ChromaDB vector database.
                </p>
              </div>
              <button
                onClick={handleRun}
                className="px-4 py-2 text-[12px] font-bold border border-teal-600 text-teal-600 rounded-xl hover:bg-teal-50 transition-colors cursor-pointer flex items-center gap-2"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Re-Index ChromaDB
              </button>
            </div>

            {/* List checklist rules */}
            <div className="space-y-4">
              {[
                { rid: 'R001', title: 'Document Legibility', sev: 'medium', mand: false, desc: 'Text, numbers, and key headers should be readable. Minor scan blur is logged as medium risk.' },
                { rid: 'R002', title: 'Mandatory Fields Present', sev: 'medium', mand: false, desc: 'Evaluates header fields based on specific document type. Missing optional fields on simple bills are not penalized as high severity.' },
                { rid: 'R003', title: 'Mathematical Accuracy', sev: 'critical', mand: true, desc: 'Core financial integrity check. Line items, subtotal sum, tax splits, discounts, and grand totals must be exact.' },
                { rid: 'R004', title: 'Authorization & Signatures', sev: 'medium', mand: false, desc: 'Signatures, stamps, or digital seals are checked where applicable. Computer tax invoices without physical stamps are medium severity.' },
                { rid: 'R005', title: 'Date Validity & Future Dates', sev: 'high', mand: true, desc: 'Dates must be valid and chronologically sound. Documents dated in the future or expired certificates are High Severity violations.' },
                { rid: 'R006', title: 'Currency & Amount Consistency', sev: 'high', mand: true, desc: 'Monetary values must use a single consistent currency symbol throughout, and line items must reconcile with total figure.' },
                { rid: 'R007', title: 'Vendor / Customer Info Completeness', sev: 'medium', mand: false, desc: 'Checks presence of legal vendor/customer names. Detailed street addresses or secondary IDs are medium severity if omitted.' },
                { rid: 'R008', title: 'Document Number Uniqueness', sev: 'low', mand: false, desc: 'Document numbering sequence variations are logged as low-severity audit notes.' },
                { rid: 'R009', title: 'Payment Terms & Due Date', sev: 'low', mand: false, desc: 'Payment schedules (Net 30) apply primarily to credit invoices. Omission on cash receipts or delivery notes is low severity.' },
                { rid: 'R010', title: 'Tax Breakdown & Compliance', sev: 'medium', mand: false, desc: 'Tax breakdowns are evaluated when applicable. Non-taxable receipts or simple bills without tax breakdowns are medium severity.' }
              ].map((policy, index) => (

                <div key={index} className="bg-surface-2 border border-border/60 rounded-xl p-5 shadow-sm grid grid-cols-1 md:grid-cols-4 gap-4 items-start">
                  <div className="md:col-span-1 space-y-1">
                    <span className="font-mono text-[11px] text-muted uppercase tracking-wider">Policy Registry</span>
                    <h4 className="text-[14px] font-bold text-ink">{policy.rid}: {policy.title}</h4>
                    <div className="flex gap-2 pt-1.5">
                      <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider border ${
                        policy.sev === 'critical' || policy.sev === 'high' ? 'bg-coral-50 border-coral-600/20 text-coral-600' : 'bg-gray-50 border-gray-400/20 text-muted'
                      }`}>
                        {policy.sev}
                      </span>
                      {policy.mand && (
                        <span className="px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-teal-50 border border-teal-600/20 text-teal-600">
                          Mandatory
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="md:col-span-3 text-[12.5px] leading-relaxed text-muted">
                    <p className="font-semibold text-ink">Description:</p>
                    <p>{policy.desc}</p>
                  </div>
                </div>
              ))}
            </div>

          </div>
        )}

        {/* ANALYTICS TAB */}
        {activeTab === 'analytics' && data && (
          <div className="space-y-6">
            <div className="bg-surface-2 border border-border/70 rounded-2xl p-6 shadow-sm">
              <h2 className="text-[18px] font-bold text-ink">Compliance Analytics Engine</h2>
              <p className="text-[13px] text-muted">
                Visualizing rule failures, violation frequencies, and risk metrics dynamically.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              
              {/* Pie document types */}
              <div className="bg-surface-2 border border-border/70 rounded-2xl p-5 shadow-sm space-y-4">
                <h3 className="text-[14px] font-bold uppercase tracking-wider text-muted">Document Types Breakdowns</h3>
                <div className="h-64 flex items-center justify-center">
                  {charts.document_types.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={charts.document_types}
                          cx="50%"
                          cy="50%"
                          outerRadius={80}
                          label={({ name, percent }: { name?: string; percent?: number }) => `${name || ''} (${((percent ?? 0) * 100).toFixed(0)}%)`}
                          dataKey="value"
                        >
                          {charts.document_types.map((_: any, index: number) => (

                            <Cell key={`cell-${index}`} fill={['#0F6E56', '#185FA5', '#D97706', '#993C1D', '#6B7280'][index % 5]} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-[12px] text-muted text-center">No type split available.</p>
                  )}
                </div>
              </div>

              {/* Violation Frequency Chart */}
              <div className="bg-surface-2 border border-border/70 rounded-2xl p-5 shadow-sm space-y-4">
                <h3 className="text-[14px] font-bold uppercase tracking-wider text-muted">Policy Violation Frequency</h3>
                <div className="h-64">
                  {charts.violation_frequency.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={charts.violation_frequency} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.2} stroke="var(--border)" />
                        <XAxis dataKey="rule_id" stroke="var(--ink-muted)" fontSize={11} />
                        <YAxis stroke="var(--ink-muted)" fontSize={11} allowDecimals={false} />
                        <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--ink)' }} />
                        <Bar dataKey="count" name="Violations Count" fill="#993C1D" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-center text-muted text-[12px] italic">
                      Zero violations registered. Compliant platform operations!
                    </div>
                  )}
                </div>
              </div>

            </div>
          </div>
        )}

        {/* REPORTS DOWNLOAD TAB */}
        {activeTab === 'reports' && data && (
          <div className="max-w-2xl mx-auto bg-surface-2 border border-border/70 rounded-2xl p-8 shadow-sm space-y-6">
            <div className="text-center space-y-2">
              <Download className="w-10 h-10 text-teal-600 mx-auto" />
              <h2 className="text-[20px] font-bold text-ink">Export Advanced Compliance Reports</h2>
              <p className="text-[13px] text-muted">
                Download structured auditing reports including executive summaries, RAG policy citations, risk evaluations, and predictions.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
              
              {/* DOCX Card */}
              <div className="border border-border/60 rounded-xl p-5 hover:border-teal-600/35 transition-all space-y-4 flex flex-col justify-between">
                <div>
                  <h4 className="text-[14px] font-bold text-ink">Microsoft Word Document (.docx)</h4>
                  <p className="text-[11.5px] text-muted mt-1 leading-relaxed">
                    Corporate Word document layout containing standard headings, table grids of violations, and full findings lists.
                  </p>
                </div>
                <button
                  onClick={() => handleDownload('docx')}
                  disabled={downloading !== null}
                  className="w-full bg-teal-600 hover:bg-teal-700 text-white py-2 rounded-xl text-[12.5px] font-bold transition-all cursor-pointer disabled:opacity-40"
                >
                  {downloading === 'docx' ? 'Exporting...' : 'Download DOCX'}
                </button>
              </div>

              {/* PDF Card */}
              <div className="border border-border/60 rounded-xl p-5 hover:border-teal-600/35 transition-all space-y-4 flex flex-col justify-between">
                <div>
                  <h4 className="text-[14px] font-bold text-ink">PDF Regulatory Report (.pdf)</h4>
                  <p className="text-[11.5px] text-muted mt-1 leading-relaxed">
                    Structured PDF layout featuring color-coded headers, bulleted risk assessments, and RAG vector search references.
                  </p>
                </div>
                <button
                  onClick={() => handleDownload('pdf')}
                  disabled={downloading !== null}
                  className="w-full bg-teal-600 hover:bg-teal-700 text-white py-2 rounded-xl text-[12.5px] font-bold transition-all cursor-pointer disabled:opacity-40"
                >
                  {downloading === 'pdf' ? 'Exporting...' : 'Download PDF'}
                </button>
              </div>

            </div>
          </div>
        )}

        {/* SETTINGS & ML TAB */}
        {activeTab === 'settings' && (
          <div className="max-w-3xl mx-auto space-y-6">
            
            {/* Risk Configuration and confidence limits */}
            <div className="bg-surface-2 border border-border/70 rounded-2xl p-6 shadow-sm space-y-4">
              <h3 className="text-[14px] font-bold uppercase tracking-wider text-muted">Auditing Parameters Settings</h3>
              
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between items-baseline mb-1.5">
                    <label className="text-[12px] font-bold text-ink">Confidence Score Threshold: {confidenceThreshold}%</label>
                    <span className="text-[11px] text-muted">Flags human review recommendation if confidence dips below this.</span>
                  </div>
                  <input
                    type="range"
                    min="50"
                    max="95"
                    value={confidenceThreshold}
                    onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                    className="w-full accent-teal-600 cursor-pointer"
                  />
                </div>
              </div>
            </div>

            {/* Random Forest Classifier train engine */}
            <div className="bg-surface-2 border border-border/70 rounded-2xl p-6 shadow-sm space-y-4">
              <div className="flex items-center gap-3">
                <Brain className="w-5 h-5 text-indigo-600" />
                <h3 className="text-[14px] font-bold uppercase tracking-wider text-muted">ML Random Forest Training Console</h3>
              </div>
              <p className="text-[12.5px] text-muted leading-relaxed">
                Train the local Random Forest Classifier. Triggering this training pipeline generates a synthetic history dataset of 500+ audit transactions to fit features like rule fail flags and total scores to predict overall document compliance categorization (Compliant, Partially Compliant, Non-Compliant).
              </p>
              
              <div className="pt-2 flex items-center gap-4">
                <button
                  onClick={handleTrainML}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl text-[13px] font-bold transition-all shadow shadow-indigo-600/10 cursor-pointer"
                >
                  Trigger Classifier Training Pipeline
                </button>
                {trainingStatus && (
                  <span className="text-[12px] text-indigo-600 font-medium animate-pulse">{trainingStatus}</span>
                )}
              </div>
            </div>

            {/* Model Evaluation Framework report */}
            {evalData && (
              <div className="bg-surface-2 border border-border/70 rounded-2xl p-6 shadow-sm space-y-4">
                <div className="flex items-center gap-3">
                  <Activity className="w-5 h-5 text-teal-600" />
                  <h3 className="text-[14px] font-bold uppercase tracking-wider text-muted">Platform Evaluation Framework Benchmark</h3>
                </div>
                <p className="text-[12.5px] text-muted">
                  Performance evaluations evaluated against mock ground-truth benchmark datasets for the compliance engine:
                </p>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { label: 'Platform Accuracy', val: `${(evalData.accuracy * 100).toFixed(1)}%` },
                    { label: 'Precision Rating', val: `${(evalData.precision * 100).toFixed(1)}%` },
                    { label: 'Recall Rating', val: `${(evalData.recall * 100).toFixed(1)}%` },
                    { label: 'F1 Compliance Score', val: `${(evalData.f1_score * 100).toFixed(1)}%` },
                    { label: 'False Positive Rate', val: `${(evalData.false_positive_rate * 100).toFixed(1)}%` },
                    { label: 'False Negative Rate', val: `${(evalData.false_negative_rate * 100).toFixed(1)}%` },
                    { label: 'Avg Latency per file', val: `${evalData.average_latency_seconds}s` },
                    { label: 'Avg Inference Certainty', val: `${evalData.average_confidence_score}%` }
                  ].map((metric, i) => (
                    <div key={i} className="bg-surface-1 p-3 rounded-lg border border-border/40 text-center">
                      <p className="text-[10px] text-muted font-medium uppercase tracking-wide">{metric.label}</p>
                      <p className="text-[15px] font-bold text-ink mt-0.5 font-mono">{metric.val}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        )}

      </main>

      {/* Footer */}
      <footer className="bg-surface-2 border-t border-border/80 px-6 py-4 text-center text-muted text-[11px] shrink-0 mt-8">
        TrustAudit platform built via Google Gemini VLM & LangGraph compliance routing. All rights reserved &copy; 2026.
      </footer>

    </div>
  )
}

export default App
