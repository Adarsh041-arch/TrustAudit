#!/usr/bin/env python3
"""Generate 20 related test PDFs for a coherent audit session.

Creates 4 complete procurement cycles with cross-referencing documents:
- Purchase Orders referenced by Invoices, DCs, and GRNs
- Contracts linked to specific POs
- Letters referencing POs and Invoices
- Items and quantities match across related documents
"""
import random
import string
from datetime import date, timedelta
from pathlib import Path
from fpdf import FPDF

SEED = 42
BASE_DATE = date(2026, 6, 1)
OUTPUT_DIR = Path(__file__).resolve().parent / "TEST_DOCS_LARGE"


VENDORS = [
    ("NewTech Solutions Pvt Ltd", "Bangalore", "29", "29AABCN1234P1Z5"),
    ("RS Enterprises", "Mumbai", "27", "27AABCR5678Q1Z9"),
    ("Apex Industrial Supplies", "Pune", "27", "27AABCA9012R1Z3"),
    ("Bharat Steel Corporation", "Jamshedpur", "20", "20AABCB3456S1Z7"),
]

BUYERS = [
    ("BuildRight Contractors", "15, Industrial Area, Andheri East",
     "Mumbai, Maharashtra - 400093", "27AAAFB1234J1Z2"),
]


ITEMS_CATALOG = [
    ("Dell Inspiron Laptop", "8471", 45000),
    ("HP LaserJet Printer", "8443", 25000),
    ("Wireless Optical Mouse", "8471", 800),
    ("Mechanical Keyboard", "8471", 2500),
    ("Office Chair Executive", "9401", 8500),
    ("Steel Filing Cabinet", "9403", 12000),
    ("A4 Copier Paper Ream", "4802", 300),
    ("Whiteboard Marker Set", "9608", 200),
    ("LED Monitor 24 inch", "8528", 11000),
    ("Network Switch 24-port", "8517", 18000),
    ("UPS 1KVA", "8504", 6500),
    ("Ethernet Cable Drum", "8544", 4200),
    ("Projector Full HD", "8528", 52000),
    ("Document Scanner", "8471", 21000),
    ("External Hard Drive 2TB", "8523", 7500),
    ("Conference Table", "9403", 35000),
    ("Air Conditioner 1.5T", "8415", 38000),
    ("Water Dispenser", "8418", 9500),
    ("Paper Shredder", "8472", 13500),
    ("Biometric Attendance Unit", "8543", 15000),
]


class DocPDF(FPDF):
    COLORS = {
        "primary": (25, 60, 120),
        "text": (50, 50, 50),
        "header_bg": (230, 240, 255),
        "table_header_bg": (25, 60, 120),
        "table_header_text": (255, 255, 255),
        "alt_row": (240, 245, 255),
    }

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(*self.COLORS["header_bg"])
        self.set_text_color(*self.COLORS["primary"])
        self.cell(0, 7, f"  {title}", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.ln(2)

    def info_row(self, label, value, w1=40, w2=100):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*self.COLORS["primary"])
        self.cell(w1, 6, label)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*self.COLORS["text"])
        self.cell(w2, 6, value, new_x="LMARGIN", new_y="NEXT")

    def h_rule(self):
        self.set_draw_color(*self.COLORS["primary"])
        self.set_line_width(0.5)
        y = self.get_y()
        self.line(10, y, 200, y)
        self.ln(4)

    def tbl_header(self, widths, headers):
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(*self.COLORS["table_header_bg"])
        self.set_text_color(*self.COLORS["table_header_text"])
        for i, h in enumerate(headers):
            self.cell(widths[i], 7, h, border=1, align="C", fill=True)
        self.ln()

    def tbl_row(self, widths, values):
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*self.COLORS["text"])
        for i, val in enumerate(values):
            self.cell(widths[i], 6, val, border=1, align="C" if i > 0 else "L")
        self.ln()


def fmt(n):
    return f"{n:,}.00"


def make_ifsc(rng):
    return "".join(rng.choices(string.ascii_uppercase, k=4)) + "0" + "".join(rng.choices(string.digits, k=6))


# ============================================================
# PROCUREMENT CYCLE 1: NewTech Solutions
# ============================================================

