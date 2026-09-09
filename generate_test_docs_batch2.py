#!/usr/bin/env python3
"""Generate 20 more test PDFs (indices 21-40) for TrustAudit testing."""
import random
import string
from datetime import date, timedelta
from pathlib import Path
from fpdf import FPDF

SEED = 199
BASE_DATE = date(2026, 6, 1)
OUTPUT_DIR = Path(__file__).resolve().parent / "TEST_DOCS_LARGE"

VENDORS = [
    ("NewTech Solutions Pvt Ltd", "Bangalore", "29"),
    ("RS Enterprises", "Mumbai", "27"),
    ("Apex Industrial Supplies", "Pune", "27"),
    ("Shree Ganesh Traders", "Ahmedabad", "24"),
    ("Delta Engineering Works", "Chennai", "33"),
    ("Kumar Electricals", "Hyderabad", "36"),
    ("Precision Tools India", "Coimbatore", "33"),
    ("Om Sai Packaging", "Surat", "24"),
    ("Bharat Steel Corporation", "Jamshedpur", "20"),
    ("Vertex IT Services", "Noida", "09"),
]

BUYERS = [
    ("BuildRight Contractors", "15, Industrial Area, Andheri East", "Mumbai, Maharashtra - 400093", "27AAAFB1234J1Z2"),
    ("Skyline Infra Projects", "88, MIDC Phase II", "Pune, Maharashtra - 411026", "27AABCS9876K1Z5"),
    ("Metro Retail Chains", "4, Commercial Street", "Bangalore, Karnataka - 560001", "29AACCM4567L1Z8"),
    ("Global Manufacturing Co", "Plot 12, SIPCOT", "Chennai, Tamil Nadu - 602105", "33AADCG7890M1Z1"),
]

ITEMS = [
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

    def info_row(self, label, value, w1=40, w2=80):
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


def make_gstin(rng, state_code):
    letters = "".join(rng.choices(string.ascii_uppercase, k=5))
    digits = "".join(rng.choices(string.digits, k=4))
    return f"{state_code}{letters}{digits}{rng.choice(string.ascii_uppercase)}{rng.choice(string.digits)}Z{rng.choice(string.digits + string.ascii_uppercase)}"


def make_ifsc(rng):
    return "".join(rng.choices(string.ascii_uppercase, k=4)) + "0" + "".join(rng.choices(string.digits, k=6))


def gen_invoice(rng, idx):
    vendor_name, vendor_city, state_code = rng.choice(VENDORS)
    buyer = rng.choice(BUYERS)
    vendor_gstin = make_gstin(rng, state_code)
    doc_id = f"INV-2026-{idx:04d}"
    inv_date = BASE_DATE + timedelta(days=rng.randrange(0, 45))
    due_date = inv_date + timedelta(days=30)
    n_items = rng.randrange(2, 6)
    chosen = rng.sample(ITEMS, n_items)

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "TAX INVOICE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, vendor_name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, f"{vendor_city}, India", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"GSTIN: {vendor_gstin}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.h_rule()

    pdf.section_title("Invoice Details")
    pdf.info_row("Invoice No:", doc_id)
    pdf.info_row("Date:", inv_date.strftime("%d %B %Y"))
    pdf.info_row("Due Date:", due_date.strftime("%d %B %Y"))
    pdf.info_row("PO Reference:", f"PO-2026-{rng.randrange(100, 999)}")
    pdf.ln(2)

    pdf.section_title("Bill To")
    pdf.info_row("Name:", buyer[0])
    pdf.info_row("Address:", buyer[1])
    pdf.info_row("", buyer[2])
    pdf.info_row("GSTIN:", buyer[3])
    pdf.ln(3)
    pdf.h_rule()

    pdf.section_title("Line Items")
    col_w = [8, 58, 22, 18, 26, 30, 28]
    pdf.tbl_header(col_w, ["#", "Description", "HSN", "Qty", "Rate", "Amount", "Taxable Value"])
    subtotal = 0
    for i, (desc, hsn, rate) in enumerate(chosen, 1):
        qty = rng.randrange(1, 20)
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
    pdf.info_row("Bank:", "Kotak Mahindra Bank")
    pdf.info_row("A/C No:", str(rng.randrange(10**9, 10**10)))
    pdf.info_row("IFSC:", make_ifsc(rng))
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 6, f"for {vendor_name}", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="R")

    return doc_id, bytes(pdf.output())


