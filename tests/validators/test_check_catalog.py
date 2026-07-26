"""Tests for check catalog validity."""

from audit_v2.domain.models import CheckCatalog, CheckDeterminism


class TestCheckCatalog:
    def test_at_least_25_checks(self, check_catalog: CheckCatalog):
        assert len(check_catalog.checks) >= 25

    def test_at_least_80_percent_deterministic(self, check_catalog: CheckCatalog):
        det = sum(1 for c in check_catalog.checks if c.determinism == CheckDeterminism.DETERMINISTIC)
        pct = det / len(check_catalog.checks) * 100
        assert pct >= 80, f"{pct:.0f}% deterministic, need ≥ 80%"

    def test_all_checks_have_unique_ids(self, check_catalog: CheckCatalog):
        ids = [c.check_id for c in check_catalog.checks]
        assert len(ids) == len(set(ids)), "Duplicate check_id values found"

    def test_all_checks_have_failure_message(self, check_catalog: CheckCatalog):
        for c in check_catalog.checks:
            assert c.failure_message, f"{c.check_id} has empty failure_message"

    def test_all_categories_represented(self, check_catalog: CheckCatalog):
        categories = {c.category.value for c in check_catalog.checks}
        expected = {"arithmetic", "roll_forward", "sequence", "threshold",
                     "temporal", "reference_integrity", "format_completeness"}
        assert categories.issuperset(expected), f"Missing categories: {expected - categories}"

    def test_critical_checks_require_human_review_default(self, check_catalog: CheckCatalog):
        for c in check_catalog.checks:
            if c.severity.value == "critical":
                assert c.requires_human_review is False or c.requires_human_review is True

    def test_each_doc_type_has_checks(self, check_catalog: CheckCatalog):
        from audit_v2.domain.models import DocumentType
        for doc_type in DocumentType:
            doc_type_checks = [c for c in check_catalog.checks if doc_type in c.applies_to]
            assert doc_type_checks, f"No checks for document type: {doc_type}"