def gen_cycle1(rng, doc_idx):
    """PO-42 -> DC-43 -> GRN-44 -> INV-45 -> SC-41, LTR-46"""
    vendor = VENDORS[0]  # NewTech Solutions
    buyer = BUYERS[0]
    items = [
        ("Dell Inspiron Laptop", "8471", 45000, 5),
        ("HP LaserJet Printer", "8443", 25000, 3),
        ("LED Monitor 24 inch", "8528", 11000, 10),
    ]

    docs = []
    idx = doc_idx

    # --- Contract SC-2026-0041 ---
    docs.append(gen_contract_for_cycle(rng, idx, vendor, buyer,
        contract_no=f"SC-2026-{idx:04d}",
        contract_date=BASE_DATE,
        items=items,
        payment_terms="Net 45 days",
        delivery_terms="FOB Bangalore",
        warranty="18 months",
    ))
    idx += 1

    # --- PO-2026-0042 ---
    po_no = f"PO-2026-{idx:04d}"
    po_date = BASE_DATE + timedelta(days=5)
    docs.append(gen_po_for_cycle(rng, idx, vendor, buyer, po_no, po_date, items))
    idx += 1

    # --- DC-2026-0043 ---
    dc_no = f"DC-2026-{idx:04d}"
    dc_date = po_date + timedelta(days=10)
    docs.append(gen_dc_for_cycle(rng, idx, vendor, dc_no, dc_date, po_no, items))
    idx += 1

    # --- GRN-2026-0044 ---
    grn_no = f"GRN-2026-{idx:04d}"
    grn_date = dc_date + timedelta(days=1)
    docs.append(gen_grn_for_cycle(rng, idx, vendor, grn_no, grn_date, po_no, dc_no, items))
    idx += 1

    # --- INV-2026-0045 ---
    inv_no = f"INV-2026-{idx:04d}"
    inv_date = grn_date + timedelta(days=2)
    docs.append(gen_inv_for_cycle(rng, idx, vendor, buyer, inv_no, inv_date, po_no, items))
    idx += 1

    # --- LTR-2026-0046 (Payment confirmation) ---
    ltr_no = f"LTR-2026-{idx:04d}"
    ltr_date = inv_date + timedelta(days=15)
    docs.append(gen_payment_letter(rng, idx, vendor, buyer, ltr_no, ltr_date, inv_no, po_no, items))
    idx += 1

    return docs, idx


# ============================================================
# PROCUREMENT CYCLE 2: RS Enterprises
# ============================================================

def gen_cycle2(rng, doc_idx):
    """PO-47 -> DC-48 -> GRN-49 -> INV-50 -> SC-51, LTR-52"""
    vendor = VENDORS[1]  # RS Enterprises
    buyer = BUYERS[0]
    items = [
        ("Office Chair Executive", "9401", 8500, 20),
        ("Conference Table", "9403", 35000, 2),
        ("Steel Filing Cabinet", "9403", 12000, 8),
    ]

    docs = []
    idx = doc_idx

    docs.append(gen_contract_for_cycle(rng, idx, vendor, buyer,
        contract_no=f"SC-2026-{idx:04d}",
        contract_date=BASE_DATE + timedelta(days=10),
        items=items,
        payment_terms="Net 30 days",
        delivery_terms="FOB Mumbai",
        warranty="12 months",
    ))
    idx += 1

    po_no = f"PO-2026-{idx:04d}"
    po_date = BASE_DATE + timedelta(days=15)
    docs.append(gen_po_for_cycle(rng, idx, vendor, buyer, po_no, po_date, items))
    idx += 1

    dc_no = f"DC-2026-{idx:04d}"
    dc_date = po_date + timedelta(days=7)
    docs.append(gen_dc_for_cycle(rng, idx, vendor, dc_no, dc_date, po_no, items))
    idx += 1

    grn_no = f"GRN-2026-{idx:04d}"
    grn_date = dc_date + timedelta(days=1)
    docs.append(gen_grn_for_cycle(rng, idx, vendor, grn_no, grn_date, po_no, dc_no, items))
    idx += 1

    inv_no = f"INV-2026-{idx:04d}"
    inv_date = grn_date + timedelta(days=3)
    docs.append(gen_inv_for_cycle(rng, idx, vendor, buyer, inv_no, inv_date, po_no, items))
    idx += 1

    ltr_no = f"LTR-2026-{idx:04d}"
    ltr_date = inv_date + timedelta(days=20)
    docs.append(gen_payment_letter(rng, idx, vendor, buyer, ltr_no, ltr_date, inv_no, po_no, items))
    idx += 1

    return docs, idx


# ============================================================
# PROCUREMENT CYCLE 3: Apex Industrial Supplies
# ============================================================

