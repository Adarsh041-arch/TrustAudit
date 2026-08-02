import React from 'react'
import { FlatCard } from '../components/FlatCard'

interface ThreeWayMatchGraphProps {
  documents: any[]
  findings: any[]
}

export const ThreeWayMatchGraph: React.FC<ThreeWayMatchGraphProps> = ({ documents, findings }) => {
  const overbillingFindings = findings.filter(f => f.check_id === 'CHK-XDOC-CUMUL-001')
  const qtyMismatchFindings = findings.filter(f => f.check_id === 'CHK-XDOC-QTY-001')
  const priceMismatchFindings = findings.filter(f => f.check_id === 'CHK-XDOC-PRICE-001')

  return (
    <div className="space-y-6">
      <FlatCard>
        <h3 className="text-[18px] font-medium text-ink flex items-center gap-2 mb-2">
          <span className="w-2.5 h-2.5 rounded-full bg-teal-600"></span>
          Three-Way Match Cluster Topology (PO ↔ DC ↔ Invoice)
        </h3>
        
        <p className="text-[13px] text-muted mb-6">
          Documents are linked into transaction clusters via explicit PO citations, vendor/amount/date-window correlation, and fuzzy line item overlap.
        </p>

        {/* Visual Link Nodes */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
          <div className="p-4 rounded-xl bg-surface-1 border-[0.5px] border-border text-center">
            <span className="text-[13px] font-medium uppercase tracking-wider text-muted">Purchase Order (PO)</span>
            <div className="mt-1 text-[24px] font-medium text-ink">
              {documents.filter(d => d.doc_type === 'purchase_order').length}
            </div>
            <p className="text-[13px] text-muted mt-1">Pre-authorized spending baseline</p>
          </div>

          <div className="p-4 rounded-xl bg-surface-1 border-[0.5px] border-border text-center">
            <span className="text-[13px] font-medium uppercase tracking-wider text-muted">Delivery Challan (DC / GRN)</span>
            <div className="mt-1 text-[24px] font-medium text-ink">
              {documents.filter(d => d.doc_type === 'delivery_challan' || d.doc_type === 'goods_receipt_note').length}
            </div>
            <p className="text-[13px] text-muted mt-1">Physical goods received proof</p>
          </div>

          <div className="p-4 rounded-xl bg-surface-1 border-[0.5px] border-border text-center">
            <span className="text-[13px] font-medium uppercase tracking-wider text-muted">Invoice (INV)</span>
            <div className="mt-1 text-[24px] font-medium text-ink">
              {documents.filter(d => d.doc_type === 'invoice').length}
            </div>
            <p className="text-[13px] text-muted mt-1">Payment claim billed by vendor</p>
          </div>
        </div>

        {/* Fraud & Discrepancy Alerts */}
        <div className="space-y-3">
          {overbillingFindings.length > 0 && (
            <div className="p-4 rounded-xl bg-coral-50 border-[0.5px] border-coral-600/30 text-coral-600 space-y-1">
              <div className="font-medium text-[14px] flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-coral-600 text-white">CRITICAL FRAUD ALERT</span>
                CHK-XDOC-CUMUL-001 Cumulative Over-Billing Detected
              </div>
              <p className="text-[13px]">
                {overbillingFindings[0].message}
              </p>
            </div>
          )}

          {qtyMismatchFindings.length > 0 && (
            <div className="p-4 rounded-xl bg-coral-50 border-[0.5px] border-coral-600/30 text-coral-600 space-y-1">
              <div className="font-medium text-[14px] flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-coral-600 text-white">QUANTITY MISMATCH</span>
                CHK-XDOC-QTY-001 Invoiced Quantity Exceeds Received Quantity
              </div>
              <p className="text-[13px]">
                {qtyMismatchFindings[0].message}
              </p>
            </div>
          )}

          {priceMismatchFindings.length > 0 && (
            <div className="p-4 rounded-xl bg-coral-50 border-[0.5px] border-coral-600/30 text-coral-600 space-y-1">
              <div className="font-medium text-[14px] flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-coral-600 text-white">PRICE VARIANCE</span>
                CHK-XDOC-PRICE-001 Invoiced Unit Price Exceeds PO Authorization
              </div>
              <p className="text-[13px]">
                {priceMismatchFindings[0].message}
              </p>
            </div>
          )}

          {findings.length === 0 && (
            <div className="p-4 rounded-xl bg-teal-50 border-[0.5px] border-teal-600/30 text-teal-600 text-[13px]">
              All cross-document line quantities, prices, and cumulative limits match authorization baselines cleanly.
            </div>
          )}
        </div>
      </FlatCard>
    </div>
  )
}
