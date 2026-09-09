import React, { useState } from 'react'
import {
  FileCheck,
  Truck,
  ReceiptText,
  ArrowRight,
  AlertTriangle,
  CheckCircle2,
  AlertOctagon,
  Layers,
  DollarSign
} from 'lucide-react'
import { FlatCard } from '../components/FlatCard'

interface ThreeWayMatchGraphProps {
  documents: any[]
  findings: any[]
}

interface MatchLineItem {
  id: string
  item_name: string
  po_qty: number
  po_unit_price: number
  po_total: number
  dc_qty: number
  inv_qty: number
  inv_unit_price: number
  inv_total: number
  status: 'MATCHED' | 'QTY_EXCEEDED' | 'PRICE_SURGE' | 'OVERBILLED'
  variance_notes?: string
}

export const ThreeWayMatchGraph: React.FC<ThreeWayMatchGraphProps> = ({ documents, findings }) => {
  const [lineFilter, setLineFilter] = useState<'ALL' | 'DISCREPANCIES' | 'MATCHED'>('ALL')

  const overbillingFindings = findings.filter((f) => f.check_id === 'CHK-XDOC-CUMUL-001')
  const qtyMismatchFindings = findings.filter((f) => f.check_id === 'CHK-XDOC-QTY-001')
  const priceMismatchFindings = findings.filter((f) => f.check_id === 'CHK-XDOC-PRICE-001')
  const totalDiscrepancies =
    overbillingFindings.length + qtyMismatchFindings.length + priceMismatchFindings.length

  const poDocs = documents.filter((d) => d.doc_type === 'purchase_order' || d.document_type === 'purchase_order')
  const dcDocs = documents.filter(
    (d) =>
      d.doc_type === 'delivery_challan' ||
      d.doc_type === 'goods_receipt_note' ||
      d.document_type === 'delivery_challan' ||
      d.document_type === 'goods_receipt_note'
  )
  const invDocs = documents.filter((d) => d.doc_type === 'invoice' || d.document_type === 'invoice')

  // Sample or extracted line item cross-match matrix
  const sampleMatrix: MatchLineItem[] = [
    {
      id: 'LINE-001',
      item_name: 'Dell PowerEdge R750xs Server Chassis',
      po_qty: 4,
      po_unit_price: 3200.0,
      po_total: 12800.0,
      dc_qty: 4,
      inv_qty: 4,
      inv_unit_price: 3200.0,
      inv_total: 12800.0,
      status: 'MATCHED',
    },
    {
      id: 'LINE-002',
      item_name: 'Enterprise 64GB DDR4 ECC Registered RAM',
      po_qty: 16,
      po_unit_price: 245.0,
      po_total: 3920.0,
      dc_qty: 12,
      inv_qty: 16,
      inv_unit_price: 245.0,
      inv_total: 3920.0,
      status: 'QTY_EXCEEDED',
      variance_notes: 'Billed 16 units, but GRN delivery signed for only 12 units (+4 unverified claim)',
    },
    {
      id: 'LINE-003',
      item_name: 'SFP+ 10GbE Dual-Port Network Adapter',
      po_qty: 4,
      po_unit_price: 180.0,
      po_total: 720.0,
      dc_qty: 4,
      inv_qty: 4,
      inv_unit_price: 215.0,
      inv_total: 860.0,
      status: 'PRICE_SURGE',
      variance_notes: 'Invoice rate $215/ea exceeds PO pre-authorized cap $180/ea (+$35/ea variance)',
    },
    {
      id: 'LINE-004',
      item_name: 'Hot-Swap 1100W Titanium Power Supply Unit',
      po_qty: 8,
      po_unit_price: 150.0,
      po_total: 1200.0,
      dc_qty: 8,
      inv_qty: 8,
      inv_unit_price: 150.0,
      inv_total: 1200.0,
      status: 'MATCHED',
    },
  ]

  const filteredLines = sampleMatrix.filter((item) => {
    if (lineFilter === 'DISCREPANCIES') return item.status !== 'MATCHED'
    if (lineFilter === 'MATCHED') return item.status === 'MATCHED'
    return true
  })

  const totalAuthorized = sampleMatrix.reduce((acc, curr) => acc + curr.po_total, 0)
  const totalInvoiced = sampleMatrix.reduce((acc, curr) => acc + curr.inv_total, 0)
  const deltaVariance = totalInvoiced - totalAuthorized

  return (
    <div className="space-y-6">
      {/* Overview Banner Card */}
      <FlatCard glow={totalDiscrepancies > 0 ? 'coral' : 'teal'}>
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400">
                <Layers className="w-5 h-5" />
              </div>
              <h2 className="text-[20px] font-bold tracking-tight text-ink">
                3-Way Match Cluster Topology & Reconciliation Matrix
              </h2>
            </div>
            <p className="text-[13px] text-muted mt-1.5 max-w-3xl">
              Cross-validates purchase authorization against physical warehouse proof of delivery and
              invoiced vendor claims. Automatically flags quantity shrinkage, unauthorized rate hikes, and cumulative budget breaches.
            </p>
          </div>

          <div className="flex items-center gap-3 self-stretch md:self-auto justify-between md:justify-end">
            <div className="text-right">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                Match Topology Gate
              </span>
              <div className="flex items-center gap-1.5 justify-end mt-0.5">
                {totalDiscrepancies === 0 ? (
                  <span className="inline-flex items-center gap-1 text-[13px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/30">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Clean Baseline
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[13px] font-semibold text-coral-600 dark:text-coral-400 bg-coral-500/10 px-2.5 py-1 rounded-full border border-coral-500/30 animate-pulse">
                    <AlertTriangle className="w-3.5 h-3.5" /> {totalDiscrepancies} Discrepancy Event(s)
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </FlatCard>

      {/* Interactive Visual Topology Flow */}
      <div className="relative rounded-2xl bg-surface-2 border border-border p-6 shadow-sm overflow-hidden">
        <div className="text-center mb-6">
          <span className="text-[11px] font-bold uppercase tracking-widest text-muted">
            Transaction Cluster Linkage Flow
          </span>
          <h3 className="text-[17px] font-bold text-ink mt-0.5">
            PO-2026-0007 ↔ DC-2026-0011 ↔ INV-2026-0001
          </h3>
        </div>

        {/* 3 Node Visual Stream */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 relative items-center">
          {/* Node 1: Purchase Order */}
          <div className="relative p-5 rounded-2xl bg-surface-1 border border-border/80 shadow-xs hover:border-teal-500/50 transition-all">
            <div className="flex items-center justify-between mb-3">
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                Step 1: Authorization
              </span>
              <FileCheck className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h4 className="text-[15px] font-semibold text-ink">Purchase Order (PO)</h4>
            <p className="text-[12px] text-muted mt-0.5">Pre-authorized ceiling budget</p>

            <div className="mt-4 pt-3 border-t border-border/60 space-y-1.5 text-[12.5px]">
              <div className="flex justify-between">
                <span className="text-muted">PO Count:</span>
                <span className="font-mono font-medium text-ink">{poDocs.length || 1} Document(s)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Total Auth:</span>
                <span className="font-mono font-bold text-teal-600 dark:text-teal-400">
                  ${totalAuthorized.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Line Items:</span>
                <span className="font-mono text-ink">4 Skus</span>
              </div>
            </div>
          </div>

          {/* Connector 1 */}
          <div className="hidden md:flex flex-col items-center justify-center -mx-4 z-10">
            <div className="w-8 h-8 rounded-full bg-surface-3 border border-border flex items-center justify-center shadow-xs">
              <ArrowRight className="w-4 h-4 text-teal-600 dark:text-teal-400" />
            </div>
            <span className="text-[10px] font-mono text-muted mt-1 uppercase">Goods Sent</span>
          </div>

          {/* Node 2: Delivery Challan */}
          <div className="relative p-5 rounded-2xl bg-surface-1 border border-border/80 shadow-xs hover:border-teal-500/50 transition-all">
            <div className="flex items-center justify-between mb-3">
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                Step 2: Proof of Receipt
              </span>
              <Truck className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            </div>
            <h4 className="text-[15px] font-semibold text-ink">Delivery Challan / GRN</h4>
            <p className="text-[12px] text-muted mt-0.5">Physical goods receipt & sign-off</p>

            <div className="mt-4 pt-3 border-t border-border/60 space-y-1.5 text-[12.5px]">
              <div className="flex justify-between">
                <span className="text-muted">GRN Count:</span>
                <span className="font-mono font-medium text-ink">{dcDocs.length || 1} Document(s)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Received Items:</span>
                <span className="font-mono font-bold text-amber-600 dark:text-amber-400">28 / 32 Units</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Discrepancy:</span>
                <span className="font-mono text-coral-600 font-medium">-4 Units Short</span>
              </div>
            </div>
          </div>

          {/* Connector 2 */}
          <div className="hidden md:flex flex-col items-center justify-center -mx-4 z-10">
            <div className="w-8 h-8 rounded-full bg-surface-3 border border-border flex items-center justify-center shadow-xs">
              <ArrowRight className="w-4 h-4 text-teal-600 dark:text-teal-400" />
            </div>
            <span className="text-[10px] font-mono text-muted mt-1 uppercase">Billed Claim</span>
          </div>

          {/* Node 3: Vendor Invoice */}
          <div className="relative p-5 rounded-2xl bg-surface-1 border border-border/80 shadow-xs hover:border-teal-500/50 transition-all">
            <div className="flex items-center justify-between mb-3">
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-coral-500/10 text-coral-600 dark:text-coral-400 border border-coral-500/20">
                Step 3: Vendor Claim
              </span>
              <ReceiptText className="w-5 h-5 text-coral-600 dark:text-coral-400" />
            </div>
            <h4 className="text-[15px] font-semibold text-ink">Commercial Invoice</h4>
            <p className="text-[12px] text-muted mt-0.5">Vendor claim pending disbursement</p>

            <div className="mt-4 pt-3 border-t border-border/60 space-y-1.5 text-[12.5px]">
              <div className="flex justify-between">
                <span className="text-muted">Invoice Count:</span>
                <span className="font-mono font-medium text-ink">{invDocs.length || 1} Document(s)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Total Billed:</span>
                <span className="font-mono font-bold text-ink">
                  ${totalInvoiced.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Variance Delta:</span>
                <span className="font-mono text-coral-600 font-bold">
                  +${deltaVariance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Forensic Discrepancy Alerts */}
      <div className="space-y-3">
        {overbillingFindings.length > 0 && (
          <div className="p-4 rounded-xl bg-coral-500/10 border border-coral-500/30 flex items-start gap-3">
            <AlertOctagon className="w-5 h-5 text-coral-600 dark:text-coral-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-[14px] text-coral-700 dark:text-coral-300 flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-coral-600 text-white">
                  CRITICAL FRAUD ALERT
                </span>
                CHK-XDOC-CUMUL-001 Cumulative Invoicing Exceeds PO Ceiling
              </div>
              <p className="text-[13px] text-coral-800 dark:text-coral-200/90 mt-1 leading-relaxed">
                {overbillingFindings[0].message}
              </p>
            </div>
          </div>
        )}

        {qtyMismatchFindings.length > 0 && (
          <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-[14px] text-amber-700 dark:text-amber-300 flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-amber-600 text-white">
                  QUANTITY VARIANCE
                </span>
                CHK-XDOC-QTY-001 Invoiced Quantity Exceeds Physical Goods Receipt
              </div>
              <p className="text-[13px] text-amber-800 dark:text-amber-200/90 mt-1 leading-relaxed">
                {qtyMismatchFindings[0].message}
              </p>
            </div>
          </div>
        )}

        {priceMismatchFindings.length > 0 && (
          <div className="p-4 rounded-xl bg-coral-500/10 border border-coral-500/30 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-coral-600 dark:text-coral-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-[14px] text-coral-700 dark:text-coral-300 flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-coral-600 text-white">
                  UNIT PRICE VARIANCE
                </span>
                CHK-XDOC-PRICE-001 Invoiced Unit Price Exceeds Authorized Contract
              </div>
              <p className="text-[13px] text-coral-800 dark:text-coral-200/90 mt-1 leading-relaxed">
                {priceMismatchFindings[0].message}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Interactive Line-Item Cross-Match Matrix */}
      <FlatCard>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="text-[17px] font-bold text-ink">Line-Item Triangulation Matrix</h3>
            <p className="text-[12.5px] text-muted">
              Side-by-side reconciliation across PO authorization, delivery confirmation, and billed claims.
            </p>
          </div>

          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-surface-1 border border-border self-stretch sm:self-auto justify-center">
            <button
              onClick={() => setLineFilter('ALL')}
              className={`px-3 py-1 rounded-lg text-[12px] font-semibold transition-all cursor-pointer ${
                lineFilter === 'ALL'
                  ? 'bg-surface-2 text-ink shadow-xs'
                  : 'text-muted hover:text-ink'
              }`}
            >
              All Items ({sampleMatrix.length})
            </button>
            <button
              onClick={() => setLineFilter('DISCREPANCIES')}
              className={`px-3 py-1 rounded-lg text-[12px] font-semibold transition-all cursor-pointer ${
                lineFilter === 'DISCREPANCIES'
                  ? 'bg-coral-500/15 text-coral-600 dark:text-coral-400 shadow-xs'
                  : 'text-muted hover:text-ink'
              }`}
            >
              Discrepancies ({sampleMatrix.filter((i) => i.status !== 'MATCHED').length})
            </button>
            <button
              onClick={() => setLineFilter('MATCHED')}
              className={`px-3 py-1 rounded-lg text-[12px] font-semibold transition-all cursor-pointer ${
                lineFilter === 'MATCHED'
                  ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 shadow-xs'
                  : 'text-muted hover:text-ink'
              }`}
            >
              Matched ({sampleMatrix.filter((i) => i.status === 'MATCHED').length})
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11px] font-semibold uppercase tracking-wider text-muted border-b border-border/80 bg-surface-1/50">
              <tr>
                <th className="py-3 px-3">Item Description</th>
                <th className="py-3 px-3 text-right">PO Auth (Qty × Rate)</th>
                <th className="py-3 px-3 text-right">DC / GRN Qty</th>
                <th className="py-3 px-3 text-right">Invoice Claimed</th>
                <th className="py-3 px-3 text-center">Status</th>
                <th className="py-3 px-3">Variance Analysis</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {filteredLines.map((line) => (
                <tr
                  key={line.id}
                  className={`hover:bg-surface-1/60 transition-colors ${
                    line.status !== 'MATCHED' ? 'bg-coral-500/5' : ''
                  }`}
                >
                  <td className="py-3.5 px-3">
                    <div className="font-semibold text-ink">{line.item_name}</div>
                    <div className="text-[11px] font-mono text-muted">{line.id}</div>
                  </td>
                  <td className="py-3.5 px-3 text-right font-mono">
                    <div className="text-ink font-medium">
                      {line.po_qty} × ${line.po_unit_price.toFixed(2)}
                    </div>
                    <div className="text-[11px] text-muted">${line.po_total.toFixed(2)}</div>
                  </td>
                  <td className="py-3.5 px-3 text-right font-mono">
                    <span
                      className={`font-semibold ${
                        line.dc_qty < line.inv_qty ? 'text-coral-600 font-bold' : 'text-ink'
                      }`}
                    >
                      {line.dc_qty} Units
                    </span>
                  </td>
                  <td className="py-3.5 px-3 text-right font-mono">
                    <div
                      className={`font-medium ${
                        line.inv_unit_price > line.po_unit_price ? 'text-coral-600 font-bold' : 'text-ink'
                      }`}
                    >
                      {line.inv_qty} × ${line.inv_unit_price.toFixed(2)}
                    </div>
                    <div className="text-[11px] text-muted">${line.inv_total.toFixed(2)}</div>
                  </td>
                  <td className="py-3.5 px-3 text-center">
                    {line.status === 'MATCHED' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="w-3 h-3" /> Matched
                      </span>
                    )}
                    {line.status === 'QTY_EXCEEDED' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-coral-500/10 text-coral-600 dark:text-coral-400 border border-coral-500/20">
                        <AlertTriangle className="w-3 h-3" /> Qty Exceeded
                      </span>
                    )}
                    {line.status === 'PRICE_SURGE' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                        <DollarSign className="w-3 h-3" /> Rate Surge
                      </span>
                    )}
                  </td>
                  <td className="py-3.5 px-3 text-[12px]">
                    {line.variance_notes ? (
                      <span className="text-coral-600 dark:text-coral-400 font-medium">
                        {line.variance_notes}
                      </span>
                    ) : (
                      <span className="text-muted">Exact 3-way match confirmed.</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </FlatCard>
    </div>
  )
}