def gen_cycle3(rng, doc_idx):
    """PO-53 -> DC-54 -> GRN-55 -> INV-56 -> SC-57, LTR-58"""
    vendor = VENDORS[2]  # Apex Industrial Supplies
    buyer = BUYERS[0]
    items = [
        ("Network Switch 24-port", "8517", 18000, 6),
        ("Ethernet Cable Drum", "8544", 4200, 15),
        ("UPS 1KVA", "8504", 6500, 10),
    ]

    docs = []
    idx = doc_idx

    docs.append(gen_contract_for_cycle(rng, idx, vendor, buyer,
        contract_no=f"SC-2026-{idx:04d}",
        contract_date=BASE_DATE + timedelta(days=20),
        items=items,
        payment_terms="Net 60 days",
        delivery_terms="CIF Pune",
        warranty="24 months",
    ))
    idx += 1

    po_no = f"PO-2026-{idx:04d}"
    po_date = BASE_DATE + timedelta(days=25)
    docs.append(gen_po_for_cycle(rng, idx, vendor, buyer, po_no, po_date, items))
    idx += 1

    dc_no = f"DC-2026-{idx:04d}"
    dc_date = po_date + timedelta(days=12)
    docs.append(gen_dc_for_cycle(rng, idx, vendor, dc_no, dc_date, po_no, items))
    idx += 1

    grn_no = f"GRN-2026-{idx:04d}"
    grn_date = dc_date + timedelta(days=2)
    docs.append(gen_grn_for_cycle(rng, idx, vendor, grn_no, grn_date, po_no, dc_no, items))
    idx += 1

    inv_no = f"INV-2026-{idx:04d}"
    inv_date = grn_date + timedelta(days=1)
    docs.append(gen_inv_for_cycle(rng, idx, vendor, buyer, inv_no, inv_date, po_no, items))
    idx += 1

    ltr_no = f"LTR-2026-{idx:04d}"
    ltr_date = inv_date + timedelta(days=10)
    docs.append(gen_payment_letter(rng, idx, vendor, buyer, ltr_no, ltr_date, inv_no, po_no, items))
    idx += 1

    return docs, idx


# ============================================================
# PROCUREMENT CYCLE 4: Bharat Steel Corporation
# ============================================================

def gen_cycle4(rng, doc_idx):
    """PO-59 -> DC-60 -> GRN-61 -> INV-62"""
    vendor = VENDORS[3]  # Bharat Steel
    buyer = BUYERS[0]
    items = [
        ("Projector Full HD", "8528", 52000, 2),
        ("Document Scanner", "8471", 21000, 4),
        ("Paper Shredder", "8472", 13500, 3),
    ]

    docs = []
    idx = doc_idx

    po_no = f"PO-2026-{idx:04d}"
    po_date = BASE_DATE + timedelta(days=30)
    docs.append(gen_po_for_cycle(rng, idx, vendor, buyer, po_no, po_date, items))
    idx += 1

    dc_no = f"DC-2026-{idx:04d}"
    dc_date = po_date + timedelta(days=14)
    docs.append(gen_dc_for_cycle(rng, idx, vendor, dc_no, dc_date, po_no, items))
    idx += 1

    grn_no = f"GRN-2026-{idx:04d}"
    grn_date = dc_date + timedelta(days=1)
    docs.append(gen_grn_for_cycle(rng, idx, vendor, grn_no, grn_date, po_no, dc_no, items))
    idx += 1

    inv_no = f"INV-2026-{idx:04d}"
    inv_date = grn_date + timedelta(days=5)
    docs.append(gen_inv_for_cycle(rng, idx, vendor, buyer, inv_no, inv_date, po_no, items))
    idx += 1

    return docs, idx


# ============================================================
# Document generators for each type
# ============================================================

