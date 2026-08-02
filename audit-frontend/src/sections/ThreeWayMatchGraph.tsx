import React from 'react'

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
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur-md">
        <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2 mb-4">
          <span className="w-3 h-3 rounded-full bg-cyan-400"></span>
          Three-Way Match Cluster Topology (PO ↔ DC ↔ Invoice)

        </h3>
        
        <p className="text-sm text-slate-400 mb-6">
          Documents are linked into transaction clusters via explicit PO citations, vendor/amount/date-window correlation, and fuzzy line item overlap.
        </p>

        {/* Visual Link Nodes */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="p-4 rounded-lg bg-blue-950/30 border border-blue-800/40 text-center">
            <span className="text-xs font-semibold uppercase tracking-wider text-blue-400">Purchase Order (PO)</span>
            <div className="mt-2 text-xl font-bold text-slate-200">
              {documents.filter(d => d.doc_type === 'purchase_order').length} Document(s)
            </div>
            <p className="text-xs text-slate-400 mt-1">Pre-authorized spending baseline</p>
          </div>

          <div className="p-4 rounded-lg bg-amber-950/30 border border-amber-800/40 text-center">
            <span className="text-xs font-semibold uppercase tracking-wider text-amber-400">Delivery Challan (DC / GRN)</span>
            <div className="mt-2 text-xl font-bold text-slate-200">
              {documents.filter(d => d.doc_type === 'delivery_challan' || d.doc_type === 'goods_receipt_note').length} Document(s)
            </div>
            <p className="text-xs text-slate-400 mt-1">Physical goods received proof</p>
          </div>

          <div className="p-4 rounded-lg bg-emerald-950/30 border border-emerald-800/40 text-center">
            <span className="text-xs font-semibold uppercase tracking-wider text-emerald-400">Invoice (INV)</span>
            <div className="mt-2 text-xl font-bold text-slate-200">
              {documents.filter(d => d.doc_type === 'invoice').length} Document(s)
            </div>
            <p className="text-xs text-slate-400 mt-1">Payment claim billed by vendor</p>
          </div>
        </div>

        {/* Fraud & Discrepancy Alerts */}
        <div className="space-y-3">
          {overbillingFindings.length > 0 && (
            <div className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300">
              <div className="font-bold flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-xs bg-rose-500/20 text-rose-200">CRITICAL FRAUD ALERT</span>
                CHK-XDOC-CUMUL-001 Cumulative Over-Billing Detected
              </div>
              <p className="text-xs text-rose-300/80 mt-1">
                {overbillingFindings[0].message}
              </p>
            </div>
          )}

          {qtyMismatchFindings.length > 0 && (
            <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300">
              <div className="font-bold flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-xs bg-amber-500/20 text-amber-200">QUANTITY MISMATCH</span>
                CHK-XDOC-QTY-001 Invoiced Quantity Exceeds Received Quantity
              </div>
              <p className="text-xs text-amber-300/80 mt-1">
                {qtyMismatchFindings[0].message}
              </p>
            </div>
          )}

          {priceMismatchFindings.length > 0 && (
            <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300">
              <div className="font-bold flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-xs bg-amber-500/20 text-amber-200">PRICE VARIANCE</span>
                CHK-XDOC-PRICE-001 Invoiced Unit Price Exceeds PO Authorization
              </div>
              <p className="text-xs text-amber-300/80 mt-1">
                {priceMismatchFindings[0].message}
              </p>
            </div>
          )}

          {findings.length === 0 && (
            <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm">
              All cross-document line quantities, prices, and cumulative limits match authorization baselines cleanly.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
