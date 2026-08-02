#!/usr/bin/env python3
"""Extended test document generator with CLI args and defect manifests.

Usage:
  python generate_test_bill.py --doc-type invoice --defects line_item_error,gst_rate_error --output-dir sample_docs/
  python generate_test_bill.py --doc-type purchase_order --output-dir sample_docs/
  python generate_test_bill.py --doc-type delivery_challan
  python generate_test_bill.py --doc-type goods_receipt_note
  python generate_test_bill.py --list-defects
"""

import argparse
import hashlib
import os
import sys
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fpdf import FPDF


# ─── Defect registry ──────────────────────────────────────────────────────────

DEFECT_REGISTRY: dict[str, dict] = {
    "line_item_error": {
        "description": "One line item has incorrect total (qty × rate mismatch)",
        "applies_to": ["invoice", "purchase_order"],
    },
    "subtotal_error": {
        "description": "Stated subtotal ≠ sum of line items",
        "applies_to": ["invoice", "purchase_order", "goods_receipt_note"],
    },
    "gst_rate_error": {
        "description": "Wrong GST rate applied to an HSN code",
        "applies_to": ["invoice"],
    },
    "gst_calc_error": {
        "description": "CGST/SGST arithmetic incorrect",
        "applies_to": ["invoice"],
    },
    "grand_total_error": {
        "description": "Grand total ≠ subtotal + taxes",
        "applies_to": ["invoice", "purchase_order"],
    },
    "words_mismatch": {
        "description": "Amount in words does not match grand total",
        "applies_to": ["invoice"],
    },
    "missing_po_ref": {
        "description": "Invoice lacks PO reference number",
        "applies_to": ["invoice"],
    },
    "date_anomaly": {
        "description": "Invoice date is after due date or delivery date is after GRN date",
        "applies_to": ["invoice", "purchase_order", "delivery_challan", "goods_receipt_note"],
    },
    "duplicate_line": {
        "description": "Same item appears twice with same quantity",
        "applies_to": ["invoice", "purchase_order", "delivery_challan"],
    },
    "quantity_mismatch": {
        "description": "Invoiced qty > PO qty",
        "applies_to": ["invoice", "goods_receipt_note"],
    },
    "missing_mandatory": {
        "description": "Missing mandatory field (vendor name, address, GSTIN, date)",
        "applies_to": ["invoice", "purchase_order", "delivery_challan", "goods_receipt_note"],
    },
    "negative_amount": {
        "description": "Credit note style negative line item without annotation",
        "applies_to": ["invoice"],
    },
}


@dataclass
class DefectManifest:
    document_id: str
    doc_type: str
    source: str
    description: str
    expected_findings: list[dict] = field(default_factory=list)


# ─── Base PDF ─────────────────────────────────────────────────────────────────

class AuditDocPDF(FPDF):
    COLORS = {
        "primary": (25, 60, 120),
        "text": (50, 50, 50),
        "header_bg": (230, 240, 255),
        "table_header_bg": (25, 60, 120),
        "table_header_text": (255, 255, 255),
        "alt_row": (240, 245, 255),
    }

    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(*self.COLORS["header_bg"])
        self.set_text_color(*self.COLORS["primary"])
        self.cell(0, 7, f"  {title}", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.ln(2)

    def info_row(self, label: str, value: str, w1: int = 40, w2: int = 0):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*self.COLORS["primary"])
        self.cell(w1, 6, label)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*self.COLORS["text"])
        self.cell(w2 if w2 else 80, 6, value, new_x="LMARGIN", new_y="NEXT")

    def horizontal_rule(self):
        self.set_draw_color(*self.COLORS["primary"])
        self.set_line_width(0.5)
        y = self.get_y()
        self.line(10, y, 200, y)
        self.ln(4)

    def table_header(self, col_widths: list[int], headers: list[str]):
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(*self.COLORS["table_header_bg"])
        self.set_text_color(*self.COLORS["table_header_text"])
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, border=1, align="C", fill=True)
        self.ln()

    def table_row(self, col_widths: list[int], values: list[str], align_center: bool = False):
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*self.COLORS["text"])
        for i, val in enumerate(values):
            align = "C" if (align_center or i > 0) else "L"
            self.cell(col_widths[i], 6, val, border=1, align=align)
        self.ln()


