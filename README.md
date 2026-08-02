# TrustAudit 🛡️ — Enterprise Compliance Intelligence Platform

TrustAudit is a multi-model AI compliance and document audit platform. It automates the verification of vendor invoices, purchase orders, receipts, delivery challans, contracts, and certificates using Vision Language Models (VLM), vector-based Policy RAG, Random Forest ML risk classification, and deterministic Three-Way Match cross-verification.

---

## 🚀 Architectural Pipeline & Pipeline Stages

TrustAudit operates an end-to-end 6-stage compliance auditing pipeline:

```
[ Local Document Batch ] ──► 1. VLM Extraction & RAG Retrieval ──► 2. Rule Risk Scoring & ML Classification
                                                                              │
[ Recharts & Export ]    ◄── 5. Report Builders & Copilot      ◄── 4. Analytics & 95% CI ◄── 3. Three-Way Match
```

### Stage 1: Document Classification, VLM Summarization & RAG Policy Retrieval
- **Document Classifier**: Identifies document types (`invoice`, `purchase_order`, `receipt`, `contract`, `certificate`).
- **Multimodal VLM**: Extracts structured summaries, metadata key fields, and 180px page-1 thumbnail previews.
- **ChromaDB Policy RAG**: Indexes [checklist.md](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/checklist.md) policies into ChromaDB (using `text-embedding-004`), retrieving top-4 relevant policies for each document.

### Stage 2: Explainable Audit & Risk Scoring
- **Deterministic Risk Score**: Calculates score bounded between 0.0% and 100.0%:
  $$\text{Score} = \max\left(0, 100 - \sum \text{Severity Weights}\right)$$
  *(Critical = 40 pts, High = 25 pts, Medium = 10 pts, Low = 5 pts)*.
- **Random Forest ML Classification**: Uses a 13-dimensional feature vector (`[doc_type_flags, page_count, score, R001..R005_fail_counts]`) to predict `Compliant`, `Partially Compliant`, or `Non-Compliant` with class probability distributions.
- **Aggregated Confidence & Human Review**:
  $$\text{Final Confidence} = 0.7 \times \text{VLM Confidence} + 0.3 \times \max(\text{ML Probabilities})$$
  *(Flags `human_review_recommended` if Confidence $< 75\%$ or Risk Level is High Risk)*.

### Stage 3: Three-Way Match Cross-Verification
Performs multi-document transaction reconciliation across 4 verification checks:
1. **Amount Match**: Reconciles $\text{Invoice Total}$ vs $\text{PO Total}$ ($|\text{Diff}| \le \$0.01$).
2. **Vendor Identity Match**: Token-set overlap verification on vendor names.
3. **Chronology Sequence**: Verifies $\text{PO Date} \le \text{Invoice Date} \le \text{Receipt Date}$.
4. **Approval Signatures**: Verifies signature rules (`R004`) across matching transaction files.

### Stage 4: Analytics Aggregator & 95% Prediction Interval
- **KPI Metrics**: Calculates total audited, overall compliance rate, average score, total violations, and high-risk document count.
- **95% Statistical Prediction Interval**:
  $$\text{Margin of Error } (E) = 1.96 \times \frac{s}{\sqrt{N}}$$
  $$\text{Prediction Interval} = [\max(0.0, \bar{S} - E), \min(100.0, \bar{S} + E)]$$
- **Recharts Datasets**: Formats Risk Distribution (Pie Chart), Violation Frequency (Bar Chart), Compliance Trends (Line Chart), and Document Type Breakdowns.

### Stage 5: Reports & Auditor Copilot
- **DOCX & PDF Report Builders**: Generates downloadable Word (`.docx`) and PDF (`.pdf`) executive reports with color-coded violation tables, severity badges, and RAG citations.
- **Auditor Copilot Chat**: Grounded conversational AI assistant powered by Gemini/NVIDIA VLM to answer user queries about audit findings and reconciliation discrepancies.

---

## 📋 Calibrated Audit Policy Checklist

Policy rules are defined in [checklist.md](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/checklist.md) with calibrated severities:

| Rule ID & Title | Severity | Mandatory? | Scope & Focus |
|---|---|---|---|
| **R003: Mathematical Accuracy** | `critical` | **`true`** | Core financial arithmetic (Line totals $Qty \times Price$, subtotal, taxes, grand total). |
| **R005: Date Validity & Future Dates** | `high` | **`true`** | Chronological integrity (Future dates, expired certificates). |
| **R006: Currency & Amount Consistency** | `high` | **`true`** | Uniform currency symbols and amount figure reconciliation. |
| **R001: Document Legibility** | `medium` | `false` | Readable text and headers. |
| **R002: Mandatory Fields Present** | `medium` | `false` | Document-dependent field check (varies by document type). |
| **R004: Authorization & Signatures** | `medium` | `false` | Signatures & stamps (omitted on computer tax invoices = medium severity). |
| **R007: Vendor / Customer Information** | `medium` | `false` | Legal names, addresses, and registry IDs. |
| **R008, R009, R010, R011, R012** | `medium` / `low` | `false` | Document number uniqueness, payment terms, tax breakdowns, descriptions, attachments. |

---

## 🏛️ System Architecture — V1 vs V2 Coexistence

The repository maintains a strict two-system architecture per `AGENTS.md` and `.importlinter`:

| System | Port | Directory | Status | Stack |
|---|---|---|---|---|
| **V1 (TrustAudit)** | **`:8000`** | `app/` + `backend/` + `audit-frontend/` | Frozen (Feature Complete) | FastAPI, Gemini/NVIDIA VLM, LangGraph, React |
| **V2 (Audit V2)** | **`:8100`** | `audit_v2/` + `contracts/` + `evaluation/` | Active Development | Temporal, Postgres, MinIO, Pure Python Validators |

---

## 📁 Repository Structure

```
├── app/                     # V1 LangGraph Agent & VLM Logic
│   ├── vlm.py               # Multimodal VLM client (Gemini / NVIDIA Llama-3.2-Vision)
│   └── explainable_audit.py # Explainable audit engine
├── backend/                 # V1 FastAPI Backend Server (Port :8000)
│   ├── server.py            # API routes (/api/audit, /api/audit/download, /api/copilot/chat)
│   └── runner.py            # Full 6-stage audit pipeline execution engine
├── audit_v2/                # V2 Audit Engine Architecture (Port :8100)
│   ├── server.py            # V2 FastAPI Server
│   ├── domain/              # Pure Python validators & Decimal arithmetic
│   ├── analytics/           # Risk scoring, ML predictor, and aggregator
│   └── reporting/           # Report builders (DOCX & PDF)
├── audit-frontend/          # React + Vite + TypeScript Dashboard (Port :5173)
├── policy_store/            # RAG vector store policy manager
├── rag_engine/              # ChromaDB policy retriever
├── risk_engine/             # Risk scoring & weighted deduction calculations
├── ml_models/               # Random Forest risk classifier
├── copilot/                 # Auditor Copilot chatbot engine
├── reporting/               # DOCX & PDF report generation builders
└── checklist.md             # Calibrated audit checklist definition
```

---

## 🛠️ Getting Started

### 1. Backend Setup

```powershell
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Start V1 Backend Server (Port 8000)
uvicorn backend.server:app --reload --port 8000
```

### 2. Frontend Setup

```powershell
cd audit-frontend
npm install
npm run dev
```

Open **`http://localhost:5173`** in your browser to access the TrustAudit platform.
