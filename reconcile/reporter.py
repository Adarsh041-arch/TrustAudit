"""DOCX/PDF reconciliation reports: match-rate banner + exception table.

Adapted from audit_v2.reporting.report_builders (same libraries, same style).
"""
from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from logging import getLogger

from reconcile.matcher import DATE_TOLERANCE_DAYS, FEE_TOLERANCE, RULESET_VERSION
from reconcile.models import MatchResult, MatchStatus, ReconciliationRun

logger = getLogger(__name__)

try:
    from reportlab.lib import colors  # type: ignore[import-untyped]
    from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
    from reportlab.lib.styles import ParagraphStyle  # type: ignore[import-untyped]
    from reportlab.platypus import (  # type: ignore[import-untyped]
        Paragraph, SimpleDocTemplate, Table, TableStyle,
    )

    REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover
    REPORTLAB_AVAILABLE = False


def _exceptions(run: ReconciliationRun) -> list[MatchResult]:
    return [r for r in run.results if r.status is MatchStatus.EXCEPTION]


def _fmt(value) -> str:
    return "" if value is None else str(value)


def _footer_line(run: ReconciliationRun) -> str:
    line = (
        f"Ruleset {RULESET_VERSION} · fee tolerance ±{FEE_TOLERANCE.as_decimal()} "
        f"· max settlement drift {DATE_TOLERANCE_DAYS} days · "
        f"{len(run.results)} verdicts fingerprinted · mode: {run.mode}"
    )
    if run.mode_note:
        line += f" · {run.mode_note}"
    return line


def _drilldown_rows(r: MatchResult) -> list[list[str]]:
    rows: list[list[str]] = []
    if r.payout:
        rows.append(["Payout", r.txn_id, str(r.payout.payout_amount),
                     r.payout.currency, str(r.payout.payout_date)])
    if r.bank:
        rows.append(["Bank", r.bank.bank_ref, str(r.bank.credited_amount),
                     r.bank.currency, str(r.bank.value_date)])
    if r.ledger:
        rows.append(["Ledger", r.ledger.invoice_id, str(r.ledger.expected_amount),
                     r.ledger.currency, str(r.ledger.due_date)])
    return rows


