# Phases 2–5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 4 (full extraction for all 4 doc types + chunking), Phase 5 (routing), and begin Phase 2 (governance controls).

**Architecture:** Extend the existing `BaseExtractor` hierarchy with PO, Delivery Challan, and GRN extractors. Add a deterministic routing engine that maps (document_type, value_band, tenant_policy) → check set. Add governance controls in parallel: PII redaction, immutable audit log, RLS policies, data retention, model register.

**Tech Stack:** Python 3.12, Pydantic, PyMuPDF, pgvector, Postgres.

## Global Constraints

- `audit_v2/` must not import from `app/` or `backend/` (enforced by CI import-linter)
- All monetary values: `Decimal` in code, integer minor units in DB, strings in JSON. Never `float`.
- Domain layer is pure — no network calls, no model calls
- Every extracted field is a `ProvenancedValue`: `{value, raw, bbox, page, confidence}`
- Deterministic checks that call a model fail CI
- Check `determinism` field on every check; ≥80% marked `deterministic`

---

### Task 1: Phase 4 M1b — Invoice hardening

**Files:**
- Modify: `audit_v2/extraction/invoice_extractor.py`
- Modify: `audit_v2/extraction/text_extractor.py`
- Modify: `audit_v2/extraction/confidence.py`
- Modify: `tests/test_extraction.py`

**Context:** Fix known deficiencies in the invoice extractor before building new extractors.

- [ ] **Step 1: Multi-page coverage**
  In `invoice_extractor.py`, replace hardcoded `pages_total=1, pages_examined=1, coverage_complete=True` with real values from `TextExtractor`. In `extract()` when mime_type is "application/pdf", use `self._text_extractor.extract_page_texts(data)` to get actual page count. Set `pages_examined` to number of successfully extracted pages, `pages_unreadable` to pages that returned no text, `coverage_complete` when `pages_examined == pages_total`.

- [ ] **Step 2: Bbox provenance**
  In `invoice_extractor.py:extract()` for PDFs, call `self._text_extractor.extract_text_blocks(data)` and use block-level bbox data when assigning ProvenancedValue fields. Each extracted field gets `bbox` from the corresponding text block.

- [ ] **Step 3: Windows line endings**
  In `invoice_extractor.py:_extract_line_items_from_text()`, change `text.split("\n")` to `text.splitlines()`.

- [ ] **Step 4: Non-silent PyMuPDF failure**
  In `text_extractor.py`, change silent `except ImportError: return []` to log a warning and re-raise a `RuntimeError`. In `pdf_utils.py`, same treatment for silent `except Exception` blocks.

- [ ] **Step 5: Configurable thresholds in confidence.py**
  Move `VLM_ONLY_PENALTY`, `DISAGREEMENT_PENALTY`, `TEXT_LAYER_BONUS` into a dataclass `ConfidenceConfig` with default values. Accept optional config in `compute_field_confidence()`.

- [ ] **Step 6: Agreement score fix**
  In `confidence.py:agreement_score()`, fix denominator for partially-overlapping dicts: only count keys present in both dicts, not union of all keys.

- [ ] **Step 7: Run tests + lint**

  ```
  pytest --tb=short -v
  ruff check audit_v2/
  ```

---

### Task 2: Phase 4.5 — Document Type Classifier

**Files:**
- Create: `audit_v2/extraction/classifier.py`
- Create: `tests/test_classifier.py`

**Interfaces:**
- `classify_document(text: str) -> tuple[DocumentType, float]` — returns (type, confidence)
- `classify_document_from_data(data: bytes, mime_type: str) -> tuple[DocumentType, float]` — extracts text then classifies
- `EXTRACTOR_REGISTRY: dict[DocumentType, type[BaseExtractor]]` — maps types to extractors

