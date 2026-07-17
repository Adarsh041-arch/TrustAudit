# TrustAudit 🛡️

TrustAudit is an AI-powered compliance and business document audit system. It automates the verification of vendor invoices, purchase orders, receipts, delivery challans, contracts, and certificates using Vision Language Models (VLM) powered by Google Gemini and a robust workflow engine orchestrated via LangGraph.

---

## 🚀 Key Features

- **Multi-Document Support:** Audit PDF invoices, receipt images, purchase orders, contracts, and certificates.
- **Rule-Based Compliance:** Runs a structured, customizable audit checklist defined in `checklist.md` (e.g., mathematical accuracy, authorization signatures, tax registration, date validity, currency consistency).
- **FastAPI Backend:** Offers API endpoints for trigger audits and downloading professional `.docx` formatted compliance reports.
- **Modern React Dashboard:** An elegant Vite/TypeScript frontend client to visualize compliance results, highlight failure severity, and export Word reports.
- **Agentic Workflow:** Employs LangGraph to coordinate the VLM analysis, document rendering, validation logic, and report structuring.

---

## 📁 Repository Structure

```
├── app/                     # LangGraph-based Audit Agent Core
│   ├── graph.py             # LangGraph workflow definition
│   ├── state.py             # State schema for the agent
│   ├── vlm.py               # VLM (Gemini) vision logic & prompt templates
│   └── schemas.py           # Internal Agent Pydantic schemas
├── backend/                 # FastAPI Web Server
│   ├── server.py            # API routes and CORS configuration
│   ├── runner.py            # API-to-Agent execution wrapper
│   └── report_generator.py  # Generates downloadable MS Word (.docx) reports
├── audit-frontend/          # React + Vite + TypeScript Frontend Dashboard
├── checklist.md             # The standard audit checklist and severity rules
├── main.py                  # CLI entry point to test the LangGraph workflow locally
├── requirements.txt         # Backend Python dependencies
└── .env                     # Environment configurations (API keys)
```

---

## 🛠️ Getting Started

### Prerequisites

- **Python:** 3.10+
- **Node.js:** 18+
- **Google Gemini API Key** (Set as `GOOGLE_API_KEY`)

---

### Backend Setup

1. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source venv/bin/activate
   ```

2. **Install Python Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create a `.env` file in the root directory (or use the existing one) and populate it with:
   ```env
   GOOGLE_API_KEY=your_gemini_api_key_here
   ```

4. **Run the CLI Audit (Local Testing):**
   ```bash
   python main.py
   ```

5. **Start the FastAPI Server:**
   ```bash
   uvicorn backend.server:app --reload --port 8000
   ```
   The API will be available at `http://localhost:8000`. You can inspect interactive docs at `http://localhost:8000/docs`.

---

### Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd audit-frontend
   ```

2. **Install Node Packages:**
   ```bash
   npm install
   ```

3. **Run the Development Server:**
   ```bash
   npm run dev
   ```
   Open `http://localhost:5173` in your browser to view the application.

---

## 📋 Audit Rules Configuration

The audit criteria are managed through [checklist.md](file:///c:/Users/adars/OneDrive/Desktop/AUDIT_AGENT/checklist.md) at the root of the workspace. You can edit this file to add, modify, or disable specific compliance rules (e.g. changing mandatory requirements or adjusting severity levels from `low` to `critical`).

---

## 📄 License

This project is proprietary and confidential. All rights reserved.
