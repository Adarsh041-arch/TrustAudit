# Audit Report — NVIDIA DiffusionGemma 26B

- **Model:** `google/diffusiongemma-26b-a4b-it`
- **Checklist:** `C:\Users\adars\OneDrive\Desktop\AUDIT_AGENT\checklist.md` (12 rules)
- **Documents:** 3 processed, 1 passed
- **Average Score:** 65.0%

---

## Bill Data Extraction and Formatting - Bill Data Extraction and Formatting (1).pdf

| Field | Value |
|-------|-------|
| Type | Invoice/Bill Statement |
| Language | English |
| Summary | A detailed list of construction and repair work across the first floor, ground floor, and extra work, including mirrors, locks, flooring, and painting. |
| total_amount | 92815.00 |
| **Result** | **FAIL** |
| **Score** | **45.0%** |

### Failed Rules (7)

| Rule | Evidence |
|------|----------|
| R002 | The document is missing several mandatory fields for an Invoice: document number, issue date, seller name/address, buyer name/address, subtotal, tax amount, and currency. |
| R004 | The document lacks a valid signature, stamp, or seal from an authorized party. |
| R006 | No currency symbol or code is specified for the monetary values. |
| R007 | Vendor and customer information (legal name, complete address, contact identifier) is entirely missing. |
| R008 | No document number is provided. |
| R009 | Payment terms and due dates are not stated. |
| R010 | No tax breakdown (GST/VAT/Sales Tax), rate, or tax registration ID is present. |

**Remarks:** The document functions as a simple list of works rather than a formal invoice. It fails almost all critical compliance requirements including vendor/buyer details, document identification, currency, tax information, and authorization.

---

## INV-2026-0715_NewTech_Solutions.pdf

| Field | Value |
|-------|-------|
| Type | TAX INVOICE |
| Language | English |
| Summary | A tax invoice from NewTech Solutions Pvt Ltd to BuildRight Contractors for electronics including a laptop, mouse, printer, and stationery. |
| document_number | INV-2026-0715 |
| date | 15 July 2026 |
| total_amount | 157784.00 |
| currency | INR |
| vendor_name | NewTech Solutions Pvt Ltd |
| customer_name | BuildRight Contractors |
| **Result** | **PASS** |
| **Score** | **85.0%** |

### Failed Rules (1)

| Rule | Evidence |
|------|----------|
| R005 | The invoice date is 15 July 2026, which is in the future relative to the current date. |

**Remarks:** The document is largely compliant but fails on R005 as the invoice date (15 July 2026) is in the future. Additionally, the document states it is computer-generated and does not require a physical signature, which is noted under R004.

---

## RS ENTERPRISES PIRAMAL.pdf

| Field | Value |
|-------|-------|
| Type | Invoice |
| Language | English |
| Summary | An invoice from RS ENTERPRISES to Sammunati Projects Pvt Ltd for man power services (CL3-T2) totaling 21,820.00. |
| document_number | RA-Bill-01 |
| date | 29.03.2026 |
| total_amount | 21820.00 |
| currency | INR |
| vendor_name | RS ENTERPRISES |
| customer_name | Sammunati Projects Pvt Ltd |
| **Result** | **FAIL** |
| **Score** | **65.0%** |

### Failed Rules (4)

| Rule | Evidence |
|------|----------|
| R007 | The document is missing physical addresses for both the vendor (RS ENTERPRISES) and the buyer (Sammunati Projects Pvt Ltd). |
| R009 | Payment terms (e.g., Net 30) and a specific due date are not explicitly deated. |
| R010 | Tax is not explicitly broken down by type and rate; only a total 'Taxation' figure is shown without specific GST rate details. |
| R011 | The line item description 'CL3-T2 Manpower Supply' is present but lacks SAC codes for service classification. |

**Remarks:** The document is generally functional but fails on critical compliance regarding physical addresses for parties, explicit payment terms/due dates, and a detailed breakdown of tax rates/types.