# ─── Invoice Generator ────────────────────────────────────────────────────────

def generate_invoice(pdf: AuditDocPDF, defects: list[str]) -> tuple[str, list[dict]]:
    doc_id = f"INV-2026-{datetime.now().strftime('%m%d')}_AutoGen"
    findings = []

    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Seller
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "TAX INVOICE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "NewTech Solutions Pvt Ltd", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, "42, Electronic City, Phase I", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Bangalore, Karnataka - 560100", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "GSTIN: 27AAGCN1234H1Z1", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.horizontal_rule()

    # Invoice meta
    invoice_date = datetime.now()
    due_date = invoice_date + timedelta(days=30)
    pdf.section_title("Invoice Details")
    pdf.info_row("Invoice No:", doc_id)
    pdf.info_row("Date:", invoice_date.strftime("%d %B %Y"))
    pdf.info_row("Due Date:", due_date.strftime("%d %B %Y"))
    has_po = "missing_po_ref" not in defects
    if has_po:
        pdf.info_row("PO Reference:", "PO-2026-0025")
    pdf.ln(2)

    # Buyer
    pdf.section_title("Bill To")
    has_mandatory = "missing_mandatory" in defects
    pdf.info_row("Name:", "" if has_mandatory else "BuildRight Contractors")
    pdf.info_row("Address:", "" if has_mandatory else "15, Industrial Area, Andheri East")
    pdf.info_row("", "" if has_mandatory else "Mumbai, Maharashtra - 400093")
    pdf.info_row("GSTIN:", "" if has_mandatory else "27AAAFB1234J1Z2")
    pdf.ln(3)
    pdf.horizontal_rule()

    # Line items
    pdf.section_title("Line Items")
    col_w = [8, 58, 22, 18, 22, 26, 36]
    headers = ["#", "Description", "HSN", "Qty", "Rate", "Amount", "Taxable Value"]
    pdf.table_header(col_w, headers)

    has_line_err = "line_item_error" in defects
    has_dup = "duplicate_line" in defects
    has_neg = "negative_amount" in defects

    items = [
        ("1", "Dell Inspiron Laptop", "8471", "2", "45,000.00", "90,000.00", "90,000.00"),
        ("2", "Wireless Mouse", "8471", "10", "800.00",
         "8,800.00" if has_line_err else "8,000.00",
         "8,800.00" if has_line_err else "8,000.00"),
        ("3", "HP LaserJet Printer", "8443", "1", "25,000.00", "25,000.00", "25,000.00"),
    ]

    if has_dup:
        items.append(("4", "Office Stationery Kit", "4820", "50", "200.00", "10,000.00", "10,000.00"))
        items.append(("5", "Office Stationery Kit", "4820", "50", "200.00", "10,000.00", "10,000.00"))
    else:
        items.append(("4", "Office Stationery Kit", "4820", "50", "200.00", "10,000.00", "10,000.00"))

    if has_neg:
        items.append(("5", "Credit Note - Discount", "9999", "1", "-5,000.00", "-5,000.00", "-5,000.00"))

    for row in items:
        pdf.table_row(col_w, row)

    # Taxable total
    correct_taxable = 90000 + 8000 + 25000 + 10000
    if has_line_err:
        stated_taxable = 90000 + 8800 + 25000 + 10000
    else:
        stated_taxable = correct_taxable
    if has_dup:
        stated_taxable += 10000
    if has_neg:
        stated_taxable -= 5000

    has_subtot_err = "subtotal_error" in defects
    display_taxable = str(stated_taxable - 500) if has_subtot_err else str(stated_taxable)

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*pdf.COLORS["alt_row"])
    pdf.cell(col_w[0] + col_w[1] + col_w[2] + col_w[3] + col_w[4], 7, "  Total Taxable Value", border=1, align="L", fill=True)
    pdf.cell(col_w[5], 7, "", border=1, fill=True)
    pdf.cell(col_w[6], 7, f"{int(display_taxable):,}.00", border=1, align="R", fill=True)
    pdf.ln()
    pdf.ln(5)

    if has_line_err:
        findings.append({
            "check_id": "CHK-ARITH-LINE-001",
            "expected_status": "FAIL",
            "detail": "Line 2: 10 x 800.00 = 8,000.00, stated 8,800.00",
        })
    if has_subtot_err:
        findings.append({
            "check_id": "CHK-ARITH-SUBTOTAL-001",
            "expected_status": "FAIL",
            "detail": f"Line total sum {correct_taxable:,} != stated {display_taxable}",
        })

    # GST
    pdf.section_title("GST Computation")
    gst_col = [56, 26, 16, 26, 26, 30]
    gst_headers = ["Description", "Taxable Value", "Rate", "CGST (9%)", "SGST (9%)", "Total GST"]
    pdf.table_header(gst_col, gst_headers)

    has_gst_rate = "gst_rate_error" in defects
    stationery_rate = "18%" if has_gst_rate else "12%"
    stationery_cgst = "900.00" if has_gst_rate else "600.00"
    stationery_sgst = "900.00" if has_gst_rate else "600.00"
    stationery_total = "1,800.00" if has_gst_rate else "1,200.00"

    gst_rows = [
        ("Dell Inspiron Laptop", "90,000.00", "18%", "8,100.00", "8,100.00", "16,200.00"),
        ("Wireless Mouse", f"{8800 if has_line_err else 8000:,}.00", "18%",
         f"{792 if has_line_err else 720}.00", f"{792 if has_line_err else 720}.00",
         f"{1584 if has_line_err else 1440}.00"),
        ("HP LaserJet Printer", "25,000.00", "18%", "2,250.00", "2,250.00", "4,500.00"),
        ("Office Stationery Kit", "10,000.00", stationery_rate, stationery_cgst, stationery_sgst, stationery_total),
    ]

    for row in gst_rows:
        pdf.table_row(gst_col, row)

    correct_cgst = 8100 + (792 if has_line_err else 720) + 2250 + (900 if has_gst_rate else 600)
    correct_sgst = correct_cgst
    has_gst_calc = "gst_calc_error" in defects

    if has_gst_calc:
        stated_cgst = correct_cgst + 500
        stated_sgst = correct_sgst + 500
    else:
        stated_cgst = correct_cgst
        stated_sgst = correct_sgst

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*pdf.COLORS["alt_row"])
    pdf.cell(gst_col[0] + gst_col[1] + gst_col[2], 7, "  Total", border=1, align="L", fill=True)
    pdf.cell(gst_col[3], 7, f"{stated_cgst:,}.00", border=1, align="R", fill=True)
    pdf.cell(gst_col[4], 7, f"{stated_sgst:,}.00", border=1, align="R", fill=True)
    pdf.cell(gst_col[5], 7, f"{stated_cgst + stated_sgst:,}.00", border=1, align="R", fill=True)
    pdf.ln()
    pdf.ln(5)

    if has_gst_rate:
        findings.append({
            "check_id": "CHK-ARITH-TAX-001",
            "expected_status": "FAIL",
            "detail": "HSN 4820 (stationery) charged 18% GST, expected 12%",
        })
    if has_gst_calc:
        findings.append({
            "check_id": "CHK-ARITH-TAX-002",
            "expected_status": "FAIL",
            "detail": f"CGST stated {stated_cgst:,}, correct {correct_cgst:,}",
        })

    # Grand total
    pdf.section_title("Amount Summary")
    grand_total = int(display_taxable.replace(",", "")) + stated_cgst + stated_sgst
    correct_grand = correct_taxable + correct_cgst + correct_sgst

    has_grand_err = "grand_total_error" in defects
    display_grand = grand_total + 1000 if has_grand_err else grand_total

    summary = [
        ("Subtotal (Taxable Value)", f"{display_taxable}"),
        ("Add: CGST", f"{stated_cgst:,}.00"),
        ("Add: SGST", f"{stated_sgst:,}.00"),
        ("Grand Total", f"{display_grand:,}.00"),
    ]

    pdf.set_font("Helvetica", "", 9)
    for i, (label, val) in enumerate(summary):
        pdf.set_font("Helvetica", "B" if "Grand" in label else "", 9)
        pdf.cell(130, 7, f"  {label}", border="T" if i == 0 else "", align="L")
        pdf.cell(50, 7, f"Rs. {val}", border="T" if i == 0 else "", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(8)

    if has_grand_err:
        findings.append({
            "check_id": "CHK-ARITH-GRAND-001",
            "expected_status": "FAIL",
            "detail": f"Grand total {display_grand:,} != correct {correct_grand:,}",
        })

    # Amount in words
    has_words = "words_mismatch" in defects
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 6, "Amount in Words:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    words_text = "Rupees One Lakh Fifty-Seven Thousand Eight Hundred and Eighty-Four Only"
    pdf.multi_cell(0, 5, words_text)
    pdf.ln(5)

    if has_words:
        findings.append({
            "check_id": "CHK-FORMAT-WORDS-001",
            "expected_status": "FAIL",
            "detail": "Amount in words does not match grand total",
        })

    # Bank details
    pdf.section_title("Bank Details")
    pdf.info_row("Bank:", "Kotak Mahindra Bank")
    pdf.info_row("A/C No:", "1234567890")
    pdf.info_row("IFSC:", "KKBK0001234")
    pdf.ln(4)

    # Declaration
    pdf.section_title("Declaration")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.multi_cell(0, 5,
        "We declare that the information shown above is true and correct. "
        "This is a computer-generated invoice and does not require a physical signature."
    )
    pdf.ln(6)

    # Signatory
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 6, "for NewTech Solutions Pvt Ltd", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="R")

    return doc_id, findings


