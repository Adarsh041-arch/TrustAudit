"""Evidence & Provenance Graph — Phase 9 (PHASES_V2 §4 Phase 9).

Stores immutable decision provenance chains linking:
finding -> check_id -> ruleset_version -> document_id -> page -> bbox -> extracted_field.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from audit_v2.domain.models import Finding

logger = logging.getLogger(__name__)


@dataclass
class ProvenanceNode:
    node_id: str
    node_type: str  # finding | check | rule_version | field | page | document
    label: str
    metadata: dict[str, Any]


@dataclass
class ProvenanceEdge:
    source_id: str
    target_id: str
    relationship: str  # derived_from | evaluated_by | cites_field | located_on


class ProvenanceGraph:
    """In-memory DAG tracking decision provenance chains (backed by Postgres in prod)."""

    def __init__(self) -> None:
        self._nodes: dict[str, ProvenanceNode] = {}
        self._edges: list[ProvenanceEdge] = []

    def record_finding_provenance(
        self,
        finding: Finding,
        document_id: str,
        ruleset_version: str,
        prompt_version: str,
        model_version: str,
    ) -> None:
        """Record the complete, immutable evidence graph for a finding."""
        f_node_id = f"finding:{finding.finding_id}"
        self._nodes[f_node_id] = ProvenanceNode(
            node_id=f_node_id,
            node_type="finding",
            label=f"Finding {finding.finding_id} ({finding.status})",
            metadata={
                "check_id": finding.check_id,
                "status": finding.status,
                "fingerprint": finding.decision_fingerprint,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

        doc_node_id = f"doc:{document_id}"
        if doc_node_id not in self._nodes:
            self._nodes[doc_node_id] = ProvenanceNode(
                node_id=doc_node_id,
                node_type="document",
                label=f"Document {document_id}",
                metadata={"document_id": document_id},
            )

        self._edges.append(ProvenanceEdge(
            source_id=f_node_id,
            target_id=doc_node_id,
            relationship="evaluates_document",
        ))

        rule_node_id = f"rule:{ruleset_version}"
        if rule_node_id not in self._nodes:
            self._nodes[rule_node_id] = ProvenanceNode(
                node_id=rule_node_id,
                node_type="rule_version",
                label=f"Ruleset {ruleset_version}",
                metadata={"prompt_version": prompt_version, "model_version": model_version},
            )

        self._edges.append(ProvenanceEdge(
            source_id=f_node_id,
            target_id=rule_node_id,
            relationship="governed_by",
        ))

        for idx, item in enumerate(finding.evidence):
            ev_node_id = f"evidence:{finding.finding_id}:{idx}"
            self._nodes[ev_node_id] = ProvenanceNode(
                node_id=ev_node_id,
                node_type="field",
                label=f"Field {item.field} (page {item.page})",
                metadata={
                    "field": item.field,
                    "page": item.page,
                    "bbox": item.bbox,
                    "raw": item.raw,
                },
            )

            self._edges.append(ProvenanceEdge(
                source_id=f_node_id,
                target_id=ev_node_id,
                relationship="cites_field",
            ))

    def get_evidence_chain(self, finding_id: str) -> list[ProvenanceNode]:
        """Retrieve all nodes connected to a finding."""
        f_node_id = f"finding:{finding_id}"
        if f_node_id not in self._nodes:
            return []

        target_ids = {
            e.target_id for e in self._edges if e.source_id == f_node_id
        }
        target_ids.add(f_node_id)
        return [self._nodes[nid] for nid in target_ids if nid in self._nodes]