- [ ] **Step 1: Write failing test**
  ```python
  from audit_v2.extraction.classifier import classify_document, classify_document_from_data
  from audit_v2.domain.models import DocumentType

  def test_classify_invoice():
      text = "Tax Invoice\nInvoice No: INV-001\nDate: 25/07/2026"
      result, conf = classify_document(text)
      assert result == DocumentType.INVOICE
      assert conf >= 0.8

  def test_classify_po():
      text = "Purchase Order\nPO No: PO-001\nVendor: Acme Corp"
      result, conf = classify_document(text)
      assert result == DocumentType.PURCHASE_ORDER
      assert conf >= 0.8

  def test_classify_delivery_challan():
      text = "Delivery Challan\nDC No: DC-001\nVehicle No: MH-01-AB-1234"
      result, conf = classify_document(text)
      assert result == DocumentType.DELIVERY_CHALLAN
      assert conf >= 0.8

  def test_classify_grn():
      text = "Goods Receipt Note\nGRN No: GRN-001\nPO Reference: PO-001"
      result, conf = classify_document(text)
      assert result == DocumentType.GOODS_RECEIPT_NOTE
      assert conf >= 0.8

  def test_classify_empty_returns_low_confidence():
      result, conf = classify_document("")
      assert conf < 0.5

  def test_classify_ambiguous_returns_low_confidence():
      # A document with minimal identifying markers
      text = "Some random document with no clear type indicators"
      result, conf = classify_document(text)
      assert conf < 0.5

  def test_classify_from_data_with_text_mime():
      data = b"Tax Invoice\nInvoice No: INV-001"
      result, conf = classify_document_from_data(data, "text/plain")
      assert result == DocumentType.INVOICE
      assert conf >= 0.8
  ```

- [ ] **Step 2: Run to verify failures**
  Run: `pytest tests/test_classifier.py -v`
  Expected: 7 failures (module not found)

- [ ] **Step 3: Implement `EXTRACTOR_REGISTRY` and `classify_document()`**

  ```python
  # audit_v2/extraction/classifier.py

  import re
  from audit_v2.domain.models import DocumentType
  from audit_v2.extraction.base import BaseExtractor
  from audit_v2.extraction.invoice_extractor import InvoiceExtractor

  EXTRACTOR_REGISTRY: dict[DocumentType, type[BaseExtractor]] = {
      DocumentType.INVOICE: InvoiceExtractor,
  }

  _TYPE_SIGNATURES: list[tuple[DocumentType, list[re.Pattern], float]] = [
      (DocumentType.INVOICE, [
          re.compile(r"Tax\s*Invoice", re.IGNORECASE),
          re.compile(r"Invoice\s*(?:No|Number|#)", re.IGNORECASE),
      ], 0.4),
      (DocumentType.PURCHASE_ORDER, [
          re.compile(r"Purchase\s*Order", re.IGNORECASE),
          re.compile(r"PO\s*(?:No|Number|#)", re.IGNORECASE),
      ], 0.4),
      (DocumentType.DELIVERY_CHALLAN, [
          re.compile(r"Delivery\s+Challan", re.IGNORECASE),
          re.compile(r"DC\s*(?:No|Number|#)", re.IGNORECASE),
          re.compile(r"Vehicle\s*(?:No|Number|#)", re.IGNORECASE),
      ], 0.3),
      (DocumentType.GOODS_RECEIPT_NOTE, [
          re.compile(r"Goods\s*(?:Receipt|Received)\s*Note", re.IGNORECASE),
          re.compile(r"GRN\s*(?:No|Number|#)", re.IGNORECASE),
          re.compile(r"(?:Material|Goods)\s*Received", re.IGNORECASE),
      ], 0.3),
  ]

  def classify_document(text: str) -> tuple[DocumentType, float]:
      best_type = DocumentType.INVOICE
      best_score = 0.0

      for doc_type, patterns, weight in _TYPE_SIGNATURES:
          score = 0.0
          for pat in patterns:
              if pat.search(text):
                  score += weight
          if score > best_score:
              best_score = score
              best_type = doc_type

      return best_type, min(best_score, 1.0)

  def classify_document_from_data(data: bytes, mime_type: str) -> tuple[DocumentType, float]:
      text = data.decode("utf-8", errors="replace") if mime_type == "text/plain" else ""
      if not text and mime_type == "application/pdf":
          from audit_v2.extraction.text_extractor import TextExtractor
          pages = TextExtractor().extract_page_texts(data)
          text = "\n".join(pages.values())
      return classify_document(text)
  ```

