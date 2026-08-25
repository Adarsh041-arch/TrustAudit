"""API tests: run the seeded batch through /api/recon/* with TestClient."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audit_v2.server import app

REPO_ROOT = Path(__file__).resolve().parents[2]
FILES = ("payout_report.csv", "bank_statement.csv", "ledger.csv")


@pytest.fixture(scope="module")
def batch_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("api_batch")
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "generate_recon_batch.py"),
         "--records", "100", "--seed", "42", "--out", str(out)],
        check=True,
    )
    return out


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)  # no network in tests
    with TestClient(app) as c:
        yield c


def _upload(client, batch_dir):
    with open(batch_dir / FILES[0], "rb") as f1, \
         open(batch_dir / FILES[1], "rb") as f2, \
         open(batch_dir / FILES[2], "rb") as f3:
        return client.post("/api/recon/run", files=[
            ("payout_report", ("payout_report.csv", f1)),
            ("bank_statement", ("bank_statement.csv", f2)),
            ("ledger", ("ledger.csv", f3)),
        ])


def test_run_returns_ground_truth_rate(client, batch_dir):
    resp = _upload(client, batch_dir)
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] == 94 and body["total"] == 100
    assert float(body["match_rate"]) == 0.94
    assert body["unmatched_bank_credits"] == 2


def test_results_roundtrip(client, batch_dir):
    run_id = _upload(client, batch_dir).json()["run_id"]
    resp = client.get(f"/api/recon/results/{run_id}")
    assert resp.status_code == 200
    types = {r["exception_type"] for r in resp.json()["results"] if r["exception_type"]}
    assert {"MISSING_BANK_CREDIT", "DUPLICATE_TXN_ID", "MISSING_LEDGER",
            "CURRENCY_MISMATCH"} <= types


def test_results_unknown_id_404(client):
    assert client.get("/api/recon/results/nope").status_code == 404


def test_bad_csv_is_422_not_crash(client, tmp_path):
    bad = tmp_path / "payout_report.csv"
    bad.write_text("txn_id,payout_amount,payout_date\nTXN1,not-a-number,2026-01-01\n")
    with open(bad, "rb") as f:
        resp = client.post("/api/recon/run", files=[
            ("payout_report", ("payout_report.csv", f)),
            ("bank_statement", ("b.csv", b"")),
            ("ledger", ("l.csv", b"")),
        ])
    assert resp.status_code == 422
    assert "not a valid amount" in resp.json()["detail"]


def test_report_pdf_and_docx(client, batch_dir):
    run = _upload(client, batch_dir).json()
    for fmt, magic in (("pdf", b"%PDF-"), ("docx", b"PK")):
        resp = client.post(f"/api/recon/report?format={fmt}", json=run)
        assert resp.status_code == 200 and resp.content[:5].startswith(magic)
        assert f'recon-{run["run_id"]}.{fmt}' in resp.headers["content-disposition"]
    assert client.post("/api/recon/report?format=xlsx", json=run).status_code == 422


def test_forecast_endpoint_shape(client, batch_dir):
    run_id = _upload(client, batch_dir).json()["run_id"]
    resp = client.get(f"/api/recon/results/{run_id}/forecast")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lag_source"] in {"derived", "fallback"}
    assert body["llm_summary"] is None  # no key in tests -> deterministic only
    lanes = {k: sum(float(b[k]) for b in body["buckets"]) for k in
             ("settled", "in_transit", "expected", "at_risk")}
    assert lanes["settled"] > 0          # most of the batch landed before as_of
    assert lanes["at_risk"] > 0          # 3 missing-bank-credit rows are overdue
    assert client.get("/api/recon/results/nope/forecast").status_code == 404


def _truth_bytes(batch_dir):
    return (batch_dir / "recon_ground_truth.json").read_bytes()


def test_run_live_mode_without_truth(client, batch_dir):
    body = _upload(client, batch_dir).json()
    assert body["mode"] == "live" and body["validation"] is None


def test_run_demo_mode_with_valid_truth(client, batch_dir):
    with open(batch_dir / FILES[0], "rb") as f1, \
         open(batch_dir / FILES[1], "rb") as f2, \
         open(batch_dir / FILES[2], "rb") as f3, \
         open(batch_dir / "recon_ground_truth.json", "rb") as f4:
        resp = client.post("/api/recon/run", files=[
            ("payout_report", ("payout_report.csv", f1)),
            ("bank_statement", ("bank_statement.csv", f2)),
            ("ledger", ("ledger.csv", f3)),
            ("ground_truth", ("recon_ground_truth.json", f4)),
        ])
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "demo"
    v = body["validation"]
    assert v["detected"] == 8 and v["total_breaks"] == 8 and v["passed"] is True


def test_malformed_truth_falls_back_to_live_with_note(client, batch_dir):
    with open(batch_dir / FILES[0], "rb") as f1, \
         open(batch_dir / FILES[1], "rb") as f2, \
         open(batch_dir / FILES[2], "rb") as f3:
        resp = client.post("/api/recon/run", files=[
            ("payout_report", ("payout_report.csv", f1)),
            ("bank_statement", ("bank_statement.csv", f2)),
            ("ledger", ("ledger.csv", f3)),
            ("ground_truth", ("ground_truth.json", b"not json at all")),
        ])
    assert resp.status_code == 200  # run must not crash
    body = resp.json()
    assert body["mode"] == "live"
    assert body["validation"] is None
    assert "ignored" in body["mode_note"] and "JSON" in body["mode_note"]


def test_ask_ai_gates_and_happy_path(client, batch_dir, monkeypatch):
    run_id = _upload(client, batch_dir).json()["run_id"]

    # no key -> 503
    resp = client.post(f"/api/recon/results/{run_id}/ask",
                       json={"txn_id": "TXN1001", "question": "why is this missing?"})
    assert resp.status_code == 503

    # key present + stubbed gateway -> answer flows through
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    class StubGW:
        def __init__(self, **kwargs):
            pass

        def extract(self, images, prompt, tenant_id, pii_classes=None):
            class R:
                content = "The payout was issued but never credited."
            return R()

    import reconcile.explainer as ex_mod
    monkeypatch.setattr(ex_mod, "NvidiaGateway", StubGW)

    ok = client.post(f"/api/recon/results/{run_id}/ask",
                     json={"txn_id": "TXN1001", "question": "why is this missing?"})
    assert ok.status_code == 200
    assert "never credited" in ok.json()["answer"]

    # validation gates
    assert client.post(f"/api/recon/results/{run_id}/ask",
                       json={"txn_id": "TXN1001", "question": ""}).status_code == 422
    assert client.post(f"/api/recon/results/{run_id}/ask",
                       json={"txn_id": "TXN1001", "question": "x" * 501}).status_code == 422
    assert client.post("/api/recon/results/nope/ask",
                       json={"txn_id": "T", "question": "q"}).status_code == 404


def test_health_reports_session_state(client, batch_dir):
    before = client.get("/api/recon/health").json()["total_runs_this_session"]
    _upload(client, batch_dir)
    health = client.get("/api/recon/health").json()
    assert health["total_runs_this_session"] == before + 1
    assert health["last_run_id"]