def generate_docx_recon_report(run: ReconciliationRun) -> bytes:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    doc.add_heading("Payment Reconciliation Report", level=0)
    doc.add_paragraph(
        f"Run {run.run_id} · generated "
        f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} · {run.total} transactions · "
        f"{run.mode.upper()} MODE"
        + (f" ({run.mode_note})" if run.mode_note else "")
    )

    banner = doc.add_paragraph()
    banner_run = banner.add_run(f"{run.matched} / {run.total} MATCHED ({run.match_rate * 100}%)")
    banner_run.bold = True
    banner_run.font.size = Pt(20)

    v = run.validation
    if v is not None:
        vp = doc.add_paragraph()
        vr = vp.add_run(
            f"Ground-truth validation: {v.detected}/{v.total_breaks} breaks detected · "
            f"{v.fee_matches_confirmed}/{v.fee_total} fee-tolerance matches · "
            f"{len(v.false_positives)} false positives -> {'PASS' if v.passed else 'FAIL'}"
        )
        vr.bold = True

    if run.llm_summary:
        p = doc.add_paragraph(run.llm_summary)
        p.add_run("\n[AI-generated summary — verified by deterministic engine]").italic = True

    excs = _exceptions(run)
    doc.add_heading(f"Exceptions ({len(excs)})", level=1)
    if excs:
        table = doc.add_table(rows=1, cols=6)
        table.style = "Table Grid"
        for i, title in enumerate(["Txn ID", "Type", "Payout", "Bank", "Delta", "Drift"]):
            table.rows[0].cells[i].text = title
        for r in excs:
            cells = table.add_row().cells
            payout_amt = _fmt(r.payout.payout_amount if r.payout else None)
            bank_amt = _fmt(r.bank.credited_amount if r.bank else None)
            drift = f"{r.date_drift_days}d" if r.date_drift_days else ""
            for i, val in enumerate([
                r.txn_id, r.exception_type.value if r.exception_type else "",
                payout_amt, bank_amt, _fmt(r.amount_delta), drift,
            ]):
                cells[i].text = val
            if r.llm_explanation:
                cells[5].text += f" — AI: {r.llm_explanation}"

        doc.add_heading("Exception drilldown (source rows)", level=2)
        for r in excs:
            doc.add_paragraph(f"{r.txn_id}")
            t = doc.add_table(rows=1, cols=5)
            t.style = "Table Grid"
            for i, title in enumerate(["Source", "Ref", "Amount", "Currency", "Date"]):
                t.rows[0].cells[i].text = title
            for row in _drilldown_rows(r):
                cells = t.add_row().cells
                for i, val in enumerate(row):
                    cells[i].text = val

    footer = doc.add_paragraph(_footer_line(run))
    footer.runs[0].font.size = Pt(8)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def generate_pdf_recon_report(run: ReconciliationRun) -> bytes:
    if not REPORTLAB_AVAILABLE:  # pragma: no cover
        logger.warning("reportlab not installed; falling back to DOCX report")
        return generate_docx_recon_report(run)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
    title = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=16, leading=20,
                           textColor=colors.HexColor("#0F6E56"))
    banner = ParagraphStyle("Banner", fontName="Helvetica-Bold", fontSize=22, leading=26,
                            textColor=colors.HexColor("#111827"))
    body = ParagraphStyle("Body", fontName="Helvetica", fontSize=9, leading=12)
    story = [Paragraph("Payment Reconciliation Report", title)]
    story.append(Paragraph(
        f"Run {run.run_id} · generated "
        f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} · {run.total} transactions · "
        f"{run.mode.upper()} MODE"
        + ("" if run.mode_note is None else f" ({run.mode_note})"),
        body))
    story.append(Paragraph(f"{run.matched} / {run.total} MATCHED ({run.match_rate * 100}%)", banner))
    v = run.validation
    if v is not None:
        verdict = "PASS" if v.passed else "FAIL"
        story.append(Paragraph(
            f"Ground-truth validation: {v.detected}/{v.total_breaks} breaks detected · "
            f"{v.fee_matches_confirmed}/{v.fee_total} fee-tolerance matches · "
            f"{len(v.false_positives)} false positives -> {verdict}",
            ParagraphStyle("Val", parent=body, fontName="Helvetica-Bold",
                           textColor=colors.HexColor("#0F6E56" if v.passed else "#993C1D"))))
    if run.llm_summary:
        story.append(Paragraph(run.llm_summary, body))
        story.append(Paragraph(
            "[AI-generated summary — verified by deterministic engine]",
            ParagraphStyle("Ai", parent=body, textColor=colors.HexColor("#6B7280"))))

    excs = _exceptions(run)
    story.append(Paragraph(f"Exceptions ({len(excs)})", ParagraphStyle(
        "H", parent=body, fontName="Helvetica-Bold", fontSize=11)))
    header = ["Txn ID", "Type", "Payout", "Bank", "Delta", "Drift"]
    rows = [header]
    for r in excs:
        explanation = f"<br/><i>AI: {r.llm_explanation}</i>" if r.llm_explanation else ""
        rows.append([
            r.txn_id,
            Paragraph(
                f"{r.exception_type.value if r.exception_type else ''}{explanation}",
                body),
            _fmt(r.payout.payout_amount if r.payout else None),
            _fmt(r.bank.credited_amount if r.bank else None),
            _fmt(r.amount_delta),
            f"{r.date_drift_days}d" if r.date_drift_days else "",
        ])
    t = Table(rows, colWidths=[70, 200, 70, 70, 60, 34])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t)
    story.append(Paragraph(_footer_line(run), ParagraphStyle(
        "F", parent=body, fontSize=7, textColor=colors.HexColor("#6B7280"))))
    doc.build(story)
    return buf.getvalue()