def gen_po(rng, idx):
    vendor_name, vendor_city, state_code = rng.choice(VENDORS)
    vendor_gstin = make_gstin(rng, state_code)
    doc_id = f"PO-2026-{idx:04d}"
    order_date = BASE_DATE + timedelta(days=rng.randrange(0, 45))
    delivery = order_date + timedelta(days=15)
    n_items = rng.randrange(2, 5)
    chosen = rng.sample(ITEMS, n_items)

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "PURCHASE ORDER", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("PO Details")
    pdf.info_row("PO No:", doc_id)
    pdf.info_row("Order Date:", order_date.strftime("%d %B %Y"))
    pdf.info_row("Vendor:", vendor_name)
    pdf.info_row("Payment Terms:", "Net 45")
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Vendor Information")
    pdf.info_row("Name:", vendor_name)
    pdf.info_row("Address:", f"{vendor_city}, India")
    pdf.info_row("GSTIN:", vendor_gstin)
    pdf.ln(3)

    pdf.section_title("Line Items")
    col_w = [8, 58, 22, 18, 26, 30]
    pdf.tbl_header(col_w, ["#", "Description", "HSN", "Qty", "Rate", "Amount"])
    total = 0
    for i, (desc, hsn, rate) in enumerate(chosen, 1):
        qty = rng.randrange(1, 20)
        amt = qty * rate
        total += amt
        pdf.tbl_row(col_w, [str(i), desc, hsn, str(qty), fmt(rate), fmt(amt)])

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*pdf.COLORS["alt_row"])
    pdf.cell(sum(col_w[:5]), 7, "  Total Order Value", border=1, align="L", fill=True)
    pdf.cell(col_w[5], 7, fmt(total), border=1, align="R", fill=True)
    pdf.ln()
    pdf.ln(5)

    delivery_str = delivery.strftime("%d %B %Y")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, f"  - Delivery by {delivery_str}.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.h_rule()
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 6, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="R")

    return doc_id, bytes(pdf.output())


def gen_dc(rng, idx):
    vendor_name, vendor_city, _ = rng.choice(VENDORS)
    doc_id = f"DC-2026-{idx:04d}"
    dc_date = BASE_DATE + timedelta(days=rng.randrange(0, 45))

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "DELIVERY CHALLAN", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("Challan Details")
    pdf.info_row("Challan No:", doc_id)
    pdf.info_row("Date:", dc_date.strftime("%d %B %Y"))
    pdf.info_row("PO Reference:", f"PO-2026-{rng.randrange(100, 999)}")
    pdf.info_row("Vehicle No:", f"KA-{rng.randrange(10, 99)}-AB-{rng.randrange(1000, 9999)}")
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Dispatch From")
    pdf.info_row("Name:", vendor_name)
    pdf.info_row("Address:", f"{vendor_city}, India")
    pdf.ln(3)

    pdf.section_title("Items")
    col_w = [8, 62, 22, 18, 30]
    pdf.tbl_header(col_w, ["#", "Description", "HSN", "Qty", "Unit"])
    for i, (desc, hsn, _) in enumerate(rng.sample(ITEMS, rng.randrange(2, 5)), 1):
        pdf.tbl_row(col_w, [str(i), desc, hsn, str(rng.randrange(1, 20)), "Nos"])

    return doc_id, bytes(pdf.output())


def gen_grn(rng, idx):
    vendor_name, vendor_city, _ = rng.choice(VENDORS)
    doc_id = f"GRN-2026-{idx:04d}"
    grn_date = BASE_DATE + timedelta(days=rng.randrange(0, 45))

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "GOODS RECEIPT NOTE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("GRN Details")
    pdf.info_row("GRN No:", doc_id)
    pdf.info_row("Date:", grn_date.strftime("%d %B %Y"))
    pdf.info_row("PO Reference:", f"PO-2026-{rng.randrange(100, 999)}")
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Receiving Details")
    pdf.info_row("Received From:", vendor_name)
    pdf.info_row("Location:", f"Warehouse, {vendor_city}")
    pdf.ln(2)

    pdf.section_title("Received Items")
    col_w = [8, 58, 20, 24, 24]
    pdf.tbl_header(col_w, ["#", "Description", "DC Qty", "Received Qty", "Accepted"])
    for i, (desc, _, _) in enumerate(rng.sample(ITEMS, rng.randrange(2, 5)), 1):
        qty = rng.randrange(1, 20)
        pdf.tbl_row(col_w, [str(i), desc, str(qty), str(qty), str(qty)])

    return doc_id, bytes(pdf.output())


