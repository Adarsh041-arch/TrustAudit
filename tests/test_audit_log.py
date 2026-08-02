"""Unit tests for AuditLog (PHASES_V2 §4 Phase 2 Governance)."""

from audit_v2.persistence.audit_log import AuditLog


class TestAuditLog:
    def test_log_creation_and_hash_chain(self):
        log = AuditLog()
        e1 = log.log(
            entry_id="e1",
            tenant_id="t1",
            action="document_ingested",
            resource_type="document",
            resource_id="doc_1",
            actor_id="user_a",
            payload={"page_count": 5},
        )
        assert e1.prev_hash == "0" * 64
        assert len(e1.hash_chain) == 64

        e2 = log.log(
            entry_id="e2",
            tenant_id="t1",
            action="finding_emitted",
            resource_type="finding",
            resource_id="fnd_1",
            actor_id="user_a",
            payload={"check_id": "CHK-ARITH-LINE-001"},
        )
        assert e2.prev_hash == e1.hash_chain

        valid, err = log.verify_chain()
        assert valid is True
        assert err is None

    def test_verify_chain_detects_payload_tampering(self):
        log = AuditLog()
        log.log(
            entry_id="e1", tenant_id="t1", action="create",
            resource_type="doc", resource_id="d1", actor_id="a1",
        )
        e2 = log.log(
            entry_id="e2", tenant_id="t1", action="create",
            resource_type="doc", resource_id="d2", actor_id="a1",
        )

        valid, _ = log.verify_chain()
        assert valid is True

        # Mutate historical entry payload
        e2.payload["tampered"] = True

        valid, err = log.verify_chain()
        assert valid is False
        assert "payload tampered" in err

    def test_verify_chain_detects_prev_hash_tampering(self):
        log = AuditLog()
        log.log("e1", "t1", "create", "doc", "d1", "a1")
        e2 = log.log("e2", "t1", "create", "doc", "d2", "a1")

        # Corrupt prev_hash
        e2.prev_hash = "corrupted_hash"

        valid, err = log.verify_chain()
        assert valid is False
        assert "prev_hash mismatch" in err