# ─── Purchase Order Generator ─────────────────────────────────────────────────

def generate_purchase_order(pdf: AuditDocPDF, defects: list[str]) -> tuple[str, list[dict]]:
    doc_id = f"PO-2026-{datetime.now().strftime('%m%d')}_AutoGen"
    findings = []

    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "PURCHASE ORDER", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("PO Details")
    pdf.info_row("PO No:", doc_id)
    pdf.info_row("Date:", datetime.now().strftime("%d %B %Y"))
    pdf.info_row("Vendor:", "NewTech Solutions Pvt Ltd")
    pdf.info_row("Payment Terms:", "Net 45")
    pdf.ln(2)
    pdf.horizontal_rule()

    has_mandatory = "missing_mandatory" in defects
    pdf.section_title("Vendor Information")
    pdf.info_row("Name:", "" if has_mandatory else "NewTech Solutions Pvt Ltd")
    pdf.info_row("Address:", "" if has_mandatory else "42, Electronic City, Phase I")
    pdf.info_row("", "" if has_mandatory else "Bangalore - 560100")
    pdf.info_row("GSTIN:", "" if has_mandatory else "27AAGCN1234H1Z1")
    pdf.ln(3)

    pdf.section_title("Line Items")
    col_w = [8, 58, 18, 22, 26, 36]
    headers = ["#", "Description", "Qty", "Rate", "Amount", "Delivery Date"]
    pdf.table_header(col_w, headers)

    has_line_err = "line_item_error" in defects
    has_dup = "duplicate_line" in defects
    delivery = (datetime.now() + timedelta(days=15)).strftime("%d-%b-%Y")

    items = [
        ("1", "Dell Inspiron Laptop", "2", "45,000.00", "90,000.00", delivery),
        ("2", "Wireless Mouse", "10", "800.00", "8,800.00" if has_line_err else "8,000.00", delivery),
        ("3", "HP LaserJet Printer", "1", "25,000.00", "25,000.00", delivery),
    ]

    if has_dup:
        items.append(("4", "Office Stationery Kit", "50", "200.00", "10,000.00", delivery))
        items.append(("5", "Office Stationery Kit", "50", "200.00", "10,000.00", delivery))
    else:
        items.append(("4", "Office Stationery Kit", "50", "200.00", "10,000.00", delivery))

    for row in items:
        pdf.table_row(col_w, row)

    po_total = sum(int(r[4].replace(",", "")) for r in items)
    has_subtot = "subtotal_error" in defects
    display_total = po_total + 1000 if has_subtot else po_total

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*pdf.COLORS["alt_row"])
    pdf.cell(col_w[0] + col_w[1] + col_w[2] + col_w[3], 7, "  Total PO Value", border=1, align="L", fill=True)
    pdf.cell(col_w[4], 7, f"{display_total:,}.00", border=1, align="R", fill=True)
    pdf.cell(col_w[5], 7, "", border=1, fill=True)
    pdf.ln()
    pdf.ln(5)

    pdf.section_title("Terms & Conditions")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*pdf.COLORS["text"])
    terms = [
        "Delivery must be completed within 15 days from PO date.",
        "100% payment within 45 days of delivery and invoice.",
        "All items must comply with applicable quality standards.",
        "This PO is subject to our standard terms and conditions.",
    ]
    for t in terms:
        pdf.cell(0, 5, f"  - {t}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.horizontal_rule()
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 6, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="R")

    if has_line_err:
        findings.append({
            "check_id": "CHK-ARITH-LINE-001",
            "expected_status": "FAIL",
            "detail": "PO Line 2: 10 x 800.00 = 8,000.00, stated 8,800.00",
        })
    if has_subtot:
        findings.append({
            "check_id": "CHK-ARITH-SUBTOTAL-001",
            "expected_status": "FAIL",
            "detail": f"PO total stated {display_total:,}, correct {po_total:,}",
        })

    return doc_id, findings


