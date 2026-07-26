from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from audit_v2.domain.models import (
    Coverage,
    DocumentHeader,
    DocumentStatus,
    ExtractedDocument,
)


# ─── State machine tests ───────────────────────────────────────────────────


class TestDocumentStateTransitions:
    INGESTION_STATES = [
        DocumentStatus.RECEIVED,
        DocumentStatus.VALIDATED,
        DocumentStatus.SCANNED,
        DocumentStatus.RENDERED,
        DocumentStatus.EXTRACTED,
        DocumentStatus.NORMALIZED,
        DocumentStatus.READY,
    ]

    TERMINAL_STATES = [
        DocumentStatus.READY,
        DocumentStatus.FAILED,
        DocumentStatus.QUARANTINED,
        DocumentStatus.QUARANTINED_ENCRYPTED,
        DocumentStatus.QUARANTINED_MALWARE,
        DocumentStatus.QUARANTINED_SECURITY,
    ]

    def test_valid_forward_transitions(self):
        for i in range(len(self.INGESTION_STATES) - 1):
            current = self.INGESTION_STATES[i]
            next_state = self.INGESTION_STATES[i + 1]
            assert _can_transition(current, next_state)

    def test_cannot_skip_states(self):
        assert not _can_transition(DocumentStatus.RECEIVED, DocumentStatus.RENDERED)
        assert not _can_transition(DocumentStatus.VALIDATED, DocumentStatus.NORMALIZED)

    def test_cannot_revert_to_earlier_state(self):
        assert not _can_transition(DocumentStatus.READY, DocumentStatus.RECEIVED)
        assert not _can_transition(DocumentStatus.NORMALIZED, DocumentStatus.EXTRACTED)

    def test_generic_quarantine_from_any_non_terminal(self):
        for s in self.INGESTION_STATES[:-1]:
            assert _can_transition(s, DocumentStatus.QUARANTINED)

    def test_malware_quarantine_from_scan_eligible_states(self):
        eligible = [
            DocumentStatus.RECEIVED,
            DocumentStatus.VALIDATED,
            DocumentStatus.SCANNED,
            DocumentStatus.RENDERED,
        ]
        for s in eligible:
            assert _can_transition(s, DocumentStatus.QUARANTINED_MALWARE)

    def test_security_quarantine_from_any_non_terminal(self):
        for s in self.INGESTION_STATES[:-1]:
            assert _can_transition(s, DocumentStatus.QUARANTINED_SECURITY)

    def test_encrypted_quarantine_from_pre_render_states(self):
        pre_render = [
            DocumentStatus.RECEIVED,
            DocumentStatus.VALIDATED,
            DocumentStatus.SCANNED,
        ]
        for s in pre_render:
            assert _can_transition(s, DocumentStatus.QUARANTINED_ENCRYPTED)

    def test_encrypted_quarantine_not_from_render_onward(self):
        post_render = [
            DocumentStatus.RENDERED,
            DocumentStatus.EXTRACTED,
            DocumentStatus.NORMALIZED,
        ]
        for s in post_render:
            assert not _can_transition(s, DocumentStatus.QUARANTINED_ENCRYPTED)

    def test_failed_from_any_non_terminal(self):
        for s in self.INGESTION_STATES[:-1]:
            assert _can_transition(s, DocumentStatus.FAILED)

    def test_terminal_states_allow_no_further_transitions(self):
        for terminal in self.TERMINAL_STATES:
            for target in DocumentStatus:
                if target != terminal:
                    assert not _can_transition(terminal, target), (
                        f"{terminal} -> {target} should be forbidden"
                    )