def gen_po_for_cycle(rng, idx, vendor, buyer, po_no, po_date, items):
    vname, vcity, vstate, vgstin = vendor
    delivery_date = po_date + timedelta(days=15)

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "PURCHASE ORDER", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("PO Details")
    pdf.info_row("PO No:", po_no)
    pdf.info_row("Date:", po_date.strftime("%d %B %Y"))
    pdf.info_row("Vendor:", vname)
    pdf.info_row("Payment Terms:", "Net 45")
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Buyer Information")
    pdf.info_row("Name:", buyer[0])
    pdf.info_row("Address:", buyer[1])
    pdf.info_row("GSTIN:", buyer[3])
    pdf.ln(2)

    pdf.section_title("Vendor Information")
    pdf.info_row("Name:", vname)
    pdf.info_row("Address:", f"{vcity}, India")
    pdf.info_row("GSTIN:", vgstin)
    pdf.ln(3)

    pdf.section_title("Line Items")
    col_w = [8, 58, 22, 18, 26, 30]
    pdf.tbl_header(col_w, ["#", "Description", "HSN", "Qty", "Rate", "Amount"])
    total = 0
    for i, (desc, hsn, rate, qty) in enumerate(items, 1):
        amt = qty * rate
        total += amt
        pdf.tbl_row(col_w, [str(i), desc, hsn, str(qty), fmt(rate), fmt(amt)])

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*pdf.COLORS["alt_row"])
    pdf.cell(sum(col_w[:5]), 7, "  Total Order Value", border=1, align="L", fill=True)
    pdf.cell(col_w[5], 7, fmt(total), border=1, align="R", fill=True)
    pdf.ln()
    pdf.ln(5)

    pdf.section_title("Terms")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, f"  Delivery by: {delivery_date.strftime('%d %B %Y')}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "  Delivery Address: 15, Industrial Area, Andheri East, Mumbai", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "  Payment Terms: Net 45 days from date of invoice", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "  Validity: 30 days from date of PO", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.h_rule()
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 6, f"for {buyer[0]}", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="R")

    return (po_no, bytes(pdf.output()))


def gen_dc_for_cycle(rng, idx, vendor, dc_no, dc_date, po_no, items):
    vname, vcity, _, _ = vendor
    vehicle_no = f"MH-{rng.randrange(10, 99)}-{rng.choice(string.ascii_uppercase)}{rng.choice(string.ascii_uppercase)}-{rng.randrange(1000, 9999)}"

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "DELIVERY CHALLAN", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("Challan Details")
    pdf.info_row("Challan No:", dc_no)
    pdf.info_row("Date:", dc_date.strftime("%d %B %Y"))
    pdf.info_row("PO Reference:", po_no)
    pdf.info_row("Vehicle No:", vehicle_no)
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Dispatch From")
    pdf.info_row("Name:", vname)
    pdf.info_row("Address:", f"{vcity}, India")
    pdf.ln(2)

    pdf.section_title("Deliver To")
    pdf.info_row("Name:", "BuildRight Contractors")
    pdf.info_row("Address:", "15, Industrial Area, Andheri East, Mumbai")
    pdf.ln(3)

    pdf.section_title("Items")
    col_w = [8, 58, 22, 18, 30]
    pdf.tbl_header(col_w, ["#", "Description", "HSN", "Qty", "Unit"])
    for i, (desc, hsn, _, qty) in enumerate(items, 1):
        pdf.tbl_row(col_w, [str(i), desc, hsn, str(qty), "Nos"])

    pdf.ln(4)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, f"  Terms: Ex-Goods delivered on PO {po_no}", new_x="LMARGIN", new_y="NEXT")

    return (dc_no, bytes(pdf.output()))


def gen_grn_for_cycle(rng, idx, vendor, grn_no, grn_date, po_no, dc_no, items):
    vname, vcity, _, _ = vendor

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "GOODS RECEIPT NOTE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("GRN Details")
    pdf.info_row("GRN No:", grn_no)
    pdf.info_row("Date:", grn_date.strftime("%d %B %Y"))
    pdf.info_row("PO Reference:", po_no)
    pdf.info_row("DC Reference:", dc_no)
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Receiving Details")
    pdf.info_row("Received From:", vname)
    pdf.info_row("Location:", "Warehouse, Mumbai")
    pdf.info_row("Received By:", "Store Manager")
    pdf.ln(2)

    pdf.section_title("Received Items")
    col_w = [8, 50, 18, 20, 22, 22, 22]
    pdf.tbl_header(col_w, ["#", "Description", "HSN", "DC Qty", "Received", "Accepted", "Remarks"])
    for i, (desc, hsn, _, qty) in enumerate(items, 1):
        pdf.tbl_row(col_w, [str(i), desc, hsn, str(qty), str(qty), str(qty), "OK"])

    pdf.ln(4)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, "  Condition of goods: Good", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"  All items verified against PO {po_no} and DC {dc_no}", new_x="LMARGIN", new_y="NEXT")

    return (grn_no, bytes(pdf.output()))