# ─── Delivery Challan Generator ───────────────────────────────────────────────

def generate_delivery_challan(pdf: AuditDocPDF, defects: list[str]) -> tuple[str, list[dict]]:
    doc_id = f"DC-2026-{datetime.now().strftime('%m%d')}_AutoGen"
    findings = []

    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "DELIVERY CHALLAN", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("Challan Details")
    has_mandatory = "missing_mandatory" in defects
    delivery_date = datetime.now() + timedelta(days=2)
    pdf.info_row("Challan No:", doc_id)
    pdf.info_row("Date:", delivery_date.strftime("%d %B %Y"))
    pdf.info_row("PO Reference:", "" if has_mandatory else "PO-2026-0025")
    pdf.info_row("Vehicle No:", "KA-01-AB-1234")
    pdf.ln(2)
    pdf.horizontal_rule()

    pdf.section_title("Dispatch From")
    pdf.info_row("Name:", "" if has_mandatory else "NewTech Solutions Pvt Ltd")
    pdf.info_row("Address:", "" if has_mandatory else "42, Electronic City, Phase I, Bangalore")
    pdf.ln(2)

    pdf.section_title("Deliver To")
    pdf.info_row("Name:", "" if has_mandatory else "BuildRight Contractors")
    pdf.info_row("Address:", "" if has_mandatory else "15, Industrial Area, Andheri East, Mumbai")
    pdf.ln(3)

    pdf.section_title("Items")
    col_w = [8, 62, 18, 22, 30, 30]
    headers = ["#", "Description", "Qty", "Unit", "Remarks", "PO Qty"]
    pdf.table_header(col_w, headers)

    has_dup = "duplicate_line" in defects
    has_qty = "quantity_mismatch" in defects
    has_date = "date_anomaly" in defects

    items = [
        ("1", "Dell Inspiron Laptop", "2", "Nos", "Good condition", "2"),
        ("2", "Wireless Mouse", "10", "Nos", "Sealed packs",
         "8" if has_qty else "10"),
        ("3", "HP LaserJet Printer", "1", "Nos", "Factory sealed", "1"),
    ]
    if has_dup:
        items.append(("4", "Office Stationery Kit", "50", "Nos", "Assorted", "50"))
        items.append(("5", "Office Stationery Kit", "50", "Nos", "Assorted", "50"))

    for row in items:
        pdf.table_row(col_w, row)

    if has_qty:
        findings.append({
            "check_id": "CHK-REF-QTY-001",
            "expected_status": "FAIL",
            "detail": "Delivered qty (10) > PO qty (8) for Wireless Mouse",
        })

    return doc_id, findings


