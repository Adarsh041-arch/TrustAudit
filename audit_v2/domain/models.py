from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

# ─── Enums ────────────────────────────────────────────────────────────────────

class DocumentType(StrEnum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    DELIVERY_CHALLAN = "delivery_challan"
    GOODS_RECEIPT_NOTE = "goods_receipt_note"


class DocumentStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    SCANNED = "SCANNED"
    RENDERED = "RENDERED"
    EXTRACTED = "EXTRACTED"
    NORMALIZED = "NORMALIZED"
    READY = "READY"
    PENDING = "PENDING"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"
    QUARANTINED_ENCRYPTED = "QUARANTINED_ENCRYPTED"
    QUARANTINED_MALWARE = "QUARANTINED_MALWARE"
    QUARANTINED_SECURITY = "QUARANTINED_SECURITY"
    INCOMPLETE = "INCOMPLETE"


class FindingStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CheckDeterminism(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"
    HYBRID = "hybrid"


class CheckCategory(StrEnum):
    ARITHMETIC = "arithmetic"
    ROLL_FORWARD = "roll_forward"
    SEQUENCE = "sequence"
    THRESHOLD = "threshold"
    TEMPORAL = "temporal"
    REFERENCE_INTEGRITY = "reference_integrity"
    FORMAT_COMPLETENESS = "format_completeness"
    DUPLICATE = "duplicate"


class FailureClass(StrEnum):
    TRANSIENT = "TRANSIENT"
    POISON = "POISON"
    BUDGET = "BUDGET"
    POLICY = "POLICY"
    LOGIC = "LOGIC"


# ─── Value Objects ────────────────────────────────────────────────────────────

class ProvenancedValue(BaseModel):
    value: str
    raw: str
    currency: str | None = None
    bbox: list[float] | None = None
    page: int = 1
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def decimal_value(self) -> Decimal:
        try:
            return Decimal(self.value)
        except InvalidOperation as e:
            raise ValueError(
                f"Field value {self.value!r} (raw {self.raw!r}) is not numeric"
            ) from e

    def model_post_init(self, __context):
        if self.bbox is not None and len(self.bbox) != 4:
            raise ValueError(f"bbox must have exactly 4 values, got {len(self.bbox)}")


class Coverage(BaseModel):
    pages_total: int = Field(ge=1)
    pages_examined: int = Field(ge=0)
    pages_unreadable: list[int] = Field(default_factory=list)
    coverage_complete: bool = False

    @model_validator(mode="after")
    def validate_coverage(self):
        if self.coverage_complete:
            assert self.pages_examined == self.pages_total, \
                "coverage_complete=True but pages_examined != pages_total"
            assert len(self.pages_unreadable) == 0, \
                "coverage_complete=True but pages_unreadable is not empty"
        return self


class ToleranceSpec(BaseModel):
    type: str = Field(pattern="^(absolute|relative|none)$")
    value: str = "0"
    currency_scaled: bool = False

    def as_decimal(self) -> Decimal:
        return Decimal(self.value)

    def apply(self, amount: Decimal) -> Decimal:
        if self.type == "none":
            return Decimal("0")
        if self.type == "absolute":
            return self.as_decimal()
        return amount * self.as_decimal() / Decimal("100")


# ─── Check Catalog ───────────────────────────────────────────────────────────

class CheckCatalogEntry(BaseModel):
    check_id: str = Field(pattern=r"^CHK-[A-Z]+-[A-Z]+-[0-9]{3}$")
    title: str
    category: CheckCategory
    applies_to: list[DocumentType] = Field(min_length=1)
    severity: Severity
    determinism: CheckDeterminism
    inputs: list[str] = Field(min_length=1)
    tolerance: ToleranceSpec
    failure_message: str
    requires_human_review: bool = False
    ruleset_version: str | None = None


class CheckCatalog(BaseModel):
    catalog_version: str
    created_at: datetime
    checks: list[CheckCatalogEntry]


# ─── Line Items ──────────────────────────────────────────────────────────────

class LineItem(BaseModel):
    line_number: int = Field(ge=1)
    description: ProvenancedValue
    quantity: ProvenancedValue
    unit_price: ProvenancedValue
    line_total: ProvenancedValue
    hsn_sac: ProvenancedValue | None = None

    def expected_total(self, exponent: Decimal = Decimal("0.01")) -> Decimal:
        """Quantity x unit price, quantized to the currency's minor unit.

        Callers must pass the exponent for zero-decimal (JPY) and
        three-decimal (KWD) currencies; the 2-decimal default is not universal.
        """
        qty = self.quantity.decimal_value
        price = self.unit_price.decimal_value
        return (qty * price).quantize(exponent, rounding=ROUND_HALF_UP)


class TaxLine(BaseModel):
    line_number: int = Field(ge=1)
    description: ProvenancedValue
    taxable_value: ProvenancedValue
    rate: ProvenancedValue
    cgst: ProvenancedValue
    sgst: ProvenancedValue
    total_tax: ProvenancedValue


class DocumentHeader(BaseModel):
    document_id: str
    doc_type: DocumentType
    vendor_name: ProvenancedValue | None = None
    vendor_address: ProvenancedValue | None = None
    vendor_gstin: ProvenancedValue | None = None
    buyer_name: ProvenancedValue | None = None
    buyer_gstin: ProvenancedValue | None = None
    invoice_date: ProvenancedValue | None = None
    due_date: ProvenancedValue | None = None
    po_reference: ProvenancedValue | None = None
    grand_total: ProvenancedValue | None = None
    amount_in_words: ProvenancedValue | None = None
    bank_details: dict[str, str] | None = None
    order_date: ProvenancedValue | None = None
    delivery_date: ProvenancedValue | None = None
    payment_terms: ProvenancedValue | None = None
    delivery_address: ProvenancedValue | None = None
    subtotal: ProvenancedValue | None = None
    discount_amount: ProvenancedValue | None = None
    discount_percentage: ProvenancedValue | None = None
    opening_balance: ProvenancedValue | None = None
    receipts: ProvenancedValue | None = None
    payments: ProvenancedValue | None = None
    closing_balance: ProvenancedValue | None = None
    expiry_date: ProvenancedValue | None = None
    received_date: ProvenancedValue | None = None
    grn_date: ProvenancedValue | None = None


class ExtractedDocument(BaseModel):
    document_id: str
    tenant_id: str
    doc_type: DocumentType
    header: DocumentHeader
    line_items: list[LineItem] = Field(default_factory=list)
    tax_lines: list[TaxLine] = Field(default_factory=list)
    coverage: Coverage
    page_count: int = Field(ge=1)
    extractor_version: str


# ─── Findings ────────────────────────────────────────────────────────────────

class EvidenceItem(BaseModel):
    document_id: str
    page: int = Field(ge=1)
    bbox: list[float] | None = None
    field: str
    raw: str


class Finding(BaseModel):
    finding_id: str
    check_id: str
    document_id: str
    tenant_id: str
    status: FindingStatus
    severity: Severity
    expected: str | None = None
    actual: str | None = None
    delta: str | None = None
    currency: str | None = None
    tolerance: str | None = None
    message: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    decision_fingerprint: str
    ruleset_version: str
    requires_human_review: bool = False
    supersedes: str | None = None
    created_at: datetime
    schema_version: str = "2.0"


# ─── Check Context ───────────────────────────────────────────────────────────

class CheckContext(BaseModel):
    document: ExtractedDocument
    check_entry: CheckCatalogEntry
    currency_exponent: Decimal = Decimal("0.01")
    tenant_tolerances: dict[str, str] = Field(default_factory=dict)

    def tolerance_for(self, check_id: str) -> Decimal:
        if check_id in self.tenant_tolerances:
            return Decimal(self.tenant_tolerances[check_id])
        return self.check_entry.tolerance.as_decimal()


class CheckResult(BaseModel):
    check_id: str
    status: FindingStatus
    expected: str | None = None
    actual: str | None = None
    delta: str | None = None
    message: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    requires_human_review: bool = False

    @classmethod
    def passed(cls, check_id: str, evidence: list[EvidenceItem] | None = None,
               message: str | None = None) -> CheckResult:
        return cls(
            check_id=check_id,
            status=FindingStatus.PASS,
            message=message or f"{check_id}: passed",
            evidence=evidence or [],
        )

    @classmethod
    def failed(cls, check_id: str, expected: str, actual: str, delta: str,
               evidence: list[EvidenceItem] | None = None,
               message: str | None = None,
               requires_human_review: bool = False) -> CheckResult:
        return cls(
            check_id=check_id,
            status=FindingStatus.FAIL,
            expected=expected,
            actual=actual,
            delta=delta,
            message=message or f"{check_id}: expected {expected}, actual {actual}",
            evidence=evidence or [],
            requires_human_review=requires_human_review,
        )

    @classmethod
    def skipped(cls, check_id: str, reason: str) -> CheckResult:
        return cls(
            check_id=check_id,
            status=FindingStatus.SKIPPED,
            message=reason,
        )


# ─── Decision Fingerprint ──────────────────────────────────────────────────

def make_fingerprint(ruleset_version: str, prompt_version: str,
                     model_version: str, extractor_version: str,
                     document_hash: str) -> str:
    raw = f"{ruleset_version}|{prompt_version}|{model_version}|{extractor_version}|{document_hash}"
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"