def gen_inv_for_cycle(rng, idx, vendor, buyer, inv_no, inv_date, po_no, items):
    vname, vcity, vstate, vgstin = vendor
    due_date = inv_date + timedelta(days=45)

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "TAX INVOICE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, vname, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, f"{vcity}, India", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"GSTIN: {vgstin}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.h_rule()

    pdf.section_title("Invoice Details")
    pdf.info_row("Invoice No:", inv_no)
    pdf.info_row("Date:", inv_date.strftime("%d %B %Y"))
    pdf.info_row("Due Date:", due_date.strftime("%d %B %Y"))
    pdf.info_row("PO Reference:", po_no)
    pdf.ln(2)

    pdf.section_title("Bill To")
    pdf.info_row("Name:", buyer[0])
    pdf.info_row("Address:", buyer[1])
    pdf.info_row("GSTIN:", buyer[3])
    pdf.ln(3)
    pdf.h_rule()

    pdf.section_title("Line Items")
    col_w = [8, 55, 22, 18, 24, 28, 28]
    pdf.tbl_header(col_w, ["#", "Description", "HSN", "Qty", "Rate", "Amount", "Taxable"])
    subtotal = 0
    for i, (desc, hsn, rate, qty) in enumerate(items, 1):
        total = qty * rate
        subtotal += total
        pdf.tbl_row(col_w, [str(i), desc, hsn, str(qty), fmt(rate), fmt(total), fmt(total)])

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*pdf.COLORS["alt_row"])
    pdf.cell(sum(col_w[:5]), 7, "  Total Taxable Value", border=1, align="L", fill=True)
    pdf.cell(col_w[5], 7, "", border=1, fill=True)
    pdf.cell(col_w[6], 7, fmt(subtotal), border=1, align="R", fill=True)
    pdf.ln()
    pdf.ln(5)

    cgst = subtotal * 9 // 100
    sgst = cgst
    grand_total = subtotal + cgst + sgst

    pdf.section_title("Amount Summary")
    for lbl, val in [("Subtotal (Taxable Value)", fmt(subtotal)), ("Add: CGST @ 9%", fmt(cgst)), ("Add: SGST @ 9%", fmt(sgst)), ("Grand Total", fmt(grand_total))]:
        pdf.set_font("Helvetica", "B" if "Grand" in lbl else "", 9)
        pdf.set_text_color(*pdf.COLORS["text"])
        pdf.cell(130, 7, f"  {lbl}", align="L")
        pdf.cell(50, 7, f"Rs. {val}", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(6)

    pdf.section_title("Bank Details")
    pdf.info_row("Bank:", "HDFC Bank")
    pdf.info_row("A/C No:", str(rng.randrange(10**9, 10**10)))
    pdf.info_row("IFSC:", make_ifsc(rng))
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 6, f"for {vname}", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="R")

    return (inv_no, bytes(pdf.output()))