def gen_contract(rng, idx):
    vendor_name, vendor_city, state_code = rng.choice(VENDORS)
    buyer_name = rng.choice(BUYERS)[0]
    contract_date = BASE_DATE + timedelta(days=rng.randrange(0, 45))
    doc_id = f"SC-2026-{idx:04d}"

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "SALES CONTRACT", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("Contract Details")
    pdf.info_row("Contract No:", doc_id)
    pdf.info_row("Date:", contract_date.strftime("%d %B %Y"))
    pdf.info_row("Buyer:", buyer_name)
    pdf.info_row("Seller:", vendor_name)
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Terms and Conditions")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    terms = [
        "1. This Agreement is entered into between the Seller and the Buyer.",
        "2. The Seller agrees to supply goods as per the specifications listed.",
        "3. Payment shall be made within 30 days of delivery.",
        "4. Any disputes shall be resolved under the jurisdiction of Mumbai courts.",
        "5. This contract is valid for 12 months from the date of signing.",
        "6. Delivery shall be FOB from the Seller's warehouse.",
        "7. Warranty period: 12 months from date of delivery.",
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
    pdf.cell(90, 5, f"For {vendor_name}", align="L")
    pdf.cell(90, 5, f"For {buyer_name}", new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.cell(90, 5, "Authorised Signatory", align="L")
    pdf.cell(90, 5, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="L")

    return doc_id, bytes(pdf.output())


def gen_letter(rng, idx):
    vendor_name, vendor_city, _ = rng.choice(VENDORS)
    letter_date = BASE_DATE + timedelta(days=rng.randrange(0, 45))
    doc_id = f"LTR-2026-{idx:04d}"
    subject = rng.choice([
        "Payment Confirmation",
        "Dispatch Notification",
        "Quotation Submission",
        "Service Level Agreement Renewal",
        "Annual Price List Update",
        "Credit Terms Extension Request",
        "Product Catalogue Launch",
    ])

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "BUSINESS LETTER", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("Letter Details")
    pdf.info_row("Letter No:", doc_id)
    pdf.info_row("Date:", letter_date.strftime("%d %B %Y"))
    pdf.info_row("From:", vendor_name)
    pdf.info_row("To:", rng.choice(BUYERS)[0])
    pdf.info_row("Subject:", subject)
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Content")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    body_lines = [
        "Dear Sir/Madam,",
        "",
        f"Re: {subject}",
        "",
        f"We, {vendor_name}, {vendor_city}, wish to bring to your attention the following matter regarding {subject.lower()}.",
        "",
        "We confirm that all terms and conditions discussed in our previous meeting have been reviewed and accepted. The revised pricing structure and delivery schedules are enclosed for your reference.",
        "",
        "Kindly acknowledge receipt of this letter and confirm your acceptance at the earliest convenience.",
        "",
        "Thanking you,",
        "Yours faithfully,",
    ]
    for line in body_lines:
        pdf.cell(0, 5, f"  {line}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, f"For {vendor_name}", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="R")

    return doc_id, bytes(pdf.output())


def gen_certificate(rng, idx):
    vendor_name, vendor_city, _ = rng.choice(VENDORS)
    cert_date = BASE_DATE + timedelta(days=rng.randrange(0, 45))
    doc_id = f"CO-2026-{idx:04d}"

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*pdf.COLORS["primary"])
    pdf.cell(0, 10, "CERTIFICATE OF ORIGIN", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.section_title("Certificate Details")
    pdf.info_row("Certificate No:", doc_id)
    pdf.info_row("Date:", cert_date.strftime("%d %B %Y"))
    pdf.info_row("Invoice Ref:", f"INV-2026-{rng.randrange(100, 999)}")
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Exporter")
    pdf.info_row("Name:", vendor_name)
    pdf.info_row("Address:", f"{vendor_city}, India")
    pdf.info_row("GSTIN:", make_gstin(rng, "29"))
    pdf.ln(2)

    pdf.section_title("Consignee")
    buyer = rng.choice(BUYERS)
    pdf.info_row("Name:", buyer[0])
    pdf.info_row("Address:", buyer[1])
    pdf.info_row("Country:", "India")
    pdf.ln(2)
    pdf.h_rule()

    pdf.section_title("Goods Description")
    col_w = [8, 58, 22, 18, 26, 30]
    pdf.tbl_header(col_w, ["#", "Description", "HSN", "Qty", "Unit", "Value"])
    chosen = rng.sample(ITEMS, rng.randrange(2, 4))
    for i, (desc, hsn, rate) in enumerate(chosen, 1):
        qty = rng.randrange(1, 10)
        pdf.tbl_row(col_w, [str(i), desc, hsn, str(qty), "Nos", fmt(qty * rate)])

    pdf.ln(4)
    pdf.section_title("Declaration")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.COLORS["text"])
    pdf.cell(0, 5, "  We hereby certify that the goods described above originate in India.", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "  This certificate is issued under the authority of the Chamber of Commerce.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, "Authorised Signatory", new_x="LMARGIN", new_y="NEXT", align="R")

    return doc_id, bytes(pdf.output())


def main():
    rng = random.Random(SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    docs = []
    idx = 21

    for _ in range(6):
        doc_id, data = gen_invoice(rng, idx)
        docs.append((doc_id, data))
        idx += 1

    for _ in range(4):
        doc_id, data = gen_po(rng, idx)
        docs.append((doc_id, data))
        idx += 1

    for _ in range(3):
        doc_id, data = gen_dc(rng, idx)
        docs.append((doc_id, data))
        idx += 1

    for _ in range(2):
        doc_id, data = gen_grn(rng, idx)
        docs.append((doc_id, data))
        idx += 1

    for _ in range(2):
        doc_id, data = gen_contract(rng, idx)
        docs.append((doc_id, data))
        idx += 1

    for _ in range(2):
        doc_id, data = gen_letter(rng, idx)
        docs.append((doc_id, data))
        idx += 1

    doc_id, data = gen_certificate(rng, idx)
    docs.append((doc_id, data))

    for doc_id, data in docs:
        path = OUTPUT_DIR / f"{doc_id}.pdf"
        path.write_bytes(data)

    types = {}
    for doc_id, _ in docs:
        prefix = doc_id.split("-")[0]
        types[prefix] = types.get(prefix, 0) + 1

    print(f"Generated {len(docs)} PDFs in {OUTPUT_DIR}")
    for t, n in sorted(types.items()):
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()
