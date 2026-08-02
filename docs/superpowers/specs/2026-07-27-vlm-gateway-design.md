# VLM Gateway — NVIDIA Extraction Fallback + Supplement

**Date:** 2026-07-27
**Status:** Draft

## Goal

Wire a real VLM (NVIDIA API, `google/diffusiongemma-26b-a4b-it`) into the extraction pipeline so scanned/image documents stop failing silently and low-confidence regex fields get a model-based second opinion.

## Architecture

```
extract_document(data, mime_type, doc_type):
  │
  ├─ Try regex extraction (current path)
  │   ├─ ValueError (scanned/no text layer)
  │   │   └─ VLM as primary → ExtractedDocument (confidence with vlm_only_penalty)
  │   └─ Success
  │       ├─ All critical fields ≥ 0.80 confidence → return regex result (fast, no model call)
  │       └─ Any critical field < 0.80 confidence → VLM supplement
  │           └─ merge_field_by_field(regex_doc, vlm_doc) via compute_field_confidence()
```

## Files

| File | Action |
|------|--------|
| `audit_v2/gateway/nvidia_gateway.py` | Create — thin OpenAI-compatible client |
| `audit_v2/extraction/vlm_extractor.py` | Create — VLM-based BaseExtractor |
| `audit_v2/orchestration/activities.py` | Modify — VLM fallback + supplement in `extract_document()` |
| `audit_v2/pyproject.toml` | Modify — add `openai>=1.0` |

## New Components

### `audit_v2/gateway/nvidia_gateway.py`

Thin HTTP client to NVIDIA's OpenAI-compatible endpoint. No LangChain, no SDK abstractions beyond what's needed.

```python
class NvidiaGateway:
    def __init__(self, api_key: str, model: str, base_url: str = DEFAULT_BASE_URL):
        ...

    def extract(self, images: list[bytes], prompt: str, tenant_id: str) -> ModelResponse:
        """
        Send page images to NVIDIA API.
        Images are base64-encoded PNGs (rendered PDF pages).
        Prompt asks for JSON matching ExtractedDocument shape.
        Returns ModelResponse with content = JSON string.
        """
        # client.chat.completions.create with multimodal content
        # Retry 2x, timeout 60s, raise on parse failure
```

- Uses `openai.OpenAI` (sync client — match existing sync extractors in activities.py)
- `DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"`
- Environment: `NVIDIA_API_KEY` (required), `NVIDIA_MODEL` (default `google/diffusiongemma-26b-a4b-it`)
- Retry: 2 attempts with exponential backoff
- Response validation: must be valid JSON, must match expected shape

### `audit_v2/extraction/vlm_extractor.py`

```python
class VlmExtractor(BaseExtractor):
    def __init__(self, gateway: NvidiaGateway):
        self.gateway = gateway

    def extract(self, data: bytes, mime_type: str) -> ExtractedDocument:
        # 1. Render PDF pages to PIL Images (PyMuPDF, 200 DPI)
        # 2. Build structured extraction prompt
        # 3. Call gateway.extract(images, prompt)
        # 4. Parse JSON → ExtractedDocument with ProvenancedValues
        # 5. Return
```

**Prompt shape** (structured, asks for JSON):
```
Extract the following fields from this invoice document image.
Return a JSON object with:
{
  "header": {
    "vendor_name": {"value": "...", "confidence": 0.95},
    "vendor_gstin": {"value": "...", "confidence": 0.95},
    "subtotal": {"value": "...", "confidence": 0.95},
    "grand_total": {"value": "...", "confidence": 0.95},
    "invoice_date": {"value": "...", "confidence": 0.95},
    ...
  },
  "line_items": [
    {
      "description": {"value": "...", "confidence": 0.95},
      "quantity": {"value": "...", "confidence": 0.95},
      "rate": {"value": "...", "confidence": 0.95},
      "total": {"value": "...", "confidence": 0.95},
      "hsn": {"value": "...", "confidence": 0.95}
    }
  ],
  "tax_lines": [...]
}
Use the exact field names shown. Set confidence based on how clearly you can read the value.
```

Prompt doc-type-specific: invoice_extractor prompt for invoices, po_extractor prompt for POs, etc. The classifier already runs before extraction, so `doc_type` is known.

### Modified `activities.py:extract_document()`

```python
def extract_document(data, mime_type, document_id, tenant_id, doc_type):
    # 1. Try regex extraction
    try:
        regex_result = _regex_extract(data, mime_type, document_id, tenant_id, doc_type)
    except ValueError:
        # Scanned / no text layer → VLM primary
        return _vlm_extract(data, mime_type, document_id, tenant_id, doc_type)

    # 2. Check confidence on critical fields
    if _has_low_confidence(regex_result.document, threshold=0.80):
        # VLM supplement → merge
        vlm_result = _vlm_extract(data, mime_type, document_id, tenant_id, doc_type)
        merged = _merge_extractions(regex_result.document, vlm_result.document)
        return ExtractionResult(document=merged, text=regex_result.text)

    # 3. All high confidence → return regex
    return regex_result
```

**Critical fields:** `subtotal`, `grand_total`, `vendor_gstin`, `invoice_date`, `po_reference`, all line item `total` values, all tax `amount` values.

**Merge logic** (per field, uses `confidence.py`):
```python
for each field in header:
    regex_pv = regex_doc.header.field
    vlm_pv = vlm_doc.header.field
    if both exist:
        agreement = 1.0 if regex_pv.value == vlm_pv.value else 0.0
        merged_confidence = compute_field_confidence(
            field_name, regex_pv.confidence, vlm_pv.confidence, agreement
        )
        use higher-confidence value
    elif only one exists:
        use that one
    else:
        skip
```

## Dependencies

Add to `pyproject.toml`:
```toml
"openai>=1.0"
```

## Config (.env)

```
NVIDIA_API_KEY=...
NVIDIA_MODEL=google/diffusiongemma-26b-a4b-it
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
```

## What doesn't change

- Validators, routing, workflow, Temporal, golden set, measure_v2.py — all untouched
- Regex extractors still the primary path for text-layer docs
- `NvidiaGateway` is lazy-initialized (only created when VLM extraction is needed)

## Testing

1. `tests/test_nvidia_gateway.py` — mock HTTP calls, verify retry/timeout/parse-error behavior
2. `tests/test_vlm_extractor.py` — mock gateway returns canned JSON, verify ExtractedDocument shape
3. `tests/test_extraction.py` — add test for scanned PDF fallback path (PDF with no text layer)
4. `tests/test_confidence.py` — verify merge logic with known regex + VLM values

## Cost

Per VLM call: ~₹2 (same as V1 NVIDIA baseline). Trigger conditions:
- Scanned PDFs (always → VLM primary)
- Text-layer PDFs where any critical field confidence < 0.80 (estimated ~40-60% of current golden set)

Full 200-doc golden set estimate: ~100-120 VLM calls × ₹2 = ₹200-240 per full evaluation run.