- [ ] **Step 4: Tests pass + lint**

  ```
  pytest tests/test_classifier.py -v
  ruff check audit_v2/extraction/classifier.py
  ```

---

### Task 3: Phase 4.2 — PO Extractor

**Files:**
- Create: `audit_v2/extraction/po_extractor.py`
- Modify: `audit_v2/extraction/classifier.py` (register in `EXTRACTOR_REGISTRY`)
- Create: `tests/test_po_extractor.py`

**Interfaces:**
- Class `POExtractor(BaseExtractor)` — same ABC as `InvoiceExtractor`
- Header fields: `po_number`, `vendor_name`, `vendor_address`, `order_date`, `delivery_date`, `payment_terms`, `delivery_address`, `total_amount`, `po_reference` (for linked POs)
- Line items: `line_number`, `description`, `hsn_sac`, `quantity`, `unit_price`, `line_total`

- [ ] **Step 1: Write test data + failing tests**

  `SAMPLE_PO_TEXT`:
  ```text
  Purchase Order
  PO No: PO-2026-0089
  Order Date: 20/07/2026
  Delivery Date: 15/08/2026
  Vendor: Global Supplies Ltd
  Vendor GSTIN: 29AABCT1234D1Z6
  Address: 456 Industrial Zone, Pune - 411001
  Delivery Address: Warehouse B, MIDC, Nashik - 422010
  Payment Terms: 30 days from invoice

  | # | Description          | HSN    | Qty | Rate    | Amount   |
  |---|----------------------|--------|-----|---------|----------|
  | 1 | Steel Rods 12mm      | 7214   | 100 | 450.00  | 45,000.00|
  | 2 | Steel Rods 16mm      | 7214   | 50  | 520.00  | 26,000.00|

  Total Order Value: 71,000.00
  Amount in words: Rupees Seventy One Thousand Only
  ```

  Tests:
  ```python
  def test_extract_po_header(): ...
  def test_extract_po_line_items(): ...
  def test_extract_po_full_document(): ...
  def test_po_number_variants(): ...  # PO-2026-0089, PO/2026/0089, etc.
  def test_po_missing_delivery_date(): ...
  def test_po_missing_payment_terms(): ...
  def test_po_provenance_on_all_fields(): ...
  ```

- [ ] **Step 2: Run to verify failures**
  Run: `pytest tests/test_po_extractor.py -v`
  Expected: 7 failures

- [ ] **Step 3: Implement `POExtractor`**

  Follow same pattern as `InvoiceExtractor`:
  - `HEADER_FIELD_PATTERNS` regex dict for PO fields
  - `LINE_ITEM_TABLE_RE` matching PO table headers
  - `LINE_ITEM_ROW_RE` for PO line rows
  - `TABLE_END_MARKERS` (Total Order Value, etc.)
  - `_extract_header_from_text()`, `_extract_line_items_from_text()`, `extract()`

- [ ] **Step 4: Register POExtractor**

  In `classifier.py`, add to `EXTRACTOR_REGISTRY`:
  ```python
  from audit_v2.extraction.po_extractor import POExtractor
  EXTRACTOR_REGISTRY[DocumentType.PURCHASE_ORDER] = POExtractor
  ```

- [ ] **Step 5: Tests pass + lint**

  ```
  pytest tests/test_po_extractor.py -v
  ruff check audit_v2/extraction/po_extractor.py
  ```

---

### Task 4: Phase 4.3 — Delivery Challan Extractor

