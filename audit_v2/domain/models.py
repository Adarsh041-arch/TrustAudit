from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

# ─── Enums ────────────────────────────────────────────────────────────────────

class DocumentType(StrEnum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    DELIVERY_CHALLAN = "delivery_challan"
    GOODS_RECEIPT_NOTE = "goods_receipt_note"
    CONTRACT = "contract"
    LETTER = "letter"
    CERTIFICATE_OF_ORIGIN = "certificate_of_origin"
    UNKNOWN = "unknown"


#: Free-text document types — VLM-only extraction (report + key fields).
TEXT_DOC_TYPES = frozenset({
    DocumentType.CONTRACT,
    DocumentType.LETTER,
    DocumentType.CERTIFICATE_OF_ORIGIN,
    DocumentType.UNKNOWN,
})


class ClassificationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTED = "CONFLICTED"
    UNSUPPORTED = "UNSUPPORTED"


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
    UNSUPPORTED = "UNSUPPORTED"


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

    def model_post_init(self, __context: object) -> None:
        if self.bbox is not None and len(self.bbox) != 4:
            raise ValueError(f"bbox must have exactly 4 values, got {len(self.bbox)}")


class Coverage(BaseModel):
    pages_total: int = Field(ge=1)
    pages_examined: int = Field(ge=0)
    pages_unreadable: list[int] = Field(default_factory=list)
    coverage_complete: bool = False

    @model_validator(mode="after")
    def validate_coverage(self) -> Coverage:

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
    quantity_unit: ProvenancedValue | None = None

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


class CertificateGoodsItem(BaseModel):
    line_number: int = Field(ge=1)
    description: ProvenancedValue
    hs_code: ProvenancedValue
    quantity: ProvenancedValue
    quantity_unit: ProvenancedValue | None = None
    invoice_number: ProvenancedValue | None = None
    invoice_date: ProvenancedValue | None = None


class ClassificationEvidence(BaseModel):
    page: int = Field(ge=1)
    text: str


class DocumentHeader(BaseModel):
    document_id: str
    doc_type: DocumentType
    vendor_name: ProvenancedValue | None = None
    vendor_address: ProvenancedValue | None = None
    vendor_gstin: ProvenancedValue | None = None
    buyer_name: ProvenancedValue | None = None
    buyer_gstin: ProvenancedValue | None = None
    invoice_number: ProvenancedValue | None = None
    po_number: ProvenancedValue | None = None
    challan_number: ProvenancedValue | None = None
    grn_number: ProvenancedValue | None = None
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
    certificate_number: ProvenancedValue | None = None
    certificate_date: ProvenancedValue | None = None
    exporter_name: ProvenancedValue | None = None
    exporter_address: ProvenancedValue | None = None
    consignee_name: ProvenancedValue | None = None
    consignee_address: ProvenancedValue | None = None
    country_of_origin: ProvenancedValue | None = None
    referenced_invoice_number: ProvenancedValue | None = None
    referenced_invoice_date: ProvenancedValue | None = None
    issuing_authority: ProvenancedValue | None = None
    signature_present: bool | None = None
    seal_present: bool | None = None

    @field_validator("bank_details", mode="before")
    @classmethod
    def _clean_bank_details(cls, v: object) -> dict[str, str] | None:
        """Normalize model-supplied bank details to ``dict[str, str] | None``.

        VLMs emit ``{"account_number": null, "ifsc": null}`` for documents with
        no bank block (e.g. export invoices), which violates the ``str`` value
        type. Drop null/empty entries and coerce the rest to strings; an
        all-empty block collapses to ``None``.
        """
        if not isinstance(v, dict):
            return None
        cleaned = {
            str(k): str(val).strip()
            for k, val in v.items()
            if val is not None and str(val).strip() != ""
        }
        return cleaned or None


class ExtractedDocument(BaseModel):
    document_id: str
    tenant_id: str
    doc_type: DocumentType
    header: DocumentHeader
    line_items: list[LineItem] = Field(default_factory=list)
    tax_lines: list[TaxLine] = Field(default_factory=list)
    certificate_goods: list[CertificateGoodsItem] = Field(default_factory=list)
    coverage: Coverage
    page_count: int = Field(ge=1)
    extractor_version: str
    # Actual vision model used for extraction. None for deterministic-only reads.
    model_version: str | None = None
    # Structured candidates rejected because they were absent from raw OCR text.
    grounding_rejections: list[str] = Field(default_factory=list)
    # VLM-only text documents (contract/letter): free-text narrative report.
    narrative_report: str | None = None
    # Dual extraction (regex + VLM): fields where the two methods disagreed.
    # field_name -> "regex_value vs vlm_value". Non-empty => human review.
    extraction_disagreements: dict[str, str] = Field(default_factory=dict)
    classification_status: ClassificationStatus = ClassificationStatus.CONFIRMED
    classification_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    classification_method: str = "provided"
    classification_evidence: list[ClassificationEvidence] = Field(default_factory=list)
    alternative_types: list[DocumentType] = Field(default_factory=list)
    extraction_strategy: str = "unsupported"
    vision_backend: str | None = None
    vision_call_count: int = Field(default=0, ge=0)
    # Compatibility counter retained for existing V2 clients.
    glm_call_count: int = Field(default=0, ge=0)
    structured_fallback_used: bool = False
    transcript_cache_hit: bool = False
    extraction_latency_ms: float = Field(default=0.0, ge=0.0)
    fallback_reasons: list[str] = Field(default_factory=list)


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "2.0"



# ─── Correlation (Phase 7) ──────────────────────────────────────────────────

class LinkMethod(StrEnum):
    EXPLICIT_REFERENCE = "explicit_reference"      # invoice cites PO number
    VENDOR_AMOUNT_DATE = "vendor_amount_date"      # (vendor, amount, date-window)
    FUZZY = "fuzzy"                                # vendor + line-description match


class DocumentLink(BaseModel):
    document_id: str
    doc_type: DocumentType
    method: LinkMethod
    confidence: float = Field(ge=0.0, le=1.0)


class TransactionCluster(BaseModel):
    """Documents linked by shared business keys — the unit of three-way match.

    PHASES_V2 §4 Phase 7: every link records its method and confidence;
    low-confidence links route to human review rather than being asserted.
    """
    cluster_id: str
    links: list[DocumentLink] = Field(default_factory=list)
    documents: list[ExtractedDocument] = Field(default_factory=list)

    def of_type(self, doc_type: DocumentType) -> list[ExtractedDocument]:
        return [d for d in self.documents if d.doc_type == doc_type]

    @property
    def purchase_order(self) -> ExtractedDocument | None:
        pos = self.of_type(DocumentType.PURCHASE_ORDER)
        return pos[0] if pos else None


class CorpusIndex(BaseModel):
    """Per-tenant duplicate-detection index (PHASES_V2 §4 Phase 6).

    Keys are pre-normalized strings so the index is serializable and the
    lookups deterministic.
    """
    # "vendor||docnum" -> list of document_ids carrying that number
    by_vendor_docnum: dict[str, list[str]] = Field(default_factory=dict)
    # "vendor||doc_type||amount||date" -> list of document_ids. Type-scoped so
    # a PO/contract/certificate sharing an invoice's amount+date is not a dup.
    by_vendor_amount_date: dict[str, list[str]] = Field(default_factory=dict)


# ─── Check Context ───────────────────────────────────────────────────────────

class CheckContext(BaseModel):
    document: ExtractedDocument
    check_entry: CheckCatalogEntry
    currency_exponent: Decimal = Decimal("0.01")
    tenant_tolerances: dict[str, str] = Field(default_factory=dict)
    # Phase 7: corpus-level context. None on single-document runs — validators
    # that need it SKIP with an explicit reason when absent.
    cluster: TransactionCluster | None = None
    corpus_index: CorpusIndex | None = None
    current_date: date | None = None

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