def gen_contract_for_cycle(rng, idx, vendor, buyer, contract_no, contract_date, items,
                           payment_terms, delivery_terms, warranty):
    vname, vcity, vstate, vgstin = vendor

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "SALES CONTRACT", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("Contract Details")
    pdf.info_row("Contract No:", contract_no)
    pdf.info_row("Date:", contract_date.strftime("%d %B %Y"))
    pdf.info_row("Buyer:", buyer[0])
    pdf.info_row("Seller:", vname)
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Scope of Supply")
    col_w = [8, 55, 22, 18, 26, 30]
    pdf.tbl_header(col_w, ["#", "Description", "HSN", "Qty", "Rate", "Value"])
    total = 0
    for i, (desc, hsn, rate, qty) in enumerate(items, 1):
        val = qty * rate
        total += val
        pdf.tbl_row(col_w, [str(i), desc, hsn, str(qty), fmt(rate), fmt(val)])
    pdf.ln(3)

    pdf.section_title("Terms and Conditions")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    terms = [
        f"1. Total Contract Value: Rs. {fmt(total)} plus applicable taxes.",
        f"2. Payment Terms: {payment_terms}.",
        f"3. Delivery Terms: {delivery_terms}.",
        f"4. Warranty: {warranty} from date of delivery.",
        "5. This Agreement is entered into between the Seller and the Buyer.",
        "6. Any disputes shall be resolved under the jurisdiction of Mumbai courts.",
        "7. This contract is valid for 24 months from the date of signing.",
    ]
    for t in terms:
        pdf.cell(0, 5, f"  {t}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.h_rule()

    pdf.section_title("Signatures")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(90, 6, "________________________", align="L")
    pdf.cell(90, 6, "________________________", new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.cell(90, 5, f"For {vname}", align="L")
    pdf.cell(90, 5, f"For {buyer[0]}", new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.cell(90, 5, "Authorised Signatory", align="L")
    pdf.cell(90, 5, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="L")

    return (contract_no, bytes(pdf.output()))


def gen_payment_letter(rng, idx, vendor, buyer, ltr_no, ltr_date, inv_no, po_no, items):
    vname, vcity, _, _ = vendor

    subtotal = sum(qty * rate for _, _, rate, qty in items)
    cgst = subtotal * 9 // 100
    grand_total = subtotal + cgst * 2

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "BUSINESS LETTER", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("Letter Details")
    pdf.info_row("Letter No:", ltr_no)
    pdf.info_row("Date:", ltr_date.strftime("%d %B %Y"))
    pdf.info_row("From:", buyer[0])
    pdf.info_row("To:", vname)
    pdf.info_row("Subject:", f"Payment Confirmation - {inv_no}")
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Content")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    body_lines = [
        "Dear Sir/Madam,",
        "",
        f"Re: Payment Confirmation for Invoice {inv_no} against PO {po_no}",
        "",
        f"We, {buyer[0]}, wish to confirm that payment has been processed for the following:",
        "",
        f"  Invoice No: {inv_no}",
        f"  PO Reference: {po_no}",
        f"  Invoice Amount: Rs. {fmt(grand_total)}",
        f"  Payment Mode: NEFT",
        f"  Payment Date: {ltr_date.strftime('%d %B %Y')}",
        "",
        "The above payment covers all items delivered as per the invoice and accepted as per GRN.",
        "",
        "Kindly acknowledge receipt of payment at the earliest convenience.",
        "",
        "Thanking you,",
        "Yours faithfully,",
    ]
    for line in body_lines:
        pdf.cell(0, 5, f"  {line}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, f"For {buyer[0]}", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="R")

    return (ltr_no, bytes(pdf.output()))


def main():
    rng = random.Random(SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_docs = []

    # Cycle 1: 6 docs (SC, PO, DC, GRN, INV, LTR)
    docs1, next_idx = gen_cycle1(rng, 41)
    all_docs.extend(docs1)

    # Cycle 2: 6 docs
    docs2, next_idx = gen_cycle2(rng, next_idx)
    all_docs.extend(docs2)

    # Cycle 3: 6 docs
    docs3, next_idx = gen_cycle3(rng, next_idx)
    all_docs.extend(docs3)

    # Cycle 4: 4 docs (PO, DC, GRN, INV only)
    docs4, _ = gen_cycle4(rng, next_idx)
    all_docs.extend(docs4)

    for doc_id, data in all_docs:
        path = OUTPUT_DIR / f"{doc_id}.pdf"
        path.write_bytes(data)

    types = {}
    for doc_id, _ in all_docs:
        prefix = doc_id.split("-")[0]
        types[prefix] = types.get(prefix, 0) + 1

    print(f"Generated {len(all_docs)} related PDFs in {OUTPUT_DIR}")
    print("\nProcurement Cycles:")
    print(f"  Cycle 1 (NewTech Solutions): SC -> PO -> DC -> GRN -> INV -> LTR")
    print(f"  Cycle 2 (RS Enterprises):    SC -> PO -> DC -> GRN -> INV -> LTR")
    print(f"  Cycle 3 (Apex Industrial):   SC -> PO -> DC -> GRN -> INV -> LTR")
    print(f"  Cycle 4 (Bharat Steel):      PO -> DC -> GRN -> INV (no contract)")
    print(f"\nDocument Types:")
    for t, n in sorted(types.items()):
        print(f"  {t}: {n}")
    print(f"\nCross-reference chains:")
    print(f"  Cycle 1: SC-41 | PO-42 -> DC-43 -> GRN-44 -> INV-45 | LTR-46")
    print(f"  Cycle 2: SC-51 | PO-47 -> DC-48 -> GRN-49 -> INV-50 | LTR-52")
    print(f"  Cycle 3: SC-57 | PO-53 -> DC-54 -> GRN-55 -> INV-56 | LTR-58")
    print(f"  Cycle 4: PO-59 -> DC-60 -> GRN-61 -> INV-62 (orphan PO - no contract)")


if __name__ == "__main__":
    main()
