# Audit Report — LiteRT Gemma 4 E2B

- **Model:** `gemma-4-E2B-it` (LiteRT, GPU-backed)
- **Checklist:** `checklist.md` (12 rules)
- **Documents:** 3 processed, 0 passed
- **Average Score:** 28.5%

---

## Bill Data Extraction and Formatting (1).pdf

| Field | Value |
|-------|-------|
| Type | purchase_order |
| Language | English |
| Summary | This document appears to be a purchase order detailing various items and their quantities for a floor, including first floor and ground floor items. |
| **Result** | **FAIL** |
| **Score** | **0.0%** |

### Failed Rules (all)

All 12 rules failed. No specific rule details were returned by the model.

---

## INV-2026-0715_NewTech_Solutions.pdf

| Field | Value |
|-------|-------|
| Type | invoice |
| Language | English |
| Summary | This document is a tax invoice from NewTech Solutions Pvt Ltd, located in Bangalore, India, issued to a customer. The invoice number is INV-2026-0715. |
| **Result** | **FAIL** |
| **Score** | **0.0%** |

### Failed Rules (all)

All 12 rules failed. No specific rule details were returned by the model.

---

## RS ENTERPRISES PIRAMAL.pdf

| Field | Value |
|-------|-------|
| Type | invoice |
| Language | English |
| Summary | This document is an invoice from RS ENTERPRISES to Sammunati Projects Pvt Ltd. It details a bill for 'Manpower Supply' with a total amount of 21,800. |
| **Result** | **FAIL** |
| **Score** | **85.5%** |

### Failed Rules (3)

| Rule | Evidence |
|------|----------|
| R002 | The document is an invoice, which contains most mandatory fields (document number, date, seller name, buyer name, line items, subtotal, grand total). However, the buyer address is missing or incomplete |
| R006 | The document does not explicitly state the currency, which is a mandatory field for consistency |
| R009 | Payment terms (e.g., Net 30) and a due date are not explicitly stated |

**Remarks:** The document is a relatively clean invoice structure, but fails several mandatory checks. Mathematical accuracy (R003) appears correct. Primary failures: missing explicit currency (R006), missing payment terms/due date (R009), incomplete buyer address (R002).

---

## Summary

The model runs on GPU (~1–2 min/doc) and produces reasonable document understanding. Key observations:
- The 3B-small Gemma 4 variant has limited vision accuracy — docs 1–2 got 0% with no specific failures
- Doc 3 produced credible, specific findings (85.5% score)
- Rule ID hallucination observed (`R00006`, `R00009` vs `R006`, `R009`)
- Score parsing fragility (model returned 855 instead of 85.5)
- V2's structured parsing and pure-Python validators address all these defects