def _can_transition(current: DocumentStatus, target: DocumentStatus) -> bool:
    VALID_TRANSITIONS: dict[DocumentStatus, set[DocumentStatus]] = {
        DocumentStatus.RECEIVED: {
            DocumentStatus.VALIDATED,
            DocumentStatus.FAILED,
            DocumentStatus.QUARANTINED,
            DocumentStatus.QUARANTINED_ENCRYPTED,
            DocumentStatus.QUARANTINED_MALWARE,
            DocumentStatus.QUARANTINED_SECURITY,
        },
        DocumentStatus.VALIDATED: {
            DocumentStatus.SCANNED,
            DocumentStatus.FAILED,
            DocumentStatus.QUARANTINED,
            DocumentStatus.QUARANTINED_ENCRYPTED,
            DocumentStatus.QUARANTINED_MALWARE,
            DocumentStatus.QUARANTINED_SECURITY,
        },
        DocumentStatus.SCANNED: {
            DocumentStatus.RENDERED,
            DocumentStatus.FAILED,
            DocumentStatus.QUARANTINED,
            DocumentStatus.QUARANTINED_ENCRYPTED,
            DocumentStatus.QUARANTINED_MALWARE,
            DocumentStatus.QUARANTINED_SECURITY,
        },
        DocumentStatus.RENDERED: {
            DocumentStatus.EXTRACTED,
            DocumentStatus.FAILED,
            DocumentStatus.QUARANTINED,
            DocumentStatus.QUARANTINED_MALWARE,
            DocumentStatus.QUARANTINED_SECURITY,
        },
        DocumentStatus.EXTRACTED: {
            DocumentStatus.NORMALIZED,
            DocumentStatus.FAILED,
            DocumentStatus.QUARANTINED,
            DocumentStatus.QUARANTINED_SECURITY,
        },
        DocumentStatus.NORMALIZED: {
            DocumentStatus.READY,
            DocumentStatus.FAILED,
            DocumentStatus.QUARANTINED,
            DocumentStatus.QUARANTINED_SECURITY,
        },
        DocumentStatus.READY: set(),
        DocumentStatus.PENDING: {
            DocumentStatus.READY,
            DocumentStatus.FAILED,
        },
        DocumentStatus.FAILED: set(),
        DocumentStatus.QUARANTINED: set(),
        DocumentStatus.QUARANTINED_ENCRYPTED: set(),
        DocumentStatus.QUARANTINED_MALWARE: set(),
        DocumentStatus.QUARANTINED_SECURITY: set(),
        DocumentStatus.INCOMPLETE: {
            DocumentStatus.READY,
            DocumentStatus.PENDING,
            DocumentStatus.FAILED,
        },
    }
    return target in VALID_TRANSITIONS.get(current, set())


# ─── Content-hash dedup tests ──────────────────────────────────────────────


class TestContentHashDedup:
    def test_same_hash_same_tenant_links(self):
        store = FakeDocumentStore()
        hash_1 = "sha256:" + hashlib.sha256(b"same content").hexdigest()
        hash_2 = "sha256:" + hashlib.sha256(b"same content").hexdigest()

        doc_1 = store.create(hash_1, "tenant-a", "invoice")
        doc_2 = store.create(hash_2, "tenant-a", "invoice")

        assert doc_2["duplicate_of"] == doc_1["document_id"]

    def test_same_hash_different_tenant_does_not_link(self):
        store = FakeDocumentStore()
        hash_1 = "sha256:" + hashlib.sha256(b"same content").hexdigest()
        hash_2 = "sha256:" + hashlib.sha256(b"same content").hexdigest()

        store.create(hash_1, "tenant-a", "invoice")
        doc_2 = store.create(hash_2, "tenant-b", "invoice")

        assert "duplicate_of" not in doc_2

    def test_different_hashes_do_not_dedup(self):
        store = FakeDocumentStore()
        hash_a = "sha256:" + hashlib.sha256(b"content A").hexdigest()
        hash_b = "sha256:" + hashlib.sha256(b"content B").hexdigest()

        store.create(hash_a, "tenant-a", "invoice")
        doc_2 = store.create(hash_b, "tenant-a", "invoice")

        assert "duplicate_of" not in doc_2


