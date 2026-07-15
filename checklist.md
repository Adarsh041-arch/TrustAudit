# Audit Checklist: Business Document Compliance

## Metadata

- **Audit Name:** Business Document Compliance Audit
- **Version:** 2.0
- **Description:** Standard checklist for auditing invoices, receipts, purchase orders, delivery challans, contracts, and certificates.

---

## Rules

### R001: Document Legibility

- **Severity:** high
- **Mandatory:** true
- **Description:** All text, numbers, barcodes, and signatures in the document must be clearly legible without magnification. Blurred, faded, faint, overexposed, partially printed, or heavily stamped-over content constitutes a failure.

### R002: Mandatory Fields Present

- **Severity:** critical
- **Mandatory:** true
- **Description:** The document must contain all mandatory fields for its type:
  - **Invoice / Receipt:** document number, issue date, seller name/address, buyer name/address, line items with quantities and unit prices, subtotal, tax amount, grand total, currency.
  - **Purchase Order:** PO number, issue date, vendor name, item descriptions, quantities, unit prices, delivery date, payment terms.
  - **Delivery Challan:** challan number, date, supplier name, receiver name, item descriptions, quantities, signature of receiver.
  - **Contract:** contract number, parties involved, effective date, term/duration, scope of work, consideration/price, signatures of both parties.
  - **Certificate:** certificate number, issue date, issuing authority, recipient name, validity period (if applicable), authorized signature/seal.

### R003: Mathematical Accuracy

- **Severity:** critical
- **Mandatory:** true
- **Description:** All arithmetic must be correct. Line-item totals must equal quantity × unit price. Subtotal must match sum of line items. Tax and discounts must be calculated correctly. Grand total must equal subtotal + tax − discounts. Cross-foot all columns.

### R004: Authorization & Signatures

- **Severity:** high
- **Mandatory:** true
- **Description:** Documents requiring authorization must contain a valid wet-ink or digital signature, stamp, or seal from the authorized party. The signatory name and designation must be legible. For contracts, all named parties must have signed.

### R005: Date Validity

- **Severity:** medium
- **Mandatory:** false
- **Description:** All dates on the document must be valid (not in the future for historical documents, not prior to the organization's founding). The document date must fall within the expected audit period. For certificates, the expiry/validity date must not have passed.

### R006: Currency & Amount Consistency

- **Severity:** high
- **Mandatory:** true
- **Description:** All monetary values must use a single consistent currency symbol throughout the document. Mixed currencies (e.g., $ and ₹ in the same document) must be flagged unless explicitly noted as a multi-currency transaction with conversion rates provided.

### R007: Vendor / Customer Information Completeness

- **Severity:** high
- **Mandatory:** true
- **Description:** Vendor/supplier and customer/buyer information must include: full legal name, complete address (street, city, state, postal code), and at least one contact identifier (phone, email, GST/VAT/TAX ID, or registration number). PO boxes without a physical address are insufficient.

### R008: Document Number Uniqueness & Format

- **Severity:** medium
- **Mandatory:** false
- **Description:** The document number must follow a logical format (alphanumeric, sequential, or date-based) and must not be a duplicate of another document in the same batch. Sequential gaps or out-of-range numbers should be noted.

### R009: Payment Terms & Due Date

- **Severity:** high
- **Mandatory:** true
- **Description:** Payment terms (e.g., Net 30, Due on Receipt, 2/10 Net 30) must be explicitly stated. A due date or payment deadline must be present. Early-payment discounts and late-payment penalties must be clearly described where applicable.

### R010: Tax Breakdown & Compliance

- **Severity:** critical
- **Mandatory:** true
- **Description:** Tax must be explicitly broken down by type (GST, VAT, sales tax, etc.), rate, and amount. The tax registration ID (GSTIN, VAT ID, etc.) of the supplier must be present. Tax-exempt documents must reference the applicable exemption clause or certificate.

### R011: Goods / Services Description

- **Severity:** medium
- **Mandatory:** false
- **Description:** Each line item must have a clear description of the goods or services provided. Generic descriptions like "miscellaneous" or "services rendered" without detail should be flagged. HSN/SAC codes, if applicable, should be present.

### R012: Supporting Attachments Reference

- **Severity:** low
- **Mandatory:** false
- **Description:** If the document references supporting attachments (e.g., "see attached schedule", "as per contract #123"), those attachments should be present in the submission. Cross-reference the attachment name or number where possible.
