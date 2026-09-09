"""FastAPI router for the reconciliation engine, mounted at /api/recon/.

Runs are cached in memory per session (demo scope - same as the review queue).
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from audit_v2.security.auth import principal
from reconcile.explainer import (
    answer_question,
    make_text_gateway,
    populate_explanations,
    summarize_forecast,
)
from reconcile.forecast import CashForecast, project_cash
from reconcile.ingest import load_bank, load_ledger, load_payouts
from reconcile.matcher import reconcile
from reconcile.models import ReconciliationRun
from reconcile.reporter import generate_docx_recon_report, generate_pdf_recon_report
from reconcile.validation import parse_ground_truth, validate_run

router = APIRouter(prefix="/api/recon", tags=["reconciliation"])

# Tenant state is persisted in the same transaction adapter as document audits.
def _runs() -> dict[str, ReconciliationRun]:
    from audit_v2.server import OPERATIONAL_STORE
    with OPERATIONAL_STORE.transaction(principal().tenant_id) as tx:
        state = tx.load() or {}
        return {k: ReconciliationRun.model_validate(v) for k, v in state.get("reconciliation_runs", {}).items()}


def _save_run(run: ReconciliationRun) -> None:
    from audit_v2.server import OPERATIONAL_STORE
    with OPERATIONAL_STORE.transaction(principal().tenant_id) as tx:
        state = tx.load() or {}
        state.setdefault("reconciliation_runs", {})[run.run_id] = run.model_dump(mode="json")
        tx.save(state, event="reconciliation_completed")



@router.post("/run")
async def run_reconciliation(
    payout_report: UploadFile = File(...),  # noqa: B008 - FastAPI idiom
    bank_statement: UploadFile = File(...),  # noqa: B008
    ledger: UploadFile = File(...),  # noqa: B008
    ground_truth: UploadFile | None = File(None),  # noqa: B008
) -> ReconciliationRun:
    try:
        payouts = load_payouts(payout_report.file)
        bank = load_bank(bank_statement.file)
        ledger_rows = load_ledger(ledger.file)
    except ValueError as err:
        raise HTTPException(422, str(err)) from None

    run = reconcile(payouts, bank, ledger_rows)

    # Demo vs live mode: only a schema-valid truth file enables validation.
    if ground_truth is not None and (ground_truth.filename or "").strip():
        raw = ground_truth.file.read()
        if raw.strip():
            try:
                truth = parse_ground_truth(raw)
                run.validation = validate_run(run, truth)
                run.mode = "demo"
            except ValueError as err:
                run.mode_note = f"Ground-truth file '{ground_truth.filename}' ignored: {err}"

    if os.getenv("NVIDIA_API_KEY"):

        # ponytail: fast-fail (20s, no retries) - explanations are cosmetic,
        # never worth blocking the verdict response; circuit-breaks after 1st failure
        run = populate_explanations(run, make_text_gateway(timeout=20, max_retries=0))
    _save_run(run)
    return run


@router.get("/results/{run_id}")
async def get_results(run_id: str) -> ReconciliationRun:
    run = _runs().get(run_id)
    if run is None:
        raise HTTPException(404, f"unknown run_id {run_id!r}")
    return run


@router.post("/report")
async def generate_report(run: ReconciliationRun, format: str = Query("docx")) -> Response:
    stored = _runs().get(run.run_id)
    if stored is None:
        raise HTTPException(404, "Reconciliation run not found")
    run = stored
    if format == "pdf":
        payload = generate_pdf_recon_report(run)
        media_type, ext = "application/pdf", "pdf"
    elif format == "docx":
        payload = generate_docx_recon_report(run)
        media_type = ("application/vnd.openxmlformats-officedocument."
                      "wordprocessingml.document")
        ext = "docx"
    else:
        raise HTTPException(422, "format must be docx or pdf")
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="recon-{run.run_id}.{ext}"'},
    )


@router.get("/results/{run_id}/forecast")
async def get_forecast(run_id: str) -> CashForecast:
    run = _runs().get(run_id)
    if run is None:
        raise HTTPException(404, f"unknown run_id {run_id!r}")
    forecast = project_cash(run)
    if os.getenv("NVIDIA_API_KEY"):

        forecast.llm_summary = summarize_forecast(
            forecast, make_text_gateway(timeout=20, max_retries=0))
    return forecast


class AskBody(BaseModel):
    txn_id: str
    question: str


@router.post("/results/{run_id}/ask")
async def ask_ai(run_id: str, body: AskBody) -> JSONResponse:
    run = _runs().get(run_id)
    if run is None:
        raise HTTPException(404, f"unknown run_id {run_id!r}")
    question = body.question.strip()
    if not question or len(question) > 500:
        raise HTTPException(422, "question must be 1-500 characters")
    if not os.getenv("NVIDIA_API_KEY"):
        raise HTTPException(503, "AI Q&A unavailable: NVIDIA_API_KEY not configured")

    # ponytail: fast-fail like the other recon LLM paths
    answer = answer_question(run, body.txn_id.strip(), question, make_text_gateway(timeout=30, max_retries=0))
    if answer is None:
        raise HTTPException(502, "AI Q&A failed - try again shortly")
    return JSONResponse({"txn_id": body.txn_id, "question": question, "answer": answer})


@router.get("/health")
async def health() -> JSONResponse:
    runs = _runs()
    last = max(runs.values(), key=lambda r: r.run_at, default=None)
    rates = [r.match_rate for r in runs.values()]
    avg_rate = (sum(rates, Decimal(0)) / len(rates)) if rates else None
    return JSONResponse({
        "match_rate": str(avg_rate) if avg_rate is not None else None,
        "last_run_id": last.run_id if last else None,
        "last_run_at": last.run_at.isoformat() if last else None,
        "total_runs_this_session": len(runs),
        "server_time": datetime.now(UTC).isoformat(),
    })