**Files:**
- Create: `audit_v2/extraction/delivery_challan_extractor.py`
- Modify: `audit_v2/extraction/classifier.py` (register)
- Create: `tests/test_dc_extractor.py`

**Interfaces:**
- Class `DeliveryChallanExtractor(BaseExtractor)`
- Header fields: `dc_number`, `po_reference`, `vendor_name`, `vehicle_number`, `date`, `from_address`, `to_address`, `received_by`
- Line items: `line_number`, `description`, `hsn_sac`, `quantity_delivered`, `unit`

- [ ] **Step 1: Write test data + failing tests**

  `SAMPLE_DC_TEXT`:
  ```text
  Delivery Challan
  DC No: DC-2026-0045
  Date: 22/07/2026
  PO Reference: PO-2026-0089
  Vehicle No: MH-01-AB-5678
  From: Global Supplies Ltd, Pune
  To: Warehouse B, MIDC, Nashik
  Received By: Rajesh Kumar

  | # | Description          | HSN    | Qty Delivered | Unit |
  |---|----------------------|--------|---------------|------|
  | 1 | Steel Rods 12mm      | 7214   | 100           | Pcs  |
  | 2 | Steel Rods 16mm      | 7214   | 50            | Pcs  |

  Remarks: Material in good condition
  ```

- [ ] **Step 2: Run to verify failures**

- [ ] **Step 3: Implement `DeliveryChallanExtractor`**

  Headers: DC No, PO Reference, Vehicle No, Date, From, To, Received By
  Line items: Sr, Description, HSN, Qty, Unit
  End markers: Remarks, Total

- [ ] **Step 4: Register in EXTRACTOR_REGISTRY**

- [ ] **Step 5: Tests pass + lint**

---

### Task 5: Phase 4.4 — GRN Extractor

**Files:**
- Create: `audit_v2/extraction/grn_extractor.py`
- Modify: `audit_v2/extraction/classifier.py` (register)
- Create: `tests/test_grn_extractor.py`

**Interfaces:**
- Class `GRNExtractor(BaseExtractor)`
- Header fields: `grn_number`, `po_reference`, `dc_reference`, `vendor_name`, `received_date`, `inspected_by`, `remarks`
- Line items: `line_number`, `description`, `hsn_sac`, `qty_ordered`, `qty_received`, `qty_rejected`

- [ ] **Step 1: Write test data + failing tests**

  `SAMPLE_GRN_TEXT`:
  ```text
  Goods Receipt Note
  GRN No: GRN-2026-0032
  Date: 25/07/2026
  PO Reference: PO-2026-0089
  DC Reference: DC-2026-0045
  Vendor: Global Supplies Ltd
  Inspected By: Suresh Patil

  | # | Description          | HSN    | Ordered | Received | Rejected |
  |---|----------------------|--------|---------|----------|----------|
  | 1 | Steel Rods 12mm      | 7214   | 100     | 98       | 2        |
  | 2 | Steel Rods 16mm      | 7214   | 50      | 50       | 0        |

  Remarks: 2 rods damaged in transit
  ```

- [ ] **Step 2: Run to verify failures**

- [ ] **Step 3: Implement `GRNExtractor`**

  Headers: GRN No, PO Reference, DC Reference, Vendor, Date, Inspected By, Remarks
  Line items: Sr, Description, HSN, Ordered Qty, Received Qty, Rejected Qty
  End markers: Remarks, Total

- [ ] **Step 4: Register in EXTRACTOR_REGISTRY**

- [ ] **Step 5: Tests pass + lint**

---

### Task 6: Phase 4.7 — Chunking + Embedding (secondary path)

**Files:**
- Create: `audit_v2/extraction/chunker.py`
- Create: `audit_v2/gateway/embedding.py`
- Create: `audit_v2/persistence/vector_store.py`
- Create: `tests/test_chunker.py`

