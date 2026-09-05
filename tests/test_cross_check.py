"""Tests for the LLM cross-check and deterministic-authority reconciliation
(new_requirements.md §5, plan §8).

Two concerns:
- ``run_cross_check`` degrades offline and coerces a small model's loose output
  into the strict :class:`Contradiction` domain type (valid enums, clamped
  confidence, injected document_id).
- the server reconciles contradictions so the LLM can never overturn or
  double-count a deterministic FAIL, and a contradiction is only ever advisory
  (NEEDS_REVIEW), never a FAIL.
"""

from __future__ import annotations

import json

from audit_v2 import server
from audit_v2.domain.evidence import Contradiction, EvidenceNature, PipelineEvidence
from audit_v2.domain.models import (
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    Finding,
    FindingStatus,
    Severity,
)
from audit_v2.pipeline.cross_check import run_cross_check


def _evidence(document_id: str = "doc1") -> PipelineEvidence:
    return PipelineEvidence(
        document_id=document_id,
        nature=EvidenceNature.ARITHMETIC_COMPUTATION,
        source="arithmetic",
        payload={"expected_grand_total": "250.00", "stated_grand_total": "9999.00"},
        summary="expected 250 vs stated 9999",
    )


def _doc(document_id: str) -> ExtractedDocument:
    return ExtractedDocument(
        document_id=document_id, tenant_id="t", doc_type=DocumentType.INVOICE,
        header=DocumentHeader(document_id=document_id, doc_type=DocumentType.INVOICE),
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1, extractor_version="test",
    )


def _fail(check_id: str, document_id: str = "doc1") -> Finding:
    return Finding(
        finding_id=f"f_{check_id}", check_id=check_id, document_id=document_id,
        tenant_id="t", status=FindingStatus.FAIL, severity=Severity.CRITICAL,
        message="deterministic fail", decision_fingerprint=f"det:{check_id}",
        ruleset_version="ruleset_v2.0",
    )


# ─── run_cross_check: graceful degradation + coercion ────────────────────────


def test_cross_check_no_evidence_is_supported() -> None:
    result = run_cross_check([], "doc1", DocumentType.INVOICE, "t")
    assert result.supported is True
    assert result.contradictions == []


def test_cross_check_skips_without_gateway_or_key() -> None:
    # Hermetic fixture removed NVIDIA_API_KEY; no gateway injected → skip cleanly.
    result = run_cross_check([_evidence()], "doc1", DocumentType.INVOICE, "t")
    assert result.supported is True
    assert result.contradictions == []
    assert "skipped" in result.summary.lower()


def test_cross_check_coerces_loose_llm_output(make_gateway) -> None:
    reply = json.dumps(
        {
            "supported": False,
            "contradictions": [
                {
                    "nature": "arithmetic",  # synonym → ARITHMETIC_COMPUTATION
                    "evidence": "grand_total 9999 vs computed 250",
                    "reason": "stated total disagrees with the arithmetic sum",
                    "confidence": 1.7,  # clamped to 1.0
                    "severity": "CRITICAL",  # upper-case → Severity.CRITICAL
                    "conflicting_with": "arithmetic_computation",
                }
            ],
            "summary": "totals disagree",
        }
    )
    result = run_cross_check(
        [_evidence()], "doc1", DocumentType.INVOICE, "t", gateway=make_gateway(reply),
    )
    assert result.supported is False
    assert len(result.contradictions) == 1
    c = result.contradictions[0]
    assert c.nature == EvidenceNature.ARITHMETIC_COMPUTATION
    assert c.severity == Severity.CRITICAL
    assert c.confidence == 1.0
    assert c.document_id == "doc1"


def test_cross_check_survives_bad_reply(make_gateway) -> None:
    # Unparseable reply on every attempt → advisory, empty, never raises.
    result = run_cross_check(
        [_evidence()], "doc1", DocumentType.INVOICE, "t",
        gateway=make_gateway("not json", "still not json"),
    )
    assert result.supported is True
    assert result.contradictions == []


# ─── deterministic authority (server reconciliation) ─────────────────────────


def test_contradiction_overlapping_deterministic_fail_is_dropped() -> None:
    arith_fail = _fail("CHK-ARITH-LINE-001")
    arith_c = Contradiction(
        document_id="doc1", nature=EvidenceNature.ARITHMETIC_COMPUTATION,
        evidence="line total off", reason="r", severity=Severity.LOW,
    )
    # An arithmetic contradiction is redundant once an arithmetic check FAILED.
    assert server._contradiction_overlaps_fail(arith_c, [arith_fail]) is True
    # With no deterministic fail it stands.
    assert server._contradiction_overlaps_fail(arith_c, []) is False


def test_contradiction_of_unmapped_nature_is_never_dropped() -> None:
    # VLM-observation contradictions have no deterministic counterpart → kept.
    vlm_c = Contradiction(
        document_id="doc1", nature=EvidenceNature.VLM_OBSERVATIONS,
        evidence="e", reason="r",
    )
    assert server._contradiction_overlaps_fail(vlm_c, [_fail("CHK-ARITH-LINE-001")]) is False


def test_extracted_fields_contradiction_overlaps_format_fail() -> None:
    fields_c = Contradiction(
        document_id="doc1", nature=EvidenceNature.EXTRACTED_FIELDS,
        evidence="e", reason="r",
    )
    assert server._contradiction_overlaps_fail(fields_c, [_fail("CHK-FORMAT-GSTIN-001")]) is True


def test_contradiction_to_finding_is_advisory_only() -> None:
    c = Contradiction(
        document_id="doc1", nature=EvidenceNature.VLM_OBSERVATIONS,
        evidence="the evidence", reason="the reason", severity=Severity.HIGH,
    )
    finding = server._contradiction_to_finding(c, _doc("doc1"), "t", 0)
    # The LLM only augments: NEEDS_REVIEW, never FAIL; carries its own severity.
    assert finding.status == FindingStatus.NEEDS_REVIEW
    assert finding.requires_human_review is True
    assert finding.severity == Severity.HIGH
    assert finding.check_id.startswith(server.CROSSCHECK_CHECK_PREFIX)