# ─── Goods Receipt Note Generator ─────────────────────────────────────────────

def generate_goods_receipt_note(pdf: AuditDocPDF, defects: list[str]) -> tuple[str, list[dict]]:
    doc_id = f"GRN-2026-{datetime.now().strftime('%m%d')}_AutoGen"
    findings = []

    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "GOODS RECEIPT NOTE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("GRN Details")
    has_mandatory = "missing_mandatory" in defects
    receipt_date = datetime.now()
    pdf.info_row("GRN No:", doc_id)
    pdf.info_row("Date:", receipt_date.strftime("%d %B %Y"))
    pdf.info_row("PO Reference:", "" if has_mandatory else "PO-2026-0025")
    pdf.info_row("DC Reference:", "DC-2026-" + datetime.now().strftime('%m%d'))
    pdf.ln(2)
    pdf.horizontal_rule()

    pdf.section_title("Receiving Details")
    pdf.info_row("Received From:", "" if has_mandatory else "NewTech Solutions Pvt Ltd")
    pdf.info_row("Location:", "" if has_mandatory else "Warehouse A, Bhiwandi")
    pdf.ln(2)

    pdf.section_title("Received Items")
    col_w = [8, 58, 18, 18, 22, 30]
    headers = ["#", "Description", "DC Qty", "Received Qty", "Accepted", "Remarks"]
    pdf.table_header(col_w, headers)

    has_qty = "quantity_mismatch" in defects
    has_subtot = "subtotal_error" in defects
    items = [
        ("1", "Dell Inspiron Laptop", "2", "2", "2", "OK"),
        ("2", "Wireless Mouse", "10", "9" if has_qty else "10", "9" if has_qty else "10",
         "1 damaged" if has_qty else "OK"),
        ("3", "HP LaserJet Printer", "1", "1", "1", "OK"),
        ("4", "Office Stationery Kit", "50", "50", "50", "OK"),
    ]

    for row in items:
        pdf.table_row(col_w, row)

    if has_qty:
        findings.append({
            "check_id": "CHK-REF-QTY-002",
            "expected_status": "FAIL",
            "detail": "Received qty (9) < DC qty (10) for Wireless Mouse",
        })

    return doc_id, findings


