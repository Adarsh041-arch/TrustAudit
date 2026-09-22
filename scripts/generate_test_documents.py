"""Generate 5 realistic business test documents for TrustAudit (3 PASS, 2 FAIL)."""

import os
from pathlib import Path
import fitz  # PyMuPDF

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "sample_docs" / "test_rules_batch"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def draw_styled_document(
    filename: str,
    doc_title: str,
    meta_pairs: list[tuple[str, str]],
    vendor_lines: list[str],
    buyer_lines: list[str],
    table_headers: list[str],
    table_rows: list[list[str]],
    col_widths: list[float],
    totals_pairs: list[tuple[str, str]],
    bank_pairs: list[tuple[str, str]] | None = None,
    notes: str = "",
):
    doc = fitz.open()
    page = doc.new_page(width=595.28, height=841.89)  # Standard A4

    # 1. Header Banner
    page.draw_rect(fitz.Rect(40, 35, 555.28, 80), color=(0.14, 0.22, 0.35), fill=(0.14, 0.22, 0.35))
    page.insert_text((55, 63), doc_title, fontsize=18, fontname="hebo", color=(1, 1, 1))

    # 2. Metadata Box (Top Right)
    meta_box = fitz.Rect(330, 95, 555.28, 95 + (len(meta_pairs) * 17) + 8)
    page.draw_rect(meta_box, color=(0.82, 0.85, 0.9), fill=(0.96, 0.97, 0.99), width=0.8)
    cur_my = 110
    for lbl, val in meta_pairs:
        page.insert_text((342, cur_my), f"{lbl}: {val}", fontsize=8.5, fontname="helv", color=(0.15, 0.15, 0.15))
        cur_my += 17

    # 3. Parties Box (Top Left)
    parties_box = fitz.Rect(40, 95, 315, 95 + (len(vendor_lines) + len(buyer_lines)) * 15 + 10)
    page.draw_rect(parties_box, color=(0.82, 0.85, 0.9), fill=(0.98, 0.98, 0.99), width=0.8)
    
    cur_py = 110
    for line in vendor_lines:
        page.insert_text((50, cur_py), line, fontsize=8.5, fontname="helv", color=(0.15, 0.15, 0.15))
        cur_py += 15

    for line in buyer_lines:
        page.insert_text((50, cur_py), line, fontsize=8.5, fontname="helv", color=(0.15, 0.15, 0.15))
        cur_py += 15

    # 4. Table Header & Rows
    start_table_y = max(cur_my + 12, cur_py + 12)
    table_w = 515.28
    header_h = 24

    # Table Header visual box
    page.draw_rect(fitz.Rect(40, start_table_y, 40 + table_w, start_table_y + header_h), 
                   color=(0.18, 0.25, 0.36), fill=(0.22, 0.30, 0.42))
    
    header_line_str = "| " + " | ".join(table_headers) + " |"
    page.insert_text((46, start_table_y + 16), header_line_str, fontsize=8.5, fontname="hebo", color=(1, 1, 1))

    cur_ty = start_table_y + header_h
    row_h = 22

    for r_idx, row in enumerate(table_rows):
        bg_col = (0.97, 0.98, 0.99) if r_idx % 2 == 1 else (1, 1, 1)
        page.draw_rect(fitz.Rect(40, cur_ty, 40 + table_w, cur_ty + row_h), 
                       color=(0.85, 0.87, 0.9), fill=bg_col, width=0.5)
        
        row_line_str = "| " + " | ".join(row) + " |"
        page.insert_text((46, cur_ty + 15), row_line_str, fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
        cur_ty += row_h

    # 5. Totals Box (Placed immediately after table so parser hits Subtotal / TABLE_END_MARKERS)
    tot_box_y = cur_ty + 15
    tot_box = fitz.Rect(320, tot_box_y - 4, 40 + table_w, tot_box_y + (len(totals_pairs) * 18) + 10)
    page.draw_rect(tot_box, color=(0.82, 0.85, 0.9), fill=(0.96, 0.97, 0.99), width=0.8)

    cur_tot_y = tot_box_y + 12
    for t_idx, (t_lbl, t_val) in enumerate(totals_pairs):
        is_grand = (t_idx == len(totals_pairs) - 1)
        f_name = "hebo" if is_grand else "helv"
        f_size = 9 if is_grand else 8.5
        f_color = (0.1, 0.2, 0.4) if is_grand else (0.2, 0.2, 0.2)

        page.insert_text((335, cur_tot_y), f"{t_lbl}: {t_val}", fontsize=f_size, fontname=f_name, color=f_color)
        cur_tot_y += 18

    # 6. Bank Details (Placed below totals / bottom section)
    cur_by = cur_tot_y + 15
    if bank_pairs:
        bank_box = fitz.Rect(40, cur_by - 4, 310, cur_by + (len(bank_pairs) * 16) + 20)
        page.draw_rect(bank_box, color=(0.82, 0.85, 0.9), fill=(0.97, 0.98, 0.99), width=0.8)
        page.insert_text((50, cur_by + 12), "Remittance & Banking Details:", fontsize=8.5, fontname="hebo", color=(0.14, 0.22, 0.35))
        bank_text_y = cur_by + 28
        for b_lbl, b_val in bank_pairs:
            page.insert_text((50, bank_text_y), f"{b_lbl}: {b_val}", fontsize=8, fontname="helv", color=(0.15, 0.15, 0.15))
            bank_text_y += 15
        cur_by = bank_text_y + 8

    # 7. Notes and Signatures
    notes_y = max(cur_tot_y + 15, cur_by + 10)
    if notes:
        page.insert_text((40, notes_y), f"Terms & Remarks: {notes}", fontsize=8, fontname="helv", color=(0.3, 0.35, 0.4))

    sig_y = notes_y + 35
    page.draw_line(fitz.Point(380, sig_y), fitz.Point(530, sig_y), color=(0.5, 0.5, 0.5), width=0.8)
    page.insert_text((405, sig_y + 14), "Authorized Signatory", fontsize=8.5, fontname="helv", color=(0.3, 0.3, 0.3))

    out_path = OUTPUT_DIR / filename
    doc.save(str(out_path))
    doc.close()
    print(f"Generated: {out_path.name}")


def main():
    # -------------------------------------------------------------
    # 1. PASS - Purchase Order (PO-2026-4420)
    # -------------------------------------------------------------
    draw_styled_document(
        filename="01_PASS_PurchaseOrder_PO-2026-4420.pdf",
        doc_title="PURCHASE ORDER",
        meta_pairs=[
            ("PO Number", "PO-2026-4420"),
            ("Order Date", "05 August 2026"),
            ("Delivery Date", "25 August 2026"),
            ("Payment Terms", "Net 30 Days"),
        ],
        vendor_lines=[
            "Vendor: Quantum Data Drives LLC",
            "1200 Innovation Parkway, Austin, TX 78758",
        ],
        buyer_lines=[
            "Buyer: BluePeak Technologies Inc.",
            "450 Silicon Avenue, Suite 300, San Jose, CA 95134",
        ],
        table_headers=["#", "Description", "Qty", "Rate", "Amount"],
        col_widths=[30, 260, 45, 90, 90.28],
        table_rows=[
            ["1", "Enterprise Solid State Drive 2TB", "20", "120.00", "2400.00"],
            ["2", "Server Registered Memory 64GB", "10", "180.00", "1800.00"],
        ],
        totals_pairs=[
            ("Grand Total", "4200.00"),
        ],
        notes="Deliver to Receiving Dock #3. All units must include factory test certificate."
    )

    # -------------------------------------------------------------
    # 2. PASS - Delivery Challan (DC-2026-1092)
    # -------------------------------------------------------------
    draw_styled_document(
        filename="02_PASS_DeliveryChallan_DC-2026-1092.pdf",
        doc_title="DELIVERY CHALLAN",
        meta_pairs=[
            ("Challan No", "DC-2026-1092"),
            ("Delivery Date", "15 August 2026"),
            ("PO Reference", "PO-2026-4420"),
        ],
        vendor_lines=[
            "Vendor: Quantum Data Drives LLC",
            "1200 Innovation Parkway, Austin, TX 78758",
        ],
        buyer_lines=[
            "Consignee: BluePeak Technologies Inc.",
            "Receiving Dock #3, 450 Silicon Avenue, San Jose, CA 95134",
        ],
        table_headers=["#", "Description", "Qty", "Unit"],
        col_widths=[30, 310, 80, 95.28],
        table_rows=[
            ["1", "Enterprise NVMe Solid State Drive 2TB", "20", "Units"],
            ["2", "Enterprise Registered Server RAM 64GB", "10", "Units"],
        ],
        totals_pairs=[
            ("Total Packages", "2 Cartons"),
        ],
        notes="Goods dispatched in sealed transit packaging against purchase order PO-2026-4420."
    )

    # -------------------------------------------------------------
    # 3. PASS - Tax Invoice (INV-2026-8801)
    # -------------------------------------------------------------
    draw_styled_document(
        filename="03_PASS_Invoice_INV-2026-8801.pdf",
        doc_title="TAX INVOICE",
        meta_pairs=[
            ("Invoice No", "INV-2026-8801"),
            ("Invoice Date", "12 August 2026"),
            ("PO Reference", "PO-2026-8801"),
        ],
        vendor_lines=[
            "Vendor: Apex Industrial Systems Pvt. Ltd.",
            "Plot 42, MIDC Industrial Area, Andheri East, Mumbai 400069",
            "GSTIN: 27AABCA1234F1Z5",
        ],
        buyer_lines=[
            "Buyer: Horizon Logistics Solutions Ltd.",
            "Prestige Tech Park, Whitefield, Bengaluru 560066",
            "GSTIN: 29AABCH5678K1Z2",
        ],
        table_headers=["#", "Description", "HSN", "Qty", "Rate", "Amount"],
        col_widths=[25, 210, 65, 35, 85, 95.28],
        table_rows=[
            ["1", "Industrial Ethernet Switch", "85176290", "5", "18000.00", "90000.00"],
            ["2", "Cat6A Patch Cable", "85444990", "50", "300.00", "15000.00"],
        ],
        totals_pairs=[
            ("Subtotal", "INR 105000.00"),
            ("CGST (9%)", "INR 9450.00"),
            ("SGST (9%)", "INR 9450.00"),
            ("Total Tax", "INR 18900.00"),
            ("Grand Total", "INR 123900.00"),
        ],
        bank_pairs=[
            ("Bank Name", "HDFC Bank Ltd."),
            ("Account No", "50200012345678"),
            ("IFSC Code", "HDFC0001234"),
        ],
        notes="Amount in Words: One Lakh Twenty Three Thousand Nine Hundred Rupees Only."
    )

    # -------------------------------------------------------------
    # 4. FAIL - Invoice with Line Calculation Typo (INV-2026-9042)
    # -------------------------------------------------------------
    # Error: Line 1 has 8 units @ 9,500.00 = 76,000.00, but stated as 82,000.00
    draw_styled_document(
        filename="04_FAIL_Invoice_Sterling_LineMismatch.pdf",
        doc_title="TAX INVOICE",
        meta_pairs=[
            ("Invoice No", "INV-2026-9042"),
            ("Invoice Date", "14 August 2026"),
            ("PO Reference", "PO-2026-9042"),
        ],
        vendor_lines=[
            "Vendor: Sterling Office Supplies Pvt. Ltd.",
            "B-18 Okhla Phase II, Industrial Area, New Delhi 110020",
            "GSTIN: 07AAACS1234D1Z8",
        ],
        buyer_lines=[
            "Buyer: Metro Consulting Services Ltd.",
            "Connaught Place, Barakhamba Road, New Delhi 110001",
            "GSTIN: 07AABCM5678P1Z3",
        ],
        table_headers=["#", "Description", "HSN", "Qty", "Rate", "Amount"],
        col_widths=[25, 210, 65, 35, 85, 95.28],
        table_rows=[
            ["1", "Ergonomic Mesh Task Chair", "94013000", "8", "9500.00", "82000.00"],  # Error: 8 x 9500 = 76000
            ["2", "Standing Desk Converter", "94031000", "4", "14000.00", "56000.00"],
        ],
        totals_pairs=[
            ("Subtotal", "INR 138000.00"),
            ("CGST (9%)", "INR 12420.00"),
            ("SGST (9%)", "INR 12420.00"),
            ("Total Tax", "INR 24840.00"),
            ("Grand Total", "INR 162840.00"),
        ],
        bank_pairs=[
            ("Bank Name", "Axis Bank Ltd."),
            ("Account No", "918020012345678"),
            ("IFSC Code", "UTIB0000123"),
        ],
        notes="Defective items must be reported within 48 hours of delivery."
    )

    # -------------------------------------------------------------
    # 5. FAIL - Invoice with Grand Total Addition Discrepancy
    # -------------------------------------------------------------
    # Error: Subtotal = 71,500.00, Tax = 12,870.00. Expected = 84,370.00. Stated = 85,370.00 (+$1000 addition error)
    draw_styled_document(
        filename="05_FAIL_Invoice_Vertex_GrandTotalMismatch.pdf",
        doc_title="TAX INVOICE",
        meta_pairs=[
            ("Invoice No", "INV-2026-7731"),
            ("Invoice Date", "19 August 2026"),
            ("PO Reference", "PO-2026-7731"),
        ],
        vendor_lines=[
            "Vendor: Vertex Engineering Solutions Pvt. Ltd.",
            "88 Industrial Highway, Sector 4, Gandhinagar 382010",
            "GSTIN: 24AABCV4321K1Z9",
        ],
        buyer_lines=[
            "Buyer: Pacific Marine Infrastructure Ltd.",
            "Harbor Estate, Pier 9, Mumbai 400001",
            "GSTIN: 27AABCP8765L1Z1",
        ],
        table_headers=["#", "Description", "HSN", "Qty", "Rate", "Amount"],
        col_widths=[25, 215, 80, 35, 80, 80.28],
        table_rows=[
            ["1", "Heavy Duty Benchtop Drill Press", "84592900", "3", "16500.00", "49500.00"],
            ["2", "Precision Lathe Chuck Set", "84662000", "2", "11000.00", "22000.00"],
        ],
        totals_pairs=[
            ("Subtotal", "INR 71500.00"),
            ("CGST (9%)", "INR 6435.00"),
            ("SGST (9%)", "INR 6435.00"),
            ("Total Tax", "INR 12870.00"),
            ("Grand Total", "INR 85370.00"),  # Error: 71500 + 12870 = 84370 != 85370 (+$1,000 mismatch)
        ],
        bank_pairs=[
            ("Bank Name", "ICICI Bank Ltd."),
            ("Account No", "001205012345"),
            ("IFSC Code", "ICIC0000012"),
        ],
        notes="Standard warranty applies for 12 months from delivery."
    )


if __name__ == "__main__":
    main()
