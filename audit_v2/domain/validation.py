import logging
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from audit_v2.domain.models import (
    CheckCatalogEntry,
    CheckContext,
    CheckResult,
    CorpusIndex,
    ExtractedDocument,
    FindingStatus,
    TransactionCluster,
)

logger = logging.getLogger(__name__)

VALIDATOR_REGISTRY: dict[str, Callable[[CheckContext], CheckResult]] = {}


def register_validator(check_id: str, fn: Callable[[CheckContext], CheckResult]) -> None:
    VALIDATOR_REGISTRY[check_id] = fn


def _import_validators() -> None:
    from audit_v2.domain.validators import (
        arithmetic,
        certificate,
        duplicate,
        format_completeness,
        reference_integrity,
        rollforward,
        sequence,
        temporal,
        threeway,
        threshold,
    )

    for check_id, fn in [
        ("CHK-ARITH-LINE-001", arithmetic.check_line_total),
        ("CHK-ARITH-SUBTOTAL-001", arithmetic.check_subtotal_tieout),
        ("CHK-ARITH-TAX-001", arithmetic.check_tax_rate),
        ("CHK-ARITH-TAX-002", arithmetic.check_tax_calculation),
        ("CHK-ARITH-DISCOUNT-001", arithmetic.check_discount_cap),
        ("CHK-ARITH-GRAND-001", arithmetic.check_grand_total),
        ("CHK-ARITH-ROUNDING-001", arithmetic.check_rounding_accumulation),
        ("CHK-RFWD-BALANCE-001", rollforward.check_balance_roll_forward),
        ("CHK-SEQ-INVNUM-001", sequence.check_invoice_sequence),
        ("CHK-SEQ-PONUM-001", sequence.check_po_sequence),
        ("CHK-SEQ-CHALLAN-001", sequence.check_challan_sequence),
        ("CHK-THRESHOLD-LINE-001", threshold.check_line_threshold),
        ("CHK-THRESHOLD-DISC-001", threshold.check_discount_threshold),
        ("CHK-THRESHOLD-TAXRATE-001", threshold.check_tax_rate_threshold),
        ("CHK-TEMP-INVDATE-001", temporal.check_invoice_date),
        ("CHK-TEMP-PODATE-001", temporal.check_po_date),
        ("CHK-TEMP-DELIVERY-001", temporal.check_delivery_date),
        ("CHK-TEMP-EXPIRY-001", temporal.check_expiry_date),
        ("CHK-REF-PO-001", reference_integrity.check_po_reference),
        ("CHK-REF-GST-001", reference_integrity.check_gstin_format),
        ("CHK-REF-HSN-001", reference_integrity.check_hsn_code),
        ("CHK-REF-BANK-001", reference_integrity.check_bank_details),
        ("CHK-REF-QTY-001", reference_integrity.check_quantity_po),
        ("CHK-REF-QTY-002", reference_integrity.check_quantity_dc),
        ("CHK-FORMAT-MANDATORY-001", format_completeness.check_mandatory_fields),
        ("CHK-FORMAT-MANDATORY-002", format_completeness.check_line_item_fields),
        ("CHK-FORMAT-TAXBREAKDOWN-001", format_completeness.check_tax_breakdown),
        ("CHK-FORMAT-CURRENCY-001", format_completeness.check_currency_format),
        ("CHK-FORMAT-WORDS-001", format_completeness.check_amount_in_words),
        ("CHK-DUP-DOC-001", duplicate.check_duplicate_document),
        ("CHK-XDOC-QTY-001", threeway.check_invoiced_vs_received),
        ("CHK-XDOC-PRICE-001", threeway.check_price_matches_po),
        ("CHK-XDOC-RECEIPT-001", threeway.check_receipt_exists),
        ("CHK-XDOC-CUMUL-001", threeway.check_cumulative_invoiced),
        ("CHK-CERT-MANDATORY-001", certificate.check_certificate_mandatory),
        ("CHK-CERT-GOODS-001", certificate.check_certificate_goods),
        ("CHK-CERT-REFERENCE-001", certificate.check_certificate_invoice_reference),
    ]:
        register_validator(check_id, fn)


class CheckRunner:
    def __init__(self, catalog_checks: list[CheckCatalogEntry]):
        self._catalog = {c.check_id: c for c in catalog_checks}

    def run_all(
        self,
        document: ExtractedDocument,
        included_check_ids: list[str],
        skipped_check_ids: dict[str, str],
        currency_exponent: Decimal = Decimal("0.01"),
        tenant_tolerances: dict[str, str] | None = None,
        cluster: TransactionCluster | None = None,
        corpus_index: CorpusIndex | None = None,
        current_date: date | None = None,
    ) -> list[CheckResult]:
        if not VALIDATOR_REGISTRY:
            _import_validators()

        results: list[CheckResult] = []
        tenant_tolerances = tenant_tolerances or {}

        for check_id in included_check_ids:
            if check_id not in VALIDATOR_REGISTRY:
                logger.error(
                    "Check %s was routed for execution but has no registered validator",
                    check_id,
                )
                results.append(CheckResult(
                    check_id=check_id,
                    status=FindingStatus.NEEDS_REVIEW,
                    message=f"No validator registered for {check_id}",
                    requires_human_review=True,
                ))
                continue

            check_entry = self._catalog.get(check_id)
            if check_entry is None:
                results.append(CheckResult(
                    check_id=check_id,
                    status=FindingStatus.SKIPPED,
                    message=f"Check {check_id} not found in catalog",
                ))
                continue

            ctx = CheckContext(
                document=document,
                check_entry=check_entry,
                currency_exponent=currency_exponent,
                tenant_tolerances=tenant_tolerances,
                cluster=cluster,
                corpus_index=corpus_index,
                current_date=current_date,
            )

            try:
                result = VALIDATOR_REGISTRY[check_id](ctx)
            except (KeyboardInterrupt, SystemExit, MemoryError):
                raise
            except Exception as exc:
                # PHASES_V2 §3.3 LOGIC class: an internal invariant violation must
                # fail loudly, never silently degrade. Emitting FAIL here would make
                # a code bug indistinguishable from a genuine document defect.
                logger.exception("Validator %s raised on document %s",
                                 check_id, document.document_id)
                result = CheckResult(
                    check_id=check_id,
                    status=FindingStatus.NEEDS_REVIEW,
                    message=f"Validator error ({type(exc).__name__}): {exc}",
                    requires_human_review=True,
                )

            results.append(result)

        for check_id, reason in skipped_check_ids.items():
            results.append(CheckResult(
                check_id=check_id,
                status=FindingStatus.SKIPPED,
                message=reason,
            ))

        return results
