import io
import datetime
from typing import Dict, Any, List

# docx imports
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

# reportlab imports
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

def _set_cell_shading(cell, color_hex: str):
    from docx.oxml.ns import qn
    shading = cell._tc.get_or_add_tcPr()
    shd = shading.makeelement(qn("w:shd"), {
        qn("w:val"): "clear",
        qn("w:color"): "auto",
        qn("w:fill"): color_hex,
    })
    shading.append(shd)

def generate_docx_report(audit_data: Dict[str, Any]) -> bytes:
    """
    Generates a professional DOCX audit report incorporating explainable findings,
    RAG policy citations, risk scoring, ML prediction, and cross-verification results.
    """
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(11)
    style.paragraph_format.space_after = Pt(6)

    report_dict = audit_data.get("report", {}) if isinstance(audit_data.get("report"), dict) else {}
    doc_results = audit_data.get("document_results") or report_dict.get("document_results", [])
    audit_title = audit_data.get("audit_title") or report_dict.get("audit_title", "TrustAudit Report")

    # Title Page / Header
    title = doc.add_heading(audit_title, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    p_meta = doc.add_paragraph()
    p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_meta.add_run(f"Generated: {date_str} | Platform: TrustAudit Intelligence Platform\n").italic = True
    
    # Executive Summary Section
    doc.add_heading("1. Executive Summary", level=1)
    p_exec = doc.add_paragraph()
    p_exec.add_run(
        f"This audit report compiles the compliance findings and risk analytics. "
        f"A total of {len(doc_results)} document(s) were audited. "
    )
    
    # Add cross verification notes
    cross = audit_data.get("cross_verification", {})
    if cross:
        p_exec.add_run(f"\nThree-Way Matching Status: {cross.get('status', 'unknown')}. ")
        p_exec.add_run(f"Details: {cross.get('reconciliation_summary', '')}\n")
        
    # Per-Document Details
    doc.add_heading("2. Detailed Document Compliance & Explainability", level=1)
    
    for idx, r in enumerate(doc_results, 1):

        doc.add_heading(f"2.{idx} File: {r['document_name']}", level=2)
        
        # Risk Card / Overall
        p_score = doc.add_paragraph()
        p_score.add_run("Compliance Score: ").bold = True
        p_score.add_run(f"{r['score']:.1f}%   |   ")
        
        risk_lvl = r.get("risk_level", "Low Risk")
        run_risk = p_score.add_run(f"Risk Category: {risk_lvl.upper()}")
        run_risk.bold = True
        
        # Color coding risk levels
        if risk_lvl == "High Risk":
            run_risk.font.color.rgb = RGBColor(0x99, 0x3C, 0x1D)
        elif risk_lvl == "Medium Risk":
            run_risk.font.color.rgb = RGBColor(0xD9, 0x77, 0x06)
        else:
            run_risk.font.color.rgb = RGBColor(0x0F, 0x6E, 0x56)
            
        doc.add_paragraph(f"Confidence Level: {r.get('confidence_score', 0.0):.1f}%")
        if r.get("human_review_recommended", False):
            p_warn = doc.add_paragraph()
            p_warn.add_run("⚠️ HUMAN REVIEW RECOMMENDED: Audit confidence score below threshold or High Risk detected.").font.color.rgb = RGBColor(0x99, 0x3C, 0x1D)
            
        # ML Prediction Details
        ml = r.get("ml_prediction", {})
        if ml:
            p_ml = doc.add_paragraph()
            p_ml.add_run("ML Risk Classification: ").bold = True
            p_ml.add_run(f"{ml.get('prediction', 'unknown')} (Mode: {ml.get('mode', 'fallback')})\n")
            probs = ml.get("probabilities", {})
            p_ml.add_run(f"Probabilities - Compliant: {probs.get('compliant', 0):.1f}%, Partially Compliant: {probs.get('partially_compliant', 0):.1f}%, Non-Compliant: {probs.get('non_compliant', 0):.1f}%")
            
        doc.add_paragraph(f"Summary: {r.get('summary_text', '')}")
        doc.add_paragraph(f"Risk Explanation: {r.get('risk_explanation', '')}")

        # Findings Table
        violations = r.get("failed_rules", [])
        if violations:
            doc.add_heading("Policy Violations & Evidence Citations", level=3)
            table = doc.add_table(rows=1, cols=4)
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.style = "Table Grid"
            
            hdr_cells = table.rows[0].cells
            headers = ["Rule", "Severity", "Finding & Evidence", "Impact & Action"]
            for i, h in enumerate(headers):
                hdr_cells[i].text = h
                _set_cell_shading(hdr_cells[i], "E5E7EB")
                for p in hdr_cells[i].paragraphs:
                    for run in p.runs:
                        run.bold = True
                        run.font.size = Pt(10)
                        
            for v in violations:
                row_cells = table.add_row().cells
                row_cells[0].text = f"{v.get('rule_id')}: {v.get('rule_title')}"
                row_cells[1].text = v.get("severity", "medium").upper()
                
                # Finding & Evidence
                f_e = f"Finding: {v.get('finding')}\nEvidence: {v.get('evidence')}"
                if v.get("page_number") is not None:
                    f_e += f" (p. {v.get('page_number')})"
                row_cells[2].text = f_e
                
                # Impact & Recommendation
                i_r = f"Impact: {v.get('impact')}\nRecommendation: {v.get('recommendation')}"
                row_cells[3].text = i_r
                
                # Set formatting font sizes
                for cell in row_cells:
                    for p in cell.paragraphs:
                        for run in p.runs:
                            run.font.size = Pt(9.5)
                            
        else:
            doc.add_paragraph("Compliant. No rule violations detected on this document.")
            
        doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()

def generate_pdf_report(audit_data: Dict[str, Any]) -> bytes:
    """
    Generates an enterprise-grade PDF report using ReportLab,
    with custom layouts, charts descriptions, and compliance breakdowns.
    """
    if not REPORTLAB_AVAILABLE:
        # Fallback to docx if PDF libraries are not loaded/installed
        logger.warning("ReportLab not available. PDF export falls back to DOCX file format.")
        return generate_docx_report(audit_data)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    story = []

    # Palette
    c_primary = colors.HexColor("#0F6E56")
    c_danger = colors.HexColor("#993C1D")
    c_warning = colors.HexColor("#D97706")
    c_gray = colors.HexColor("#4B5563")

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=c_primary,
        alignment=1, # Center
        spaceAfter=15
    )
    
    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=c_primary,
        spaceBefore=18,
        spaceAfter=8,
        keepWithNext=True
    )
    
    h2_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=c_gray,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        "BodyText_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=6
    )

    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        alignment=1,
        spaceAfter=20
    )

    report_dict = audit_data.get("report", {}) if isinstance(audit_data.get("report"), dict) else {}
    doc_results = audit_data.get("document_results") or report_dict.get("document_results", [])
    audit_title = audit_data.get("audit_title") or report_dict.get("audit_title", "TrustAudit Audit Report")

    # Document Header
    story.append(Paragraph(audit_title, title_style))
    story.append(Paragraph(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | Compliance Intelligence Platform", meta_style))
    story.append(Spacer(1, 10))

    # Section 1: Executive Summary
    story.append(Paragraph("1. Executive Summary", h1_style))
    doc_count = len(doc_results)
    summary_p = f"This comprehensive compliance review evaluates {doc_count} document(s). "
    cross = audit_data.get("cross_verification", {})
    if cross:
        summary_p += f"<br/><b>Three-Way Reconciliation:</b> {cross.get('reconciliation_summary', '')}"
    story.append(Paragraph(summary_p, body_style))
    story.append(Spacer(1, 10))

    # Section 2: Detailed Document Findings
    story.append(Paragraph("2. Document Assessments & Risk Scoring", h1_style))

    for idx, r in enumerate(doc_results, 1):

        doc_heading = f"2.{idx} File: {r['document_name']} ({r.get('document_type', 'unknown').replace('_', ' ').title()})"
        story.append(Paragraph(doc_heading, h2_style))
        
        # Risk score line
        risk_lvl = r.get("risk_level", "Low Risk")
        color_hex = "#993C1D" if risk_lvl == "High Risk" else ("#D97706" if risk_lvl == "Medium Risk" else "#0F6E56")
        
        score_text = (
            f"<b>Compliance Score:</b> {r['score']:.1f}% | "
            f"<b>Confidence:</b> {r.get('confidence_score', 0.0):.1f}% | "
            f"<b>Risk Classification:</b> <font color='{color_hex}'><b>{risk_lvl.upper()}</b></font>"
        )
        story.append(Paragraph(score_text, body_style))
        
        if r.get("human_review_recommended", False):
            story.append(Paragraph("<font color='#993C1D'><b>⚠️ HUMAN REVIEW RECOMMENDED: Review required due to low confidence score or severe compliance findings.</b></font>", body_style))
            
        # ML prediction
        ml = r.get("ml_prediction", {})
        if ml:
            probs = ml.get("probabilities", {})
            ml_text = (
                f"<b>ML Predictive Status:</b> {ml.get('prediction', 'unknown')} | "
                f"Compliant: {probs.get('compliant', 0):.1f}%, "
                f"Partially Compliant: {probs.get('partially_compliant', 0):.1f}%, "
                f"Non-Compliant: {probs.get('non_compliant', 0):.1f}%"
            )
            story.append(Paragraph(ml_text, body_style))

        story.append(Paragraph(f"<b>Summary:</b> {r.get('summary_text', '')}", body_style))
        story.append(Paragraph(f"<b>Risk Explanation:</b> {r.get('risk_explanation', '')}", body_style))
        
        # Violations Table
        violations = r.get("failed_rules", [])
        if violations:
            story.append(Paragraph("<b>Policy Violations & Evidence:</b>", body_style))
            table_data = [[
                Paragraph("<b>Rule</b>", body_style),
                Paragraph("<b>Severity</b>", body_style),
                Paragraph("<b>Finding & Evidence</b>", body_style),
                Paragraph("<b>Impact & Recommendation</b>", body_style)
            ]]
            
            for v in violations:
                rule_cell = Paragraph(f"<b>{v.get('rule_id')}</b><br/>{v.get('rule_title')}", body_style)
                sev_color = "#993C1D" if v.get("severity") in ("critical", "high") else "#4B5563"
                sev_cell = Paragraph(f"<font color='{sev_color}'><b>{v.get('severity', 'medium').upper()}</b></font>", body_style)
                
                f_e_text = f"<b>Finding:</b> {v.get('finding')}<br/><b>Evidence:</b> {v.get('evidence')}"
                if v.get("page_number") is not None:
                    f_e_text += f" (page {v.get('page_number')})"
                fe_cell = Paragraph(f_e_text, body_style)
                
                ir_cell = Paragraph(f"<b>Impact:</b> {v.get('impact')}<br/><b>Mitigation:</b> {v.get('recommendation')}", body_style)
                
                table_data.append([rule_cell, sev_cell, fe_cell, ir_cell])
                
            col_widths = [80, 70, 180, 174]
            t = Table(table_data, colWidths=col_widths)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E5E7EB")),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#D1D5DB")),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(t)
        else:
            story.append(Paragraph("<i>Compliant. No active policy rules failed.</i>", body_style))
            
        story.append(Spacer(1, 10))

    # Build document
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
