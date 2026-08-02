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
}

export function DashboardSection({ documents }: DashboardSectionProps) {
  const total = documents.length
  const passed = documents.filter((d) => d.passed).length
  const avg = total ? documents.reduce((s, d) => s + d.score, 0) / total : 0
  const violations = documents.reduce((s, d) => s + d.failed_rules.length, 0)
  const highRisk = documents.filter((d) => d.risk_level === 'High Risk').length

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
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MetricCard label="Documents audited" value={total} />
        <MetricCard label="Compliance rate" value={`${total ? ((passed / total) * 100).toFixed(0) : 0}%`} color="teal" />
        <MetricCard label="Average score" value={`${avg.toFixed(1)}%`} color="teal" />
        <MetricCard label="Violations" value={violations} color="coral" />
        <MetricCard label="High risk" value={highRisk} color="coral" />
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
    </div>
  )
}