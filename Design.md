# Design.md — TrustAudit UI (V1 Frontend)

**Stack:** React 19, TypeScript 6, Vite 8, Tailwind CSS v4, oxlint (no ESLint).  
**Entry:** `audit-frontend/src/main.tsx` → `App.tsx`.  
**Build:** `npm run build` (tsc -b && vite build).  
**Dev:** `npm run dev` → `localhost:5173`.

---

## Color system (index.css)

The design uses a semantic 4-color palette, not utility colors:

| Token | Role | Light | Dark |
|-------|------|-------|------|
| `--color-ink` | Primary text | `#2C2C2A` | `#2C2C2A` (unchanged) |
| `--color-muted` | Secondary text | `#5F5E5A` | `#5F5E5A` |
| `--color-teal-600` | AI/model outputs (pass, score) | `#0F6E56` |
| `--color-coral-600` | Risk, anomaly, failure | `#993C1D` |
| `--color-blue-600` | Human actions (download button) | `#185FA5` |
| `--color-surface-1` | Page background | `#F5F5F4` | `#1A1A18` |
| `--color-surface-2` | Card background | `#FFFFFF` | `#242422` |
| `--color-border` | Hairlines, strokes | `#d4d4d0` | `#3D3C38` |

Dark mode is toggled via `.dark` class on `<html>`, stored in `localStorage` key `trustaudit-dark`.

---

## Layout

```
┌─────────────────────────────────────────────────────┐
│  Header: "TrustAudit" / {audit_title}    [☾ Dark]  │
├─────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────┐│
│  │  Folder path  [_________________________] [Run] ││
│  │                               [Download .docx]  ││
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  [ProcessingAnimation]  ← while loading              │
│                                                     │
│  [Audit Summary card]   ← results section            │
│    Score: 72.3% | X docs processed                   │
│    Summary text                                      │
│                                                     │
│  Summary                                             │
│  ┌──────┬──────┬──────┬──────┐                      │
│  │ Docs │ Pass │ Fail │ Score│   ← MetricCard grid  │
│  └──────┴──────┴──────┴──────┘                      │
│  ───────────────────────────────────── hairline      │
│  Documents                                           │
│  ┌─────────────────────────────────────────────────┐│
│  │ [img] Doc name                    [Pass/Fail]   ││
│  │       72.3% (60.1% – 84.5%)                    ││
│  │       ┌ Failed rules dropdowns ──────────────┐  ││
│  │       │ R003: Math accuracy [+]               │  ││
│  │       │ R010: Tax breakdown [+]               │  ││
│  │       └───────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────┘│
│  ...more DocumentCards...                            │
└─────────────────────────────────────────────────────┘
```

Max content width: `960px`, centered (`max-w-[960px] mx-auto`).

---

## Component tree

```
App
├── Header
│     dark toggle (☀ Light / ☾ Dark)
│     breadcrumb: "TrustAudit / {audit_title}"
├── FlatCard (folder input row)
│     input[type=text] + "Run audit" button (teal outline)
│     "Download .docx" button (blue outline, shown only after results)
├── ProcessingAnimation (shown during loading)
│     SVG magnifying glass orbit + scanning line + "Auditing documents…"
├── ReportSection (FlatCard)
│     overall StatusBadge + ScoreDisplay (large) + doc counts
│     summary prose
├── SummaryMetrics
│     2×2 grid of MetricCard: processed / passed / failed / score
├── DocumentList
│     └── DocumentCard (FlatCard)
│           preview_base64 image (120×120, object-cover)
│           document name (truncated), ScoreDisplay, StatusBadge
│           └── FailedRulesList (accordion)
│                 sorted by severity (critical → low)
│                 SeverityDot (colored circle)
│                 expanded: description + evidence + page number
│           remarks (italic, muted)
```

---

## Component reference

| Component | Props | Notes |
|-----------|-------|-------|
| `Header` | `dark`, `onToggleDark`, `title?` | Fixed top bar, border-bottom |
| `FlatCard` | `children`, `className?` | White card, rounded-xl, 0.5px border |
| `ProcessingAnimation` | `message?` | SVG orbit + scan line, 78 LoC pure CSS animation |
| `ScoreDisplay` | `score`, `interval`, `size?` | Shows `XX.X%` with prediction range below |
| `StatusBadge` | `passed`, `label?` | Teal bg for pass, coral bg for fail |
| `MetricCard` | `label`, `value`, `color?` | 4-card grid, 24px value text |
| `FailedRulesList` | `rules: FailedChecklistItem[]` | Accordion, severity-sorted, SeverityDot helper |
| `DocumentCard` | `doc`, `interval` | Preview thumbnail + score + failed rules + remarks |
| `SummaryMetrics` | `report: FinalAuditReport` | 2×2 grid of MetricCard |
| `DocumentList` | `documents[]`, `interval` | Maps to DocumentCards |
| `ReportSection` | `report`, `interval` | Header card with overview score + summary |

---

## API client (`src/api/audit.ts`)

| Function | Endpoint | Method | Request | Response |
|----------|----------|--------|---------|----------|
| `runAudit` | `/api/audit` | POST | `{ folder_path, audit_title }` | `AuditResponse` |
| `downloadReport` | `/api/audit/download` | POST | `{ folder_path, audit_title }` | Blob (.docx) via download link |

**Base URL:** `http://localhost:8000` (hardcoded).  
**Error handling:** Throws `Error` with `body.detail` or status text.

---

## Types (`src/types/audit.ts`)

```typescript
interface FailedChecklistItem {
  rule_id: string; rule_title: string; description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  evidence: string; page_number: number | null;
}
interface DocumentAuditResult {
  document_name: string; passed: boolean; score: number;
  failed_rules: FailedChecklistItem[]; remarks: string;
  preview_base64: string;  // base64 JPEG thumbnail
}
interface FinalAuditReport {
  audit_title: string; documents_processed: number;
  documents_passed: number; documents_failed: number;
  overall_score: number; overall_result: 'PASS' | 'REVIEW REQUIRED' | 'FAIL';
  summary: string; document_results: DocumentAuditResult[];
}
interface PredictionInterval { lower: number; upper: number; }
interface AuditResponse {
  report: FinalAuditReport; prediction_interval: PredictionInterval;
  elapsed_seconds: number;
}
type Status = 'idle' | 'loading' | 'success' | 'error';
```

---

## State machine (App.tsx)

```
  idle ──[Run]──→ loading ──[success]──→ success (show results)
                              ──[error]───→ error (show error message)
```

App state: `status: Status`, `data: AuditResponse | null`, `error: string | null`.

---

## Key design decisions

1. **No routing library.** Single-page, no React Router. All state via `useState`.
2. **No state management.** No Redux, Zustand, etc.
3. **No test framework.** No Vitest, Playwright, or testing libraries configured.
4. **Tailwind v4**, not v3. Uses `@theme` directive, CSS variables for dark mode.
5. **oxlint** for linting (Rust-based), no ESLint.
6. **Preview thumbnails** are base64 JPEG embedded in the API response (not fetched separately).
7. **Download** triggers a browser download via hidden `<a>` click + `URL.createObjectURL`.
8. **Dark mode** respects system preference on first visit, then persists choice.
