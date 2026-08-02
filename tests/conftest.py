"""Pytest configuration for audit_v2 tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from audit_v2.domain.models import (
    CheckCatalog,
    CheckCatalogEntry,
    Coverage,
    DocumentHeader,
    DocumentType,
    EvidenceItem,
    ExtractedDocument,
    LineItem,
    ProvenancedValue,
    ToleranceSpec,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def check_catalog() -> CheckCatalog:
    path = REPO_ROOT / "contracts" / "check_catalog.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return CheckCatalog(**data)


@pytest.fixture
def sample_line_item() -> LineItem:
    return LineItem(
        line_number=1,
        description=ProvenancedValue(value="Widget A", raw="Widget A", page=1, confidence=0.98),
        quantity=ProvenancedValue(value="5", raw="5", page=1, confidence=0.99),
        unit_price=ProvenancedValue(value="30.00", raw="$30.00", currency="USD", page=1, confidence=0.97),
        line_total=ProvenancedValue(value="150.00", raw="$150.00", currency="USD", page=1, confidence=0.97),
        hsn_sac=ProvenancedValue(value="8471", raw="8471", page=1, confidence=0.81),
    )


@pytest.fixture
def sample_coverage_full() -> Coverage:
    return Coverage(pages_total=5, pages_examined=5, pages_unreadable=[], coverage_complete=True)


@pytest.fixture
def sample_coverage_partial() -> Coverage:
    return Coverage(pages_total=18, pages_examined=10, pages_unreadable=[11], coverage_complete=False)


@pytest.fixture
def empty_tolerance() -> ToleranceSpec:
    return ToleranceSpec(type="absolute", value="0.00", currency_scaled=True)


@pytest.fixture
def sample_evidence() -> list[EvidenceItem]:
    return [
        EvidenceItem(document_id="doc_001", page=1, bbox=[100, 200, 150, 220], field="quantity", raw="5"),
        EvidenceItem(document_id="doc_001", page=1, bbox=[160, 200, 220, 220], field="unit_price", raw="$30.00"),
    ]


@pytest.fixture
def catalog_entry_arithmetic() -> CheckCatalogEntry:
    return CheckCatalogEntry(
        check_id="CHK-ARITH-LINE-001",
        title="Line-item total equals quantity times unit price",
        category="arithmetic",
        applies_to=["invoice", "purchase_order"],
        severity="critical",
        determinism="deterministic",
        inputs=["line_items"],
        tolerance=ToleranceSpec(type="absolute", value="0.00", currency_scaled=True),
        failure_message="Line {n}: {qty} x {unit_price} = {expected}, stated {actual}",
    )


@pytest.fixture
def deterministic_checks(check_catalog: CheckCatalog) -> list[CheckCatalogEntry]:
    return [c for c in check_catalog.checks if c.determinism.value == "deterministic"]


@pytest.fixture
def all_check_ids(check_catalog: CheckCatalog) -> set[str]:
    return {c.check_id for c in check_catalog.checks}
