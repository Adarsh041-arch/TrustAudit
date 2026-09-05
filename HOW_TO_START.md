# How to Start TrustAudit V1 and V2 Services

This guide provides step-by-step instructions for running **V1 (TrustAudit Legacy)** and **V2 (Audit V2 Architecture)** services.

---

## 🏛️ System Overview

| Parameter | V1 (TrustAudit) | V2 (Audit V2) |
|---|---|---|
| **Directory Scope** | `app/`, `backend/`, `audit-frontend/` | `audit_v2/`, `contracts/`, `evaluation/`, `reconcile/` |
| **Status** | Frozen (bugfixes only) | Active Development |
| **Backend Port** | `:8000` | `:8100` |
| **Frontend Port** | `:5173` | `:5173` (includes V2 Dashboard & Reconciliation tabs) |
| **Workflow Engine** | LangGraph State Machine (`app/graph.py`) | Temporal Workflow Engine (`audit_v2/orchestration`) |
| **Data & Storage** | Vector RAG (ChromaDB), In-memory | Postgres 16 (`:5432`), MinIO (`:9000`), Temporal (`:7233`) |
| **OCR / VLM Model** | Gemini / LiteRT-LM / NVIDIA | Qwen2.5-VL through Ollama (`:11434`) by default; GLM-OCR remains optional |

---

## 🚀 How to Start V1 (Legacy System)

### Prerequisites
1. Virtual environment activated:
   ```powershell
   .\venv\Scripts\activate
   ```
2. Python dependencies installed (`pip install -r requirements.txt`).
3. Valid `.env` configuration (e.g. `GEMINI_API_KEY` or `NVIDIA_API_KEY`).

### Step 1: Start V1 API Server (Port 8000)
Run the FastAPI backend server on port 8000:
```powershell
uvicorn backend.server:app --reload --port 8000
```
- **Swagger Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Check:** `http://127.0.0.1:8000/api/health`

### Step 2: Start Frontend Dashboard
In a separate terminal window:
```powershell
cd audit-frontend
npm run dev
```
Open **[http://localhost:5173](http://localhost:5173)** in your browser.

### Step 3: Run V1 CLI Pipeline (Optional)
To run a batch audit on `sample_docs/` directly via CLI:
```powershell
python main.py
```

---

## ⚡ How to Start V2 (Audit V2 System)

### Step 1: Start Infrastructure Containers (Postgres + MinIO + Temporal)
Use Docker Compose to launch the required background services:
```powershell
docker-compose up -d
# or via Makefile
make dev
```
- **Postgres DB:** `localhost:5432` (`audit_v2` database)
- **MinIO Storage:** `localhost:9000` (Console UI at `http://localhost:9001`)
- **Temporal Server:** `localhost:7233` (Web UI at `http://localhost:8233`)

To verify container health:
```powershell
docker-compose ps
```

### Step 2: Start Qwen2.5-VL through Ollama

Start Ollama, then confirm the model is installed and available:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" list
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" run qwen2.5vl:3b
```

The V2 API uses `http://127.0.0.1:11434` and `qwen2.5vl:3b` when
`V2_VISION_BACKEND=qwen_ollama` is set in `.env`. You may close the interactive
`ollama run` prompt after the model loads; the Ollama background service stays
available. V2 keeps the source PDF render at 200 DPI, then bounds only the copy
sent to Qwen to a 1200-pixel longest edge so its 4096-token context retains
enough output capacity. Do not raise `QWEN_VL_CONTEXT_LENGTH` above 4096 on the
6 GB RTX 4050 without retesting GPU stability.

To use GLM-OCR instead, set `V2_VISION_BACKEND=glm_ocr` and start llama.cpp:

```powershell
cd C:\llama-cpp
.\llama-server.exe `
  -m ".\models\GLM-OCR-Q8_0.gguf" `
  --mmproj ".\models\mmproj-GLM-OCR-Q8_0.gguf" `
  --host 127.0.0.1 `
  --port 8080 `
  -c 8192 -np 1 -b 128 -ub 64 -ngl 20 `
  --no-mmproj-offload --flash-attn on --fit on
```
- **Qwen/Ollama endpoint:** `http://127.0.0.1:11434`
- **Optional GLM endpoint:** `http://127.0.0.1:8080/v1`

### Step 3: Start V2 Temporal Worker
In a terminal with `venv` activated:
```powershell
python -m audit_v2.orchestration.worker
```
*(The worker connects to Temporal on `:7233` and listens on `audit-v2-task-queue`)*.

### Step 4: Start V2 API Server (Port 8100)
In a separate terminal with `venv` activated:
```powershell
python -m uvicorn audit_v2.server:app --host 127.0.0.1 --port 8100
```
- **V2 Swagger Docs:** [http://127.0.0.1:8100/docs](http://127.0.0.1:8100/docs)
- **V2 Health Check:** [http://127.0.0.1:8100/api/v2/health](http://127.0.0.1:8100/api/v2/health)

### Step 5: Start Frontend Dashboard
In a separate terminal:
```powershell
cd audit-frontend
npm run dev -- --host 127.0.0.1
```
Open **[http://127.0.0.1:5173](http://127.0.0.1:5173)**. V2 audit workspace and Reconciliation tabs interact with backend port `:8100`.

---

## 🧪 Verification & Development Commands (V2)

```powershell
# Run unit & integration test suite (Postgres required for full suite)
pytest --cov=audit_v2 --cov-report=term-missing -v

# Run linting & type checks
ruff check audit_v2/
mypy --strict audit_v2/domain/

# Validate JSON contracts & import boundaries
make validate-schemas
make import-lint

# Full pre-flight check
make all
```

---

## 🛠️ Summary of Terminal Commands Quick Reference

```powershell
# Terminal 1: Infrastructure
docker-compose up -d

# Terminal 2: Qwen local vision (Ollama normally runs in the background)
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" run qwen2.5vl:3b

# Terminal 3: V2 Temporal Worker
python -m audit_v2.orchestration.worker

# Terminal 4: V2 API Server (:8100) OR V1 API Server (:8000)
python -m uvicorn audit_v2.server:app --host 127.0.0.1 --port 8100
# OR for V1: uvicorn backend.server:app --reload --port 8000

# Terminal 5: Frontend
cd audit-frontend; npm run dev
```