**Interfaces:**
- `chunk_text(text: str, source: str, page: int) -> list[TextChunk]`
- `class TextChunk(id, source, page, bbox, text, embedding)`
- `class EmbeddingGateway` — `generate(text: str) -> list[float]` (stub returns zeros)
- `class VectorStore` — `insert(chunk: TextChunk)`, `search(query: list[float], tenant_id: str, top_k: int) -> list[TextChunk]`

- [ ] **Step 1: Write failing tests**

- [ ] **Step 2: Implement `chunk_text()`**

  Split by paragraphs and sentence boundaries. Each chunk has source document ID, page number, bbox if available.

- [ ] **Step 3: Implement `EmbeddingGateway` stub**

  Returns `[0.0] * 384` for any input.

- [ ] **Step 4: Implement `VectorStore` interface + memory implementation**

  Memory implementation for tests, pgvector interface for production.

- [ ] **Step 5: Tests pass + lint**

---

### Task 7: Phase 5 — Routing Engine

**Files:**
- Create: `audit_v2/routing/__init__.py`
- Create: `audit_v2/routing/models.py`
- Create: `audit_v2/routing/engine.py`
- Create: `contracts/routing_rules.yaml`
- Modify: `audit_v2/orchestration/workflows.py` (wire routing)
- Create: `tests/test_routing.py`

**Interfaces:**
- `RoutingRule(doc_type, value_band_min, value_band_max, tenant_policy, include_checks, exclude_checks, rule_id)`
- `RoutingDecision(rule_id, included_check_ids: list[str], skipped_check_ids: dict[str, str])` — key = check_id, value = skip_reason
- `resolve(document_header, tenant_policy, check_catalog) -> RoutingDecision`

- [ ] **Step 1: Write routing rules YAML + failing tests**

  ```yaml
  # contracts/routing_rules.yaml
  rules:
    - rule_id: ROUTE-INV-001
      doc_type: invoice
      value_band_min: "0"
      value_band_max: "1000000000"
      tenant_policy: standard
      include_checks:
        - CHK-ARITH-LINE-001
        - CHK-ARITH-TAX-001
        - CHK-ARITH-GRAND-001
        - CHK-FORMAT-FIELDS-001
      exclude_checks:
        - CHK-REF-QTY-001  # requires PO — not available for standalone invoice

    - rule_id: ROUTE-PO-001
      doc_type: purchase_order
      value_band_min: "0"
      value_band_max: "1000000000"
      tenant_policy: standard
      include_checks:
        - CHK-ARITH-LINE-001
        - CHK-ARITH-GRAND-001
        - CHK-SEQ-DATE-001
  ```

  Tests:
  ```python
  def test_resolve_invoice_standard(): ...
  def test_resolve_po_standard(): ...
  def test_resolve_excluded_checks(): ...
  def test_resolve_same_input_same_output(): ...
  def test_decision_records_rule_id(): ...
  def test_skipped_check_has_reason(): ...
  def test_unknown_doc_type_returns_empty(): ...
  ```

