# V1 Feature Parity for Audit V2 — Design

**Date:** 2026-08-02
**Status:** Approved (user: "begin")
**Goal:** Port the V1 dashboard/backend features still missing from V2 (`:8100` + `audit-frontend`), reimplemented on V2's deterministic data shapes. No V1→V2 imports (cardinal rule).

## Decisions (user-confirmed)

| Item | Decision |
|------|----------|
| ML prediction card | Rule-based only (score + severity counts → Compliant/Partially/Non-Compliant + probabilities). No sklearn, no fake training, no train console. |
| Reports | DOCX **and** PDF; python-docx + reportlab added to V2 deps. |
| Copilot chat | **Skip** (needs LLM text path; demo flourish). |
| ChromaDB RAG | **Skip** (dead code in V1; V2 has structured check catalog). |
| V1 heuristic cross-verification | **Skip** (superseded by V2 cluster-based 3-way match). |

## Backend

### New pure modules (audit_v2/analytics/)

- **`risk_scorer.py`** — `RiskScorer.score(findings: list[Finding]) -> tuple[float, str, str]`
  - `SEVERITY_WEIGHTS = {critical: 40.0, high: 25.0, medium: 10.0, low: 5.0}` (ported from V1).
  - `score = max(0, 100 − Σ weights)` over failed findings of the document.
  - Risk level: `< 70` or any critical → `High Risk`; `< 85` or any high → `Medium Risk`; else `Low Risk`.
  - Third element: natural-language risk explanation (counts per severity + remediation hint).
- **`risk_predictor.py`** — `predict(score, severity_counts) -> dict` — V1's rule-based fallback path, `mode: "Rule-based (V2)"`: score ≥85 & no crit/high → Compliant (90/8/2); ≥50 & no crit → Partially (15/70/15); else Non-Compliant (2/18/80). Returns `{prediction, probabilities, features_used, mode}`.
- **`aggregator.py`** — `aggregate_results(documents, findings) -> dict` with `kpis` (total_audited, compliance_rate, average_score, violations_detected, high_risk_count) and `charts` (risk_distribution pie, violation_frequency bar sorted desc, compliance_trends line, document_types) — V1 shapes, computed from V2 data. Plus `compute_prediction_interval(scores) -> {lower, upper}` (n=0 → 100/100; n=1 → ±12.5; else 95% CI 1.96·σ/√n).

Scores/percentages are floats (not monetary — Decimal rule untouched). All three modules are pure functions over domain models; unit-testable with zero infra.

### `audit_v2/extraction/preview.py`

- `generate_preview(extracted_document, max_size=180) -> str` — base64 JPEG page-1 thumbnail via existing `render_pages_to_jpeg` (vlm_extractor) + Pillow LANCZOS resize. `""` on failure (never breaks the upload).

### `audit_v2/reporting/report_builders.py`

- `generate_docx_report(payload: dict) -> bytes` — python-docx: title, timestamp, overall score + result, prediction interval, executive summary, per-document sections (score, risk level, ML prediction, failed findings table Rule/Severity/Evidence/Impact), header shading.
- `generate_pdf_report(payload: dict) -> bytes` — ReportLab: same content, severity color-coded table cells. Guarded import like V1 (`REPORTLAB_AVAILABLE`), no latent NameError (V1 bug not reproduced).
- Deps: `python-docx`, `reportlab` added to `audit_v2[dev]` extras / requirements.

### `backend/server_v2.py` changes

- Upload response: each document gains `score`, `risk_level`, `risk_explanation`, `ml_prediction`, `confidence_score`, `human_review_recommended`, `preview_base64`. Batch gains `analytics` (kpis + charts) and `prediction_interval`.
- `POST /api/v2/audit/report?format=docx|pdf` — body `{documents: [...], findings: [...], audit_title?}` (the data the frontend already holds; stateless). Returns binary with `Content-Disposition` attachment.
- `GET /api/v2/audit/eval` — 8-metric grid (`accuracy`, `precision`, `recall`, `f1_score`, `false_positive_rate`, `false_negative_rate`, `average_latency_seconds`, `average_confidence_score`) mapped from the real golden-set baselines `evaluation/baselines/v2.json` (not mock data). If baselines lack a metric, `null` with the gate table included.

## Frontend (audit-frontend/src)

- **Tabs** become: Upload, Dashboard, 3-Way Match, Findings, Review, Audit Log, Reports, Settings.
- **Dashboard tab** (`sections/DashboardSection.tsx`): KPI cards (reuse `MetricCard`/`SummaryMetrics`), recharts PieChart (risk distribution), BarChart (violation frequency), LineChart (compliance trends) — computed client-side from accumulated `allDocuments`/`allFindings`.
- **Document inspector** on Upload tab: sidebar of documents + detail panel reusing `DocumentCard`/`FailedRulesList`/`ScoreDisplay`/`StatusBadge` (currently orphaned V1 leftovers), re-shaped to V2 fields (`finding.check_id`), plus ML prediction card and risk explanation. Selected document state in App.
- **Reports tab** (`sections/ReportSection.tsx` — existing orphaned name, rebuilt): DOCX/PDF download buttons → `downloadReportV2(format, documents, findings)`.
- **Settings tab** (`sections/SettingsSection.tsx`): confidence-threshold slider (50–95, localStorage) filtering the "human review recommended" badge in the inspector; eval metrics grid from `GET /api/v2/audit/eval`.
- **Processing animation**: existing orphaned `ProcessingAnimation.tsx` shown while `uploading`.
- **api_v2.ts**: types for `Score/risk/ml/analytics/report/eval` payloads + `downloadReportV2` + `fetchEvalV2`.

## Data flow

Upload → server classifies/extracts → pure modules compute derived fields → response carries per-doc report + batch analytics → App accumulates into `allDocuments`/`allFindings` → Dashboard/Inspector/Reports read from accumulated state. Reports call the stateless report endpoint with the accumulated payload. Eval is a read-only endpoint.

## Testing

- pytest: new unit tests for `risk_scorer`, `risk_predictor`, `aggregator` (incl. edge cases: no findings, empty batch, n=0/1 prediction interval), `preview` (no-PDF path), `report_builders` (DOCX/PDF smoke: returns non-empty bytes), eval endpoint shape, expanded `tests/test_server_v2.py` (derived fields present in upload response).
- `ruff check`, `tsc --noEmit`, `npm run build` clean.
- tracker.md + shortcomings.md updated (incl. new items: report deps, client-side threshold is cosmetic-only).
