# Audit Checklist: Business Document Compliance

## Metadata

- **Audit Name:** Business Document Compliance Audit
- **Version:** 2.1
- **Description:** Calibrated checklist for auditing invoices, receipts, purchase orders, delivery challans, contracts, and certificates. High severity is reserved for core financial integrity (arithmetic accuracy, future dates, amount & currency consistency). Document-dependent fields (signatures, stamps, addresses, tax IDs) are evaluated with medium/low severity.

---

## Rules

### R001: Document Legibility

- **Severity:** medium
- **Mandatory:** false
- **Description:** Text, numbers, and key headers should be readable. Minor scan blur or faint print is noted as medium risk unless numbers are completely illegible.

### R002: Mandatory Fields Present

- **Severity:** medium
- **Mandatory:** false
- **Description:** Evaluates header fields based on the specific document type (Invoices require total/date; Contracts require parties/effective date). Missing optional fields on simple receipts or challans are not penalized as high severity.

### R003: Mathematical Accuracy

- **Severity:** critical
- **Mandatory:** true
- **Description:** Core financial integrity check. All arithmetic must be exact: Line-item totals (quantity × unit price), subtotal sum, tax splits, discounts, and grand totals. Any math error directly impacts compliance score.

### R004: Authorization & Signatures

- **Severity:** medium
- **Mandatory:** false
- **Description:** Signatures, stamps, or digital seals are checked where applicable. Computer-generated tax invoices or retail receipts without physical signatures are flagged as medium or low priority rather than critical failures.

### R005: Date Validity & Future Dates

- **Severity:** high
- **Mandatory:** true
- **Description:** Dates must be valid and chronologically sound. Documents dated in the future or expired certificates are flagged as High Severity violations as they invalidate audit timelines.

### R006: Currency & Amount Consistency

- **Severity:** high
- **Mandatory:** true
- **Description:** Monetary values must use a single consistent currency symbol throughout the document, and line item amounts must consistently reconcile with the total figure.

### R007: Vendor / Customer Information Completeness

- **Severity:** medium
- **Mandatory:** false
- **Description:** Checks presence of legal vendor and customer names. Detailed street addresses and secondary tax IDs are document-dependent and treated as medium severity if omitted.

### R008: Document Number Uniqueness & Format

- **Severity:** low
- **Mandatory:** false
- **Description:** Document numbers should follow a logical sequence. Formatting variations are logged as low-severity audit notes.

### R009: Payment Terms & Due Date

- **Severity:** low
- **Mandatory:** false
- **Description:** Payment terms (Net 30, Due on Receipt) apply primarily to credit invoices. Omission on immediate cash receipts or delivery notes is low severity.

### R010: Tax Breakdown & Compliance

- **Severity:** medium
- **Mandatory:** false
- **Description:** Explicit tax rate and GST/VAT breakdowns are evaluated when applicable. Non-taxable receipts or simple bills without itemized tax breakdowns are treated as medium severity.

### R011: Goods / Services Description

- **Severity:** low
- **Mandatory:** false
- **Description:** Evaluates line item descriptions for clarity. Generic descriptions are logged with low severity.

### R012: Supporting Attachments Reference

- **Severity:** low
- **Mandatory:** false
- **Description:** References to schedules or attached annexures are logged as low-severity informational checks.