- [ ] **Step 2: Implement `RoutingRule` model + `resolve()`**

  ```python
  # audit_v2/routing/models.py
  from pydantic import BaseModel

  class RoutingRule(BaseModel):
      rule_id: str
      doc_type: str
      value_band_min: str  # Decimal as string
      value_band_max: str
      tenant_policy: str
      include_checks: list[str]
      exclude_checks: list[str] = []

  class RoutingDecision(BaseModel):
      rule_id: str
      included_check_ids: list[str]
      skipped_check_ids: dict[str, str]  # check_id -> reason
  ```

  ```python
  # audit_v2/routing/engine.py
  import yaml
  from decimal import Decimal
  from audit_v2.domain.models import DocumentType
  from audit_v2.routing.models import RoutingRule, RoutingDecision

  def load_rules(path: str = "contracts/routing_rules.yaml") -> list[RoutingRule]:
      with open(path) as f:
          data = yaml.safe_load(f)
      return [RoutingRule(**r) for r in data["rules"]]

  def resolve(
      doc_type: DocumentType,
      total_value: Decimal | None,
      tenant_policy: str,
      catalog_check_ids: list[str],
      rules: list[RoutingRule] | None = None,
  ) -> RoutingDecision:
      if rules is None:
          rules = load_rules()

      for rule in rules:
          if rule.doc_type != doc_type.value:
              continue
          if total_value is not None:
              if Decimal(rule.value_band_min) > total_value or Decimal(rule.value_band_max) < total_value:
                  continue
          if rule.tenant_policy != tenant_policy:
              continue

          included = rule.include_checks
          excluded = {c: f"Excluded per routing rule {rule.rule_id}" for c in rule.exclude_checks}
          # All catalog checks not in included or excluded are also skipped
          skipped = {
              c: f"Not applicable for {doc_type.value} per routing rule {rule.rule_id}"
              for c in catalog_check_ids if c not in included and c not in excluded
          }
          skipped.update(excluded)
          return RoutingDecision(rule_id=rule.rule_id, included_check_ids=included, skipped_check_ids=skipped)

      # No matching rule — all checks skipped
      return RoutingDecision(
          rule_id="NO_RULE",
          included_check_ids=[],
          skipped_check_ids={c: "No routing rule matched document" for c in catalog_check_ids},
      )
  ```

- [ ] **Step 3: Wire routing into workflow**

  After extraction and normalization in `AuditWorkflow.run()`, call `resolve()` with extracted doc_type and grand_total. Store `RoutingDecision` on the document record. Return check set.

- [ ] **Step 4: Tests pass + lint**

---

### Task 8: Phase 2.1 — PII Redaction

**Files:**
- Create: `audit_v2/gateway/pii_redactor.py`
- Create: `tests/test_pii_redactor.py`

**Interfaces:**
- `classify_pii(text: str) -> dict[str, list[Span]]` — returns labels and spans
- `redact(text: str, pii_classes: list[str]) -> str` — replaces PII with `[REDACTED]`
- PII classes: `name`, `address`, `tax_id` (GSTIN/PAN), `bank_details` (account/IFSC), `phone`, `email`

- [ ] **Step 1: Write failing tests**

  ```python
  def test_redact_gstin(): ...
  def test_redact_pan(): ...
  def test_redact_bank_account(): ...
  def test_redact_ifsc(): ...
  def test_redact_phone(): ...
  def test_redact_email(): ...
  def test_redact_name(): ...
  def test_redact_address(): ...
  def test_no_false_positives_on_amounts(): ...  # 27AAAPL1234C1Z2 != amount
  def test_redact_leaves_structure_intact(): ...  # JSON still parseable
  ```

- [ ] **Step 2: Implement regex-based PII classifier + redactor**

  Use regex patterns for Indian financial identifiers:
  - GSTIN: `\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z]\d` (15 chars)
  - PAN: `[A-Z]{5}\d{4}[A-Z]`
  - IFSC: `[A-Z]{4}0\d{6}`
  - Bank account: `\d{9,18}`
  - Phone: Indian mobile pattern
  - Email: standard regex

- [ ] **Step 3: Tests pass + lint**

---

## Execution Order

```
Task 1 (M1b hardening) — fixes existing code, unblocks everything
  │
  ├──→ Task 2 (classifier) — needed before multi-extractor dispatch
  │      │
  │      ├──→ Task 3 (PO extractor)
  │      ├──→ Task 4 (DC extractor)
  │      └──→ Task 5 (GRN extractor)
  │
  ├──→ Task 6 (chunking) — parallel with Tasks 3-5
  │
  └──→ Task 7 (routing) — after classifier, can use PO/DC/GRN extractors
  │
  └──→ Task 8 (PII redaction) — parallel track
```

Recommended execution: subagent-driven development, dispatching parallel subagents for independent tasks (Tasks 3, 4, 5 can run in parallel).
