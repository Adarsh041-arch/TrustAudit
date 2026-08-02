from __future__ import annotations

from audit_v2.gateway.pii_redactor import classify_pii, redact


class TestClassifyPII:
    def test_classify_gstin(self):
        text = "GSTIN: 27AAAPL1234C1Z2"
        result = classify_pii(text)
        assert "gstin" in result
        assert len(result["gstin"]) == 1

    def test_classify_pan(self):
        text = "PAN: AAPPL1234C"
        result = classify_pii(text)
        assert "pan" in result

    def test_classify_ifsc(self):
        text = "IFSC: SBIN0001234"
        result = classify_pii(text)
        assert "ifsc" in result

    def test_classify_email(self):
        text = "Email: test@example.com"
        result = classify_pii(text)
        assert "email" in result

    def test_classify_phone(self):
        text = "Phone: +91 9876543210"
        result = classify_pii(text)
        assert "phone" in result

    def test_classify_bank_account(self):
        text = "Account: 123456789012345678"
        result = classify_pii(text)
        assert "bank_account" in result

    def test_no_pii_returns_empty(self):
        result = classify_pii("This is a regular sentence about widgets.")
        assert all(len(v) == 0 for v in result.values()) if result else True


class TestRedact:
    def test_redact_gstin(self):
        result = redact("GSTIN: 27ATAPL1119C1Z5")
        assert "27ATAPL1119C1Z5" not in result
        assert "[REDACTED_GSTIN]" in result

    def test_redact_multiple_pii(self):
        result = redact("GSTIN: 27ATAPL1119C1Z5, Email: test@example.com")
        assert "[REDACTED_GSTIN]" in result
        assert "[REDACTED_EMAIL]" in result

    def test_redact_selective_classes(self):
        result = redact(
            "GSTIN: 27ATAPL1119C1Z5, Email: test@example.com",
            pii_classes=["gstin"],
        )
        assert "[REDACTED_GSTIN]" in result
        assert "test@example.com" in result

    def test_redact_leaves_structure_intact(self):
        original = "header: value\nGSTIN: 27ATAPL1119C1Z5\namount: 1500.00"
        result = redact(original)
        assert "header:" in result
        assert "amount: 1500.00" in result
        assert result.count("[REDACTED_GSTIN]") == 1

    def test_redact_no_false_positives_on_amounts(self):
        result = redact("Amount: 1000.50")
        assert "1000.50" in result

    def test_redact_empty_string(self):
        result = redact("")
        assert result == ""