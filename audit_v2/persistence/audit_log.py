"""Immutable Hash-Chained Audit Log — Phase 2 Governance (PHASES_V2 §4 Phase 2).

Provides an append-only audit trail where each entry includes sha256(prev_hash || payload).
Any historical mutation or tampering breaks the hash chain and is detected by verify_chain().
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64


@dataclass
class AuditLogEntry:
    entry_id: str
    tenant_id: str
    action: str
    resource_type: str
    resource_id: str
    actor_id: str
    payload: dict[str, Any]
    timestamp: str
    prev_hash: str
    hash_chain: str

    def compute_hash(self) -> str:
        content = json.dumps(
            {
                "entry_id": self.entry_id,
                "tenant_id": self.tenant_id,
                "action": self.action,
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
                "actor_id": self.actor_id,
                "payload": self.payload,
                "timestamp": self.timestamp,
                "prev_hash": self.prev_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class AuditLog:
    """In-memory append-only hash-chained audit log (backed by database when active)."""

    def __init__(self) -> None:
        self._entries: list[AuditLogEntry] = []
        self._last_hash: str = GENESIS_HASH

    @property
    def entries(self) -> list[AuditLogEntry]:
        return list(self._entries)

    def log(
        self,
        entry_id: str,
        tenant_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        actor_id: str,
        payload: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> AuditLogEntry:
        payload = payload or {}
        ts = timestamp or datetime.now(UTC).isoformat()
        prev = self._last_hash

        entry_dummy = AuditLogEntry(
            entry_id=entry_id,
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            payload=payload,
            timestamp=ts,
            prev_hash=prev,
            hash_chain="",
        )
        entry_hash = entry_dummy.compute_hash()
        entry = AuditLogEntry(
            entry_id=entry_id,
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            payload=payload,
            timestamp=ts,
            prev_hash=prev,
            hash_chain=entry_hash,
        )

        self._entries.append(entry)
        self._last_hash = entry_hash
        logger.info(
            "AuditLog entry %s recorded for tenant %s (action=%s, hash=%s)",
            entry_id, tenant_id, action, entry_hash[:8],
        )
        return entry

    def verify_chain(self) -> tuple[bool, str | None]:
        """Verify the cryptographic integrity of the audit log chain.

        Returns (True, None) if valid, or (False, failure_reason) if tampered.
        """
        expected_prev = GENESIS_HASH
        for idx, entry in enumerate(self._entries):
            if entry.prev_hash != expected_prev:
                return False, f"Entry {entry.entry_id} at index {idx}: prev_hash mismatch"

            recomputed = entry.compute_hash()
            if entry.hash_chain != recomputed:
                return False, f"Entry {entry.entry_id} at index {idx}: hash_chain payload tampered"

            expected_prev = entry.hash_chain

        return True, None