# ─── Main ─────────────────────────────────────────────────────────────────────

GENERATORS = {
    "invoice": generate_invoice,
    "purchase_order": generate_purchase_order,
    "delivery_challan": generate_delivery_challan,
    "goods_receipt_note": generate_goods_receipt_note,
}


def write_manifest(manifest: DefectManifest, output_dir: Path):
    path = output_dir / f"{manifest.document_id}_manifest.yaml"
    with open(path, "w") as f:
        yaml.dump({
            "document_id": manifest.document_id,
            "doc_type": manifest.doc_type,
            "source": manifest.source,
            "description": manifest.description,
            "expected_findings": manifest.expected_findings,
        }, f, default_flow_style=False, sort_keys=False)
    return path


def list_defects():
    print("Available defects:\n")
    for def_id, info in sorted(DEFECT_REGISTRY.items()):
        applies = ", ".join(info["applies_to"])
        print(f"  {def_id}")
        print(f"    Description: {info['description']}")
        print(f"    Applies to:  {applies}\n")


def main():
    parser = argparse.ArgumentParser(description="Generate test audit documents with defects")
    parser.add_argument("--doc-type", choices=list(GENERATORS) + ["all"], default="invoice",
                        help="Document type to generate")
    parser.add_argument("--defects", default="",
                        help="Comma-separated defect IDs to inject")
    parser.add_argument("--output-dir", default="sample_docs",
                        help="Output directory for generated files")
    parser.add_argument("--list-defects", action="store_true",
                        help="List all available defects and exit")
    args = parser.parse_args()

    if args.list_defects:
        list_defects()
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    defects = [d.strip() for d in args.defects.split(",") if d.strip()]

    doc_types = list(GENERATORS) if args.doc_type == "all" else [args.doc_type]

    for doc_type in doc_types:
        generator = GENERATORS[doc_type]
        pdf = AuditDocPDF()
        doc_id, findings = generator(pdf, defects)

        pdf_path = output_dir / f"{doc_id}.pdf"
        pdf.output(str(pdf_path))

        manifest = DefectManifest(
            document_id=doc_id,
            doc_type=doc_type,
            source=str(pdf_path),
            description=f"Synthetic {doc_type} with defects: {defects or 'none'}",
            expected_findings=findings,
        )
        manifest_path = write_manifest(manifest, output_dir)

        print(f"Created: {pdf_path}")
        print(f"Manifest: {manifest_path}")
        print(f"  Defects: {defects or 'none'}")
        print(f"  Expected findings: {len(findings)}")


if __name__ == "__main__":
    main()
