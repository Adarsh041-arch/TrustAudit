# V1 Legacy System Analysis — What It Did & What the Frontend Showed

## Overview

The V1 system was a **folder-based audit pipeline** on port `:8000`. The user pointed it at a local folder of PDFs/images, the backend sent each document to **Gemini VLM** with the full checklist, and the frontend rendered a rich 7-tab dashboard with charts, copilot chat, ML predictions, downloadable reports, and cross-document verification.

---

## 1. Backend Pipeline ([server.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/backend/server.py) → [runner.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/backend/runner.py) → [explainable_audit.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/audit_engine/explainable_audit.py))

### Input
User provides a **local folder path** (e.g. `C:\Users\...\sample_docs`) via `POST /api/audit`. The runner scans for `.pdf`, `.png`, `.jpg`, `.tiff`, `.bmp`, `.webp` files.

### Per-Document Processing (6-Step Pipeline)

| Step | Module | What It Does |
|------|--------|-------------|
| 1. **Classify** | [classifier.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/document_classifier/classifier.py) | Infers doc type from filename patterns (`INV` → invoice, `PO` → purchase_order, etc.) |
| 2. **VLM Summarize** | [app/vlm.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/app/vlm.py) | Sends document images to **Gemini 2.0 Flash** via `google-genai`, gets `DocumentSummary` (summary text + metadata dict) |
| 3. **RAG Retrieval** | [retriever.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/rag_engine/retriever.py) | Indexes [checklist.md](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/checklist.md) rules into **ChromaDB** vector store, retrieves top-4 relevant policies for each doc |
| 4. **VLM Audit** | [explainable_audit.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/audit_engine/explainable_audit.py#L67-L121) | Sends document images + all checklist rules + RAG context to Gemini with a structured JSON prompt. Model returns `{passed_all_mandatory, failed_rules[], confidence_score, remarks}` |
| 5. **Risk Scoring** | [risk_scorer.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/risk_engine/risk_scorer.py) | Deterministic score: `100 - Σ(severity_weights)`. Critical=40pts, High=25pts, Medium=10pts, Low=5pts. Classifies as Low/Medium/High Risk |
| 6. **ML Prediction** | [risk_classifier.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/ml_models/risk_classifier.py) | **Random Forest classifier** (scikit-learn) trained on synthetic data. Features: doc type flags, page count, score, per-rule fail flags. Predicts `Compliant`/`Partially Compliant`/`Non-Compliant` with class probabilities |

### Post-Document Processing

| Step | Module | What It Does |
|------|--------|-------------|
| 7. **Cross-Verification** | [cross_verification.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/audit_engine/cross_verification.py) | Three-Way Match between Invoice, PO, Receipt: compares amounts ($), vendor names (fuzzy token overlap), date chronology, and signature approvals. Returns `{is_consistent, status, discrepancies[], matched_amount, mismatched_amount}` |
| 8. **Analytics** | [aggregator.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/analytics/aggregator.py) | Computes KPIs (compliance rate, avg score, violation count, high-risk count) and chart-ready data arrays (risk distribution pie, violation frequency bar, compliance trends line, document type breakdown) |
| 9. **Preview** | [runner.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/backend/runner.py#L28-L48) | Generates 180×180px JPEG thumbnails of page-1 (base64-encoded) for each document |
| 10. **Prediction Interval** | [runner.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/backend/runner.py#L50-L64) | 95% confidence interval on the overall score using `1.96 × σ/√n` |

### Final Response Shape (`EnhancedAuditResponse`)
```
{
  report: {
    audit_title, documents_processed, documents_passed, documents_failed,
    overall_score, overall_result, summary,
    document_results: [{
      document_name, document_type, passed, score,
      risk_level, risk_explanation,
      failed_rules: [{ rule_id, rule_title, finding, evidence, impact, recommendation, severity, page_number }],
      ml_prediction: { prediction, probabilities: {compliant, partially_compliant, non_compliant}, features_used, mode },
      confidence_score, human_review_recommended, remarks,
      preview_base64, page_count, summary_text, metadata
    }]
  },
  prediction_interval: { lower, upper },
  elapsed_seconds,
  cross_verification: { is_consistent, status, discrepancies[], matched_amount, mismatched_amount, reconciliation_summary },
  analytics: { kpis: {...}, charts: { risk_distribution, violation_frequency, compliance_trends, document_types } }
}
```

---

## 2. Frontend Tabs — What Each Rendered

The V1 frontend had **7 navigation tabs** in the header bar:

### Tab 1: Upload & Run
- Text input for **local folder path**
- "Run Audit" button (invokes `POST /api/audit`)
- Processing animation (orbiting magnifying glass SVG with scan line)
- Error display if audit fails

### Tab 2: Dashboard (post-audit)
- **KPI Cards** (5 metrics in a row): Total Audited, Compliance Rate, Average Score, Violations Detected, High Risk Count
- **Recharts PieChart**: Risk Distribution (Low/Medium/High Risk colored pie slices)
- **Recharts BarChart**: Top Violation Frequency (rule IDs on X-axis, count on Y-axis)
- **Recharts LineChart**: Compliance Score Trends across documents
- **Cross-Verification Summary Card**: Status badge (Compliant/Partially/Non-Compliant), matched/mismatched amounts, reconciliation summary text, discrepancy list with severity dots

### Tab 3: Audit Results (detailed document inspector)
- **Document Selector Sidebar**: Clickable list of document names with Pass/Fail badges
- **Selected Document Detail Panel**:
  - **Thumbnail Preview**: 120×120px base64 image of page 1
  - **Document Name + Score** with `StatusBadge` (Pass/Fail)
  - **ScoreDisplay**: Large score `XX.X%` with prediction interval range below
  - **Risk Level + Explanation**: Text block with risk classification
  - **Failed Rules Accordion** (`FailedRulesList`): Sorted by severity (critical first), expandable cards showing:
    - Severity dot (coral for critical/high, gray for medium/low)
    - `rule_id: rule_title`
    - Expanded: description, evidence (coral background with page number), impact, recommendation
  - **ML Prediction Card**: prediction label, probability bar (compliant vs partially vs non-compliant), mode indicator
  - **Confidence Score** with human review recommendation badge
  - **Remarks**: VLM-generated summary paragraph
  - **Summary Text + Metadata table**

### Tab 4: Policy Center
- Rendered the checklist rules from `checklist.md` as browseable cards
- RAG knowledge base viewer

### Tab 5: Analytics
- Full-width **Recharts dashboard**:
  - Risk Distribution Pie Chart
  - Violation Frequency Bar Chart  
  - Compliance Trend Line Chart
  - Document Type Distribution
- Interactive tooltips and legends

### Tab 6: Reports
- **Download DOCX** card with description and button → calls `POST /api/audit/download?format=docx`
- **Download PDF** card with description and button → calls `POST /api/audit/download?format=pdf`
- Report includes executive summary, per-document tables, failed rules, and RAG citations
- Generated by [report_builders.py](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/reporting/report_builders.py) using python-docx and reportlab

### Tab 7: Settings & ML
- **Confidence Threshold Slider**: `<input type="range" min="50" max="95">` controlling when human review is flagged
- **ML Random Forest Training Console**: "Trigger Classifier Training Pipeline" button → calls `POST /api/ml/train`
- **Evaluation Framework Benchmark**: 8-metric grid from `GET /api/eval`:
  - Platform Accuracy, Precision, Recall, F1 Score
  - False Positive Rate, False Negative Rate
  - Average Latency per file, Average Inference Certainty

### Copilot Chat (floating panel on Results tab)
- Chat input with send button
- Conversation history (user/assistant messages)
- Calls `POST /api/copilot/chat` with current audit results + cross-verification context
- Gemini answers questions about findings grounded in the actual audit data

### Footer
> *TrustAudit platform built via Google Gemini VLM & LangGraph compliance routing.*

---

## 3. V1 Features vs Current V2 Frontend — Gap Analysis

| V1 Feature | Current V2 Status | Notes |
|------------|-------------------|-------|
| Folder path text input | ✅ Replaced with file upload (better) | Multi-file batch upload |
| Processing animation | ❌ **Missing** | V1 had orbiting magnifying glass SVG |
| KPI Dashboard cards | ❌ **Missing** | Compliance rate, avg score, violations count, high-risk count |
| Recharts PieChart (risk distribution) | ❌ **Missing** | Needs recharts or equivalent |
| Recharts BarChart (violation frequency) | ❌ **Missing** | Top violated rules |
| Recharts LineChart (compliance trends) | ❌ **Missing** | Score trend across documents |
| Document selector sidebar | ❌ **Missing** | Click-to-select per-document inspector |
| Thumbnail preview (base64) | ❌ **Missing** | 120px page-1 thumbnail |
| Score display with prediction interval | ❌ **Missing** | `XX.X%` with `lower – upper` range |
| Per-document failed rules accordion | ❌ **Missing** | V1 `FailedRulesList` with severity dots, expandable evidence |
| ML prediction card (Random Forest) | ❌ **Missing** | Probability bars: compliant/partial/non-compliant |
| Confidence score + human review badge | ❌ **Missing** | Aggregated VLM + ML confidence |
| Cross-verification summary card | ✅ Partial | V2 has 3-Way Match Topology tab but different data shape |
| Copilot chat panel | ❌ **Missing** | Gemini-powered Q&A about findings |
| Reports download (DOCX/PDF) | ❌ **Missing** | Export buttons with report_builders |
| Settings slider (confidence threshold) | ❌ **Missing** | Configurable audit parameters |
| ML training console | ❌ **Missing** | Random Forest training trigger |
| Evaluation framework benchmark | ❌ **Missing** | Accuracy/Precision/Recall/F1 metrics grid |
| Risk level + explanation text | ❌ **Missing** | Per-document risk explanation paragraph |
| Summary text + metadata table | ❌ **Missing** | VLM-generated document summary |
| Dark/Light mode toggle | ✅ Present | Working in V2 |
| Hash-chained audit log viewer | ✅ **New in V2** | Not in V1 |
| Human review queue with actions | ✅ **New in V2** | Not in V1 |
| Decision fingerprints | ✅ **New in V2** | Not in V1 |
| Batch multi-document upload | ✅ **New in V2** | V1 was folder-based only |

---

## 4. Key Architectural Difference

| Aspect | V1 | V2 |
|--------|----|----|
| **Input** | Local folder path string | File upload (multipart) |
| **Audit engine** | Gemini VLM does everything (arithmetic, rules, extraction) | Pure Python validators + VLM only for extraction fallback |
| **Math** | LLM does arithmetic (B1 defect) | `Decimal` arithmetic in Python validators |
| **Money type** | `float` (B3 defect) | `Decimal` in code, integer minor units in DB |
| **Cross-doc checks** | Heuristic regex on summary text | Structural cluster-based 3-way match with line-item correlation |
| **ML** | Random Forest on synthetic features | Not yet integrated in V2 |
| **Reports** | python-docx / reportlab generators | Not yet in V2 |
| **Governance** | None | Hash-chained audit log, RBAC permission matrix |
| **Port** | `:8000` | `:8100` |

