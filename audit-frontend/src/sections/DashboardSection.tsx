import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { DocumentAuditResult } from '../types/audit'
import { FlatCard } from '../components/FlatCard'
import { MetricCard } from '../components/MetricCard'

const RISK_COLORS: Record<string, string> = {
  'Low Risk': '#0F6E56',
  'Medium Risk': '#D97706',
  'High Risk': '#993C1D',
}

interface DashboardSectionProps {
  documents: DocumentAuditResult[]
  executiveSummary?: string
  onOpenDocument?: (documentId: string) => void
}

export function DashboardSection({ documents, executiveSummary, onOpenDocument }: DashboardSectionProps) {
  const total = documents.length
  const audited = documents.filter((d) => d.audit_status !== 'NOT_AUDITED' && d.score !== null).length
  const passed = documents.filter((d) => d.passed).length
  const scored = documents.filter((d) => d.score !== null)
  const avg = scored.length ? scored.reduce((s, d) => s + (d.score ?? 0), 0) / scored.length : 0
  const violations = documents.reduce((s, d) => s + d.failed_rules.length, 0)
  const highRisk = documents.filter((d) => d.risk_level === 'High Risk').length
  const incomplete = documents.filter((d) => d.document_status !== 'READY').length
  const reviewRequired = documents.filter((d) => d.human_review_recommended).length

  const riskMap: Record<string, number> = {}
  for (const d of documents) riskMap[d.risk_level] = (riskMap[d.risk_level] ?? 0) + 1
  const riskData = Object.entries(riskMap).map(([name, value]) => ({
    name,
    value,
    color: RISK_COLORS[name] ?? '#6B7280',
  }))

  const freq = new Map<string, { rule_id: string; title: string; count: number }>()
  for (const d of documents) {
    for (const r of d.failed_rules) {
      const cur = freq.get(r.rule_id) ?? { rule_id: r.rule_id, title: r.rule_title, count: 0 }
      cur.count += 1
      freq.set(r.rule_id, cur)
    }
  }
  const violationData = [...freq.values()].sort((a, b) => b.count - a.count).slice(0, 10)
  const trendData = documents.map((d) => ({ name: d.document_name, score: d.score }))

  if (total === 0) {
    return (
      <FlatCard>
        <p className="text-[13px] text-muted py-6">Upload documents to see analytics.</p>
      </FlatCard>
    )
  }

  return (
    <div className="space-y-4">
      {executiveSummary && (
        <FlatCard>
          <p className="text-[11px] uppercase tracking-[0.14em] text-muted mb-2">Executive summary</p>
          <p className="text-[14px] leading-6 text-ink">{executiveSummary}</p>
        </FlatCard>
      )}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <MetricCard label="Documents audited" value={audited} />
        <MetricCard label="Passed" value={passed} color="teal" />
        <MetricCard label="Incomplete" value={incomplete} color="coral" />
        <MetricCard label="Average score" value={`${avg.toFixed(1)}%`} color="teal" />
        <MetricCard label="High risk" value={highRisk} color="coral" />
        <MetricCard label="Review required" value={reviewRequired} color="coral" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <FlatCard>
          <h3 className="text-[16px] font-medium text-ink mb-4">Risk Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={riskData} dataKey="value" nameKey="name" outerRadius={80} label>
                {riskData.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </FlatCard>

        <FlatCard>
          <h3 className="text-[16px] font-medium text-ink mb-4">Top Violations</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={violationData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="rule_id" tick={{ fontSize: 10 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#993C1D" />
            </BarChart>
          </ResponsiveContainer>
        </FlatCard>

        <FlatCard>
          <h3 className="text-[16px] font-medium text-ink mb-4">Document Scores</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Line type="monotone" dataKey="score" stroke="#0F6E56" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </FlatCard>
      </div>

      <FlatCard>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[16px] font-medium text-ink">Workspace documents</h3>
          <span className="text-[12px] text-muted">{violations} total findings</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12.5px]">
            <thead className="text-[10px] uppercase tracking-[0.12em] text-muted border-b border-border">
              <tr><th className="py-2 pr-4">Document</th><th className="py-2 pr-4">Status</th><th className="py-2 pr-4">Score</th><th className="py-2 pr-4">Risk</th><th className="py-2">Findings</th></tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.document_id} className="border-b border-border/50 last:border-0">
                  <td className="py-3 pr-4"><button onClick={() => onOpenDocument?.(doc.document_id)} className="text-ink font-medium hover:text-teal-600 cursor-pointer text-left">{doc.document_name}</button></td>
                  <td className="py-3 pr-4 text-muted">{doc.document_status}</td>
                  <td className="py-3 pr-4 font-mono text-ink">{doc.score === null ? 'Not audited' : `${doc.score.toFixed(1)}%`}</td>
                  <td className="py-3 pr-4 text-muted">{doc.risk_level}</td>
                  <td className="py-3 text-muted">{doc.failed_rules.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </FlatCard>
    </div>
  )
}
