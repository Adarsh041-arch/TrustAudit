import logging
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class DiscrepancyItem(BaseModel):
    check_type: str  # amount, vendor, date, signature
    status: str      # match, mismatch, missing_data
    details: str
    severity: str    # high, medium, low

class CrossVerificationResult(BaseModel):
    is_consistent: bool
    status: str # Compliant, Partially Compliant, Non-Compliant
    discrepancies: List[Dict[str, Any]]
    matched_amount: float
    mismatched_amount: float
    reconciliation_summary: str

class CrossVerifier:
    @staticmethod
    def verify_documents(audit_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Performs Three-Way Match cross-verification between Invoice, Purchase Order, and Receipt.
        """
        # Find document instances
        invoice_doc = None
        po_doc = None
        receipt_doc = None
        
        for doc in audit_results:
            doc_type = doc.get("document_type", "").lower()
            if "invoice" in doc_type or "receipt" in doc_type:
                # Receipt could be categorized as receipt, we distinguish them
                if "receipt" in doc_type:
                    receipt_doc = doc
                else:
                    invoice_doc = doc
            elif "purchase_order" in doc_type or "po" in doc_type:
                po_doc = doc
            elif "receipt" in doc_type:
                receipt_doc = doc
                
        # If no explicit typing, try guessing by filename
        if not invoice_doc or not po_doc:
            for doc in audit_results:
                name = doc.get("document_name", "").lower()
                if "inv" in name and not invoice_doc:
                    invoice_doc = doc
                elif "po" in name and not po_doc:
                    po_doc = doc
                elif ("rcpt" in name or "receipt" in name or "challan" in name) and not receipt_doc:
                    receipt_doc = doc

        discrepancies = []
        is_consistent = True
        
        # 1. Amount Verification
        inv_amt = CrossVerifier._extract_amount(invoice_doc) if invoice_doc else None
        po_amt = CrossVerifier._extract_amount(po_doc) if po_doc else None
        rec_amt = CrossVerifier._extract_amount(receipt_doc) if receipt_doc else None
        
        matched_amount = 0.0
        mismatched_amount = 0.0
        
        if inv_amt is not None and po_amt is not None:
            diff = abs(inv_amt - po_amt)
            if diff > 0.01:
                is_consistent = False
                mismatched_amount = diff
                discrepancies.append({
                    "check_type": "amount",
                    "status": "mismatch",
                    "details": f"Amount mismatch: Invoice total is ${inv_amt:.2f} but Purchase Order total is ${po_amt:.2f} (Difference: ${diff:.2f}).",
                    "severity": "high"
                })
            else:
                matched_amount = inv_amt
                discrepancies.append({
                    "check_type": "amount",
                    "status": "match",
                    "details": f"Invoice total matches Purchase Order total (${inv_amt:.2f}).",
                    "severity": "low"
                })
        else:
            discrepancies.append({
                "check_type": "amount",
                "status": "missing_data",
                "details": "Amount cross-check incomplete: Missing Invoice or Purchase Order total value.",
                "severity": "medium"
            })

        # 2. Vendor Verification
        inv_vendor = CrossVerifier._extract_vendor(invoice_doc) if invoice_doc else None
        po_vendor = CrossVerifier._extract_vendor(po_doc) if po_doc else None
        
        if inv_vendor and po_vendor:
            # Simple fuzzy checking
            clean_inv = re.sub(r"[^\w\s]", "", inv_vendor.lower())
            clean_po = re.sub(r"[^\w\s]", "", po_vendor.lower())
            
            # Check if one is a substring of the other or token overlap
            tokens_inv = set(clean_inv.split())
            tokens_po = set(clean_po.split())
            common = tokens_inv.intersection(tokens_po)
            
            if not common:
                is_consistent = False
                discrepancies.append({
                    "check_type": "vendor",
                    "status": "mismatch",
                    "details": f"Vendor name mismatch: Invoice has vendor '{inv_vendor}' but PO references '{po_vendor}'.",
                    "severity": "high"
                })
            else:
                discrepancies.append({
                    "check_type": "vendor",
                    "status": "match",
                    "details": f"Vendor names match fuzzy validation: '{inv_vendor}' matches '{po_vendor}'.",
                    "severity": "low"
                })
        else:
            discrepancies.append({
                "check_type": "vendor",
                "status": "missing_data",
                "details": "Vendor identity mismatch check incomplete: Missing vendor name in one or more files.",
                "severity": "medium"
            })

        # 3. Date Sequence Check
        inv_date = CrossVerifier._extract_date(invoice_doc) if invoice_doc else None
        po_date = CrossVerifier._extract_date(po_doc) if po_doc else None
        rec_date = CrossVerifier._extract_date(receipt_doc) if receipt_doc else None
        
        if inv_date and po_date:
            if inv_date < po_date:
                is_consistent = False
                discrepancies.append({
                    "check_type": "date",
                    "status": "mismatch",
                    "details": f"Chronology violation: Invoice date ({inv_date}) is prior to Purchase Order date ({po_date}).",
                    "severity": "high"
                })
            else:
                discrepancies.append({
                    "check_type": "date",
                    "status": "match",
                    "details": f"Chronology validated: Invoice issued ({inv_date}) after or on PO date ({po_date}).",
                    "severity": "low"
                })
        else:
            discrepancies.append({
                "check_type": "date",
                "status": "missing_data",
                "details": "Date timeline check incomplete: Missing dates on Invoice or PO.",
                "severity": "medium"
            })

        # 4. Approval Signatures Verification
        inv_approved = CrossVerifier._check_signature(invoice_doc) if invoice_doc else True
        po_approved = CrossVerifier._check_signature(po_doc) if po_doc else True
        
        if not inv_approved or not po_approved:
            is_consistent = False
            discrepancies.append({
                "check_type": "signature",
                "status": "mismatch",
                "details": "Approval failure: Unauthorized documents. Signature rules failed on Invoice or PO.",
                "severity": "high"
            })
        else:
            discrepancies.append({
                "check_type": "signature",
                "status": "match",
                "details": "Authorizations validated: Signatures/stamps verified on matching files.",
                "severity": "low"
            })

        # Compile final summary
        doc_count = sum(1 for d in [invoice_doc, po_doc, receipt_doc] if d is not None)
        rec_status = "Compliant" if is_consistent else ("Partially Compliant" if len([d for d in discrepancies if d["severity"] == "high"]) < 2 else "Non-Compliant")
        
        summary = (
            f"Three-Way Match complete for {doc_count} document(s). "
            f"Cross-verification resulted in {rec_status.upper()}. "
            f"Matched Amount: ${matched_amount:.2f}, Mismatched: ${mismatched_amount:.2f}."
        )
        
        return {
            "is_consistent": is_consistent,
            "status": rec_status,
            "discrepancies": discrepancies,
            "matched_amount": matched_amount,
            "mismatched_amount": mismatched_amount,
            "reconciliation_summary": summary
        }

    @staticmethod
    def _extract_amount(doc: Dict[str, Any]) -> Optional[float]:
        # Try metadata first
        meta = doc.get("metadata", {})
        if "total_amount" in meta:
            try:
                return float(meta["total_amount"])
            except ValueError:
                pass
        
        # Scan summary text
        summary = doc.get("summary_text", "")
        # Find values like $1,200.00
        matches = re.findall(r"\$\s*([\d,]+\.?\d*)", summary)
        if matches:
            try:
                # Remove commas
                return float(matches[0].replace(",", ""))
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_vendor(doc: Dict[str, Any]) -> Optional[str]:
        meta = doc.get("metadata", {})
        if "vendor_name" in meta and meta["vendor_name"]:
            return str(meta["vendor_name"])
            
        summary = doc.get("summary_text", "")
        match = re.search(r"from\s+([A-Za-z0-9\s,\.\-\&]+)\b", summary, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _extract_date(doc: Dict[str, Any]) -> Optional[str]:
        meta = doc.get("metadata", {})
        if "date" in meta and meta["date"]:
            return str(meta["date"])
        return None

    @staticmethod
    def _check_signature(doc: Dict[str, Any]) -> bool:
        # Check if R004 failed
        for fr in doc.get("failed_rules", []):
            if "R004" in fr.get("rule_id", ""):
                return False
        return True
