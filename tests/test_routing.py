from __future__ import annotations

from decimal import Decimal

from audit_v2.domain.models import DocumentType
from audit_v2.routing.engine import load_rules, resolve
from audit_v2.routing.models import RoutingRule

SAMPLE_CATALOG = [
    "CHK-ARITH-LINE-001",
    "CHK-ARITH-TAX-001",
    "CHK-ARITH-GRAND-001",
    "CHK-REF-PO-001",
    "CHK-FORMAT-FIELDS-001",
    "CHK-DUP-001",
]

INVOICE_RULE = RoutingRule(
    rule_id="ROUTE-INV-001",
    doc_type="invoice",
    value_band_min="0",
    value_band_max="1000000000",
    tenant_policy="standard",
    include_checks=[
        "CHK-ARITH-LINE-001",
        "CHK-ARITH-TAX-001",
        "CHK-FORMAT-FIELDS-001",
    ],
    exclude_checks=["CHK-REF-PO-001"],
)

PO_RULE = RoutingRule(
    rule_id="ROUTE-PO-001",
    doc_type="purchase_order",
    value_band_min="0",
    value_band_max="1000000000",
    tenant_policy="standard",
    include_checks=["CHK-ARITH-LINE-001"],
)

RULES = [INVOICE_RULE, PO_RULE]


class TestResolve:
    def test_resolve_invoice_standard(self):
        decision = resolve(
            DocumentType.INVOICE, Decimal(1000), "standard", SAMPLE_CATALOG, RULES,
        )
        assert decision.rule_id == "ROUTE-INV-001"
        assert "CHK-ARITH-LINE-001" in decision.included_check_ids
        assert "CHK-REF-PO-001" in decision.skipped_check_ids
        assert "Excluded per routing rule" in decision.skipped_check_ids["CHK-REF-PO-001"]

    def test_resolve_po_standard(self):
        decision = resolve(
            DocumentType.PURCHASE_ORDER, Decimal(1000), "standard", SAMPLE_CATALOG, RULES,
        )
        assert decision.rule_id == "ROUTE-PO-001"
        assert "CHK-ARITH-LINE-001" in decision.included_check_ids

    def test_resolve_excluded_checks_have_reason(self):
        decision = resolve(
            DocumentType.INVOICE, Decimal(1000), "standard", SAMPLE_CATALOG, RULES,
        )
        assert decision.skipped_check_ids["CHK-REF-PO-001"] != ""

    def test_resolve_same_input_same_output(self):
        d1 = resolve(
            DocumentType.INVOICE, Decimal(1000), "standard", SAMPLE_CATALOG, RULES,
        )
        d2 = resolve(
            DocumentType.INVOICE, Decimal(1000), "standard", SAMPLE_CATALOG, RULES,
        )
        assert d1.rule_id == d2.rule_id
        assert d1.included_check_ids == d2.included_check_ids

    def test_resolve_skipped_checks_not_in_catalog(self):
        other_catalog = ["CHK-DUP-001"]
        decision = resolve(
            DocumentType.INVOICE, Decimal(1000), "standard", other_catalog, RULES,
        )
        assert "CHK-DUP-001" in decision.skipped_check_ids

    def test_unknown_doc_type_returns_no_rule(self):
        decision = resolve(
            DocumentType.GOODS_RECEIPT_NOTE, Decimal(1000), "standard",
            SAMPLE_CATALOG, RULES,
        )
        assert decision.rule_id == "NO_RULE"
        assert len(decision.included_check_ids) == 0

    def test_decision_records_rule_id(self):
        decision = resolve(
            DocumentType.INVOICE, Decimal(1000), "standard", SAMPLE_CATALOG, RULES,
        )
        assert isinstance(decision.rule_id, str)
        assert len(decision.rule_id) > 0

    def test_value_band_excludes(self):
        small_value_rule = RoutingRule(
            rule_id="ROUTE-SMALL",
            doc_type="invoice",
            value_band_min="0",
            value_band_max="100",
            tenant_policy="standard",
            include_checks=["CHK-DUP-001"],
        )
        decision = resolve(
            DocumentType.INVOICE, Decimal(500), "standard",
            SAMPLE_CATALOG, [small_value_rule],
        )
        assert decision.rule_id == "NO_RULE"

    def test_none_total_matches_any_value_band(self):
        decision = resolve(
            DocumentType.INVOICE, None, "standard", SAMPLE_CATALOG, RULES,
        )
        assert decision.rule_id == "ROUTE-INV-001"


class TestLoadRules:
    def test_load_rules_from_yaml(self):
        rules = load_rules()
        assert len(rules) >= 1
        assert all(isinstance(r, RoutingRule) for r in rules)