class FakeDocumentStore:
    def __init__(self):
        self._docs: dict[str, dict] = {}
        self._counter = 0

    def create(self, content_hash: str, tenant_id: str, doc_type: str) -> dict:
        for existing in self._docs.values():
            if existing["content_hash"] == content_hash and existing["tenant_id"] == tenant_id:
                return {
                    "document_id": f"doc_{self._counter:04d}",
                    "duplicate_of": existing["document_id"],
                    "status": existing["status"],
                }
        self._counter += 1
        doc_id = f"doc_{self._counter:04d}"
        entry = {
            "document_id": doc_id,
            "content_hash": content_hash,
            "tenant_id": tenant_id,
            "doc_type": doc_type,
            "status": "RECEIVED",
        }
        self._docs[doc_id] = entry
        return entry


# ─── Document validation tests ─────────────────────────────────────────────


class TestDocumentValidation:
    def test_rejects_beyond_max_pages(self):
        assert not _is_valid_page_count(501)
        assert not _is_valid_page_count(999)

    def test_accepts_up_to_max_pages(self):
        assert _is_valid_page_count(1)
        assert _is_valid_page_count(500)
        assert _is_valid_page_count(100)

    def test_rejects_beyond_max_size_bytes(self):
        max_bytes = 100 * 1024 * 1024
        assert not _is_valid_file_size(max_bytes + 1)

    def test_accepts_within_size_limit(self):
        max_bytes = 100 * 1024 * 1024
        assert _is_valid_file_size(max_bytes)
        assert _is_valid_file_size(0)
        assert _is_valid_file_size(1024)

    def test_rejects_zero_byte_file(self):
        assert _is_zero_byte(0)

    def test_accepts_non_empty_file(self):
        assert not _is_zero_byte(1)

    def test_detects_encrypted_pdf_header(self):
        assert _is_encrypted_pdf(b"%PDF-1.4\n%some content\n/Encrypt 123 0 R")
        assert not _is_encrypted_pdf(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>")

    def test_supported_mime_types(self):
        assert _is_supported_mime("application/pdf")
        assert _is_supported_mime("image/jpeg")
        assert _is_supported_mime("image/png")
        assert not _is_supported_mime("application/zip")
        assert not _is_supported_mime("text/plain")


def _is_valid_page_count(pages: int) -> bool:
    return 1 <= pages <= 500


def _is_valid_file_size(size_bytes: int) -> bool:
    return size_bytes <= 100 * 1024 * 1024


def _is_zero_byte(size_bytes: int) -> bool:
    return size_bytes == 0


def _is_encrypted_pdf(data: bytes) -> bool:
    return b"/Encrypt" in data


def _is_supported_mime(mime: str) -> bool:
    return mime in {"application/pdf", "image/jpeg", "image/png"}


# ─── Reconciliation tests ──────────────────────────────────────────────────


class TestReconciliation:
    def test_zero_discrepancy_when_balanced(self):
        counts = {
            "accepted": 100,
            "completed": 85,
            "quarantined": 5,
            "failed": 3,
            "in_flight": 7,
        }
        assert _reconcile(counts)["discrepancy"] == 0

    def test_discrepancy_when_unbalanced(self):
        counts = {
            "accepted": 100,
            "completed": 80,
            "quarantined": 5,
            "failed": 3,
            "in_flight": 7,
        }
        assert _reconcile(counts)["discrepancy"] == 5

    def test_negative_discrepancy(self):
        counts = {
            "accepted": 100,
            "completed": 90,
            "quarantined": 10,
            "failed": 5,
            "in_flight": 5,
        }
        assert _reconcile(counts)["discrepancy"] == -10


def _reconcile(counts: dict[str, int]) -> dict:
    total = counts["completed"] + counts["quarantined"] + counts["failed"] + counts["in_flight"]
    return {"discrepancy": counts["accepted"] - total}
