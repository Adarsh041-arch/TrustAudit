"""Property-based tests — hypothesis was a declared dependency but unused.

Targets the two places where a silent wrong answer is most costly: locale-aware
money parsing, and the arithmetic validators that decide audit verdicts.
"""
from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from audit_v2.domain.catalog_loader import load_catalog
from audit_v2.domain.models import (
    CheckContext,
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    FindingStatus,
    LineItem,
    ProvenancedValue,
)
from audit_v2.domain.validators.arithmetic import check_line_total, check_subtotal_tieout
from audit_v2.extraction.parser import parse_amount

_CATALOG = {c.check_id: c for c in load_catalog().checks}

money = st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("999999.99"),
    places=2, allow_nan=False, allow_infinity=False,
)
qty = st.decimals(
    min_value=Decimal("1"), max_value=Decimal("1000"),
    places=0, allow_nan=False, allow_infinity=False,
)


def _pv(value: str) -> ProvenancedValue:
    return ProvenancedValue(value=value, raw=value, page=1)


def _doc(lines: list[LineItem], subtotal: str | None = None) -> ExtractedDocument:
    header = DocumentHeader(document_id="d", doc_type=DocumentType.INVOICE)
    if subtotal is not None:
        header.subtotal = _pv(subtotal)
    return ExtractedDocument(
        document_id="d", tenant_id="t", doc_type=DocumentType.INVOICE,
        header=header, line_items=lines,
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1, extractor_version="2.1.0",
    )


def _ctx(doc: ExtractedDocument, check_id: str) -> CheckContext:
    return CheckContext(document=doc, check_entry=_CATALOG[check_id])


@given(q=qty, price=money)
@settings(max_examples=200)
def test_consistent_line_never_fails(q, price):
    """A line whose stated total is exactly qty x price must never FAIL."""
    total = (q * price).quantize(Decimal("0.01"))
    line = LineItem(
        line_number=1, description=_pv("Widget"),
        quantity=_pv(str(q)), unit_price=_pv(str(price)), line_total=_pv(str(total)),
    )
    result = check_line_total(_ctx(_doc([line]), "CHK-ARITH-LINE-001"))
    assert result.status == FindingStatus.PASS


@given(q=qty, price=money, drift=money)
@settings(max_examples=200)
def test_inconsistent_line_always_fails(q, price, drift):
    """Any stated total differing from qty x price must FAIL — no tolerance leak."""
    correct = (q * price).quantize(Decimal("0.01"))
    stated = correct + drift
    assume(stated != correct)
    line = LineItem(
        line_number=1, description=_pv("Widget"),
        quantity=_pv(str(q)), unit_price=_pv(str(price)), line_total=_pv(str(stated)),
    )
    result = check_line_total(_ctx(_doc([line]), "CHK-ARITH-LINE-001"))
    assert result.status == FindingStatus.FAIL


@given(totals=st.lists(money, min_size=1, max_size=8))
@settings(max_examples=100)
def test_subtotal_matching_line_sum_passes(totals):
    lines = [
        LineItem(
            line_number=i + 1, description=_pv("W"),
            quantity=_pv("1"), unit_price=_pv(str(t)), line_total=_pv(str(t)),
        )
        for i, t in enumerate(totals)
    ]
    subtotal = sum(totals)
    result = check_subtotal_tieout(
        _ctx(_doc(lines, subtotal=str(subtotal)), "CHK-ARITH-SUBTOTAL-001")
    )
    assert result.status == FindingStatus.PASS


@given(st.text(max_size=30))
@settings(max_examples=300)
def test_parse_amount_never_raises(raw):
    """parse_amount must return None on junk, never propagate an exception."""
    result = parse_amount(raw)
    assert result is None or isinstance(result, Decimal)


@given(value=money)
@settings(max_examples=200)
def test_parse_amount_roundtrips_plain_decimal(value):
    assert parse_amount(str(value)) == value


@given(whole=st.integers(min_value=1, max_value=999), cents=st.integers(0, 99))
@settings(max_examples=200)
def test_en_us_and_de_de_grouping_agree(whole, cents):
    """The same magnitude written in two locales must normalize identically."""
    en_us = f"{whole:,}.{cents:02d}"
    de_de = f"{whole:,}".replace(",", ".") + f",{cents:02d}"
    assert parse_amount(en_us, "en-US") == parse_amount(de_de, "de-DE")
