"""Consistency between the check catalog, the validator registry, and routing.

These are the tests that make silent degradation visible: an unimplemented
check, a routing rule naming a check that does not exist, or a check routed to
a document type it does not apply to.
"""
from decimal import Decimal

import pytest

from audit_v2.domain.catalog_loader import load_catalog
from audit_v2.domain.models import CheckDeterminism, DocumentType
from audit_v2.domain.validation import VALIDATOR_REGISTRY, _import_validators
from audit_v2.routing.engine import load_rules, resolve


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def registry():
    _import_validators()
    return VALIDATOR_REGISTRY


def test_every_deterministic_check_has_a_validator(catalog, registry):
    missing = [
        c.check_id
        for c in catalog.checks
        if c.determinism == CheckDeterminism.DETERMINISTIC
        and c.check_id not in registry
    ]
    assert missing == [], f"Deterministic checks with no validator: {missing}"


def test_no_validator_registered_for_unknown_check(catalog, registry):
    catalog_ids = {c.check_id for c in catalog.checks}
    orphans = sorted(set(registry) - catalog_ids)
    assert orphans == [], f"Validators registered for checks absent from catalog: {orphans}"


def test_routing_rules_only_reference_catalog_checks(catalog):
    catalog_ids = {c.check_id for c in catalog.checks}
    bad: list[str] = []
    for rule in load_rules():
        for cid in list(rule.include_checks) + list(rule.exclude_checks):
            if cid not in catalog_ids:
                bad.append(f"{rule.rule_id} -> {cid}")
    assert bad == [], f"Routing rules reference non-existent checks: {bad}"


def test_routing_rules_respect_applies_to(catalog):
    entries = {c.check_id: c for c in catalog.checks}
    bad: list[str] = []
    for rule in load_rules():
        doc_type = DocumentType(rule.doc_type)
        for cid in rule.include_checks:
            if doc_type not in entries[cid].applies_to:
                bad.append(f"{rule.rule_id} includes {cid}, not applicable to {doc_type.value}")
    assert bad == [], f"Routing includes inapplicable checks: {bad}"


@pytest.mark.parametrize("doc_type", list(DocumentType))
def test_every_doc_type_routes_to_a_rule(doc_type, catalog):
    applicable = [
        c.check_id
        for c in catalog.checks
        if c.determinism == CheckDeterminism.DETERMINISTIC and doc_type in c.applies_to
    ]
    decision = resolve(doc_type, Decimal("1000"), "standard", applicable)
    assert decision.rule_id != "NO_RULE", f"No routing rule for {doc_type.value}"
    assert decision.included_check_ids, f"{doc_type.value} routed to zero checks"


@pytest.mark.parametrize("doc_type", list(DocumentType))
def test_routing_accounts_for_every_applicable_check(doc_type, catalog):
    """No check may vanish: each is either run or explicitly skipped with a reason."""
    applicable = [
        c.check_id
        for c in catalog.checks
        if c.determinism == CheckDeterminism.DETERMINISTIC and doc_type in c.applies_to
    ]
    decision = resolve(doc_type, Decimal("1000"), "standard", applicable)
    accounted = set(decision.included_check_ids) | set(decision.skipped_check_ids)
    assert set(applicable) - accounted == set(), (
        f"{doc_type.value}: checks neither run nor skipped"
    )


def test_routing_is_deterministic(catalog):
    applicable = [c.check_id for c in catalog.checks]
    first = resolve(DocumentType.INVOICE, Decimal("5000"), "standard", applicable)
    for _ in range(5):
        again = resolve(DocumentType.INVOICE, Decimal("5000"), "standard", applicable)
        assert again.rule_id == first.rule_id
        assert again.included_check_ids == first.included_check_ids
        assert again.skipped_check_ids == first.skipped_check_ids
