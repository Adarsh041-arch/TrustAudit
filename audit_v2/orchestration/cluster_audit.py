"""Cluster-level audit with deferred re-evaluation — Phase 7 (PHASES_V2 §4).

Documents arrive out of order and clusters are incomplete for days. The
ClusterAuditor accumulates extracted documents per tenant; every new arrival
re-evaluates the cross-document checks for its cluster. A re-evaluated
(document_id, check_id) pair supersedes the earlier finding rather than
duplicating it — findings have a lifecycle, not just a creation.
"""
from __future__ import annotations

import hashlib
import logging

from audit_v2.domain.catalog_loader import entries_by_id, load_catalog
from audit_v2.domain.correlation import build_clusters, build_corpus_index
from audit_v2.domain.finding_generator import make_finding_from_result
from audit_v2.domain.models import (
    CheckDeterminism,
    ExtractedDocument,
    Finding,
    TransactionCluster,
)
from audit_v2.domain.validation import CheckRunner

logger = logging.getLogger(__name__)

# The cross-document check set. Single-document checks are the plain
# workflow's job; re-running them here would double-emit findings.
CLUSTER_CHECK_IDS = (
    "CHK-DUP-DOC-001",
    "CHK-REF-QTY-001",
    "CHK-REF-QTY-002",
    "CHK-XDOC-QTY-001",
    "CHK-XDOC-PRICE-001",
    "CHK-XDOC-RECEIPT-001",
    "CHK-XDOC-CUMUL-001",
)


class ClusterAuditor:
    """Accumulates documents and re-evaluates cluster checks on each arrival.

    ponytail: in-memory, single tenant per instance; back with Postgres when
    clusters must survive process restarts.
    """

    def __init__(
        self,
        ruleset_version: str,
        prompt_version: str = "prompt_v3",
        model_version: str = "deterministic",
    ) -> None:
        self._documents: list[ExtractedDocument] = []
        self._ruleset_version = ruleset_version
        self._prompt_version = prompt_version
        self._model_version = model_version
        # (document_id, check_id) -> active finding; superseded ones move to history
        self._active: dict[tuple[str, str], Finding] = {}
        self._history: list[Finding] = []
        catalog = load_catalog()
        self._by_id = entries_by_id(catalog)
        self._runner = CheckRunner(catalog_checks=catalog.checks)
        self._check_ids = [
            c for c in CLUSTER_CHECK_IDS
            if self._by_id.get(c) is not None
            and self._by_id[c].determinism == CheckDeterminism.DETERMINISTIC
        ]

    @property
    def active_findings(self) -> list[Finding]:
        return list(self._active.values())

    @property
    def superseded_findings(self) -> list[Finding]:
        return list(self._history)

    def clusters(self) -> list[TransactionCluster]:
        return build_clusters(self._documents)

    def add_document(self, document: ExtractedDocument) -> list[Finding]:
        """Ingest a document and re-evaluate its cluster.

        Returns the findings emitted by this re-evaluation (new and
        superseding). Earlier findings for the same (document, check) are
        moved to history with the new finding's `supersedes` pointing at them.
        """
        self._documents.append(document)
        clusters = build_clusters(self._documents)
        corpus_index = build_corpus_index(self._documents)

        cluster = next(
            (c for c in clusters
             if any(d.document_id == document.document_id for d in c.documents)),
            None,
        )
        if cluster is None:  # cannot happen — every doc lands in some cluster
            logger.error("Document %s missing from all clusters", document.document_id)
            return []

        emitted: list[Finding] = []
        # The cluster context determines cross-document verdicts: hash the
        # member set so the fingerprint changes when the cluster grows.
        cluster_hash = hashlib.sha256(
            "|".join(sorted(d.document_id for d in cluster.documents)).encode()
        ).hexdigest()[:16]
        for member in cluster.documents:
            applicable = [
                c for c in self._check_ids
                if member.doc_type in self._by_id[c].applies_to
            ]
            if not applicable:
                continue
            results = self._runner.run_all(
                document=member,
                included_check_ids=applicable,
                skipped_check_ids={},
                cluster=cluster,
                corpus_index=corpus_index,
            )
            for cr in results:
                entry = self._by_id[cr.check_id]
                finding = make_finding_from_result(
                    result=cr,
                    check_entry=entry,
                    document=member,
                    ruleset_version=self._ruleset_version,
                    prompt_version=self._prompt_version,
                    model_version=self._model_version,
                    context_hash=cluster_hash,
                )
                key = (member.document_id, cr.check_id)
                prior = self._active.get(key)
                if prior is not None:
                    verdict_unchanged = (
                        prior.status == finding.status
                        and prior.expected == finding.expected
                        and prior.actual == finding.actual
                        and prior.message == finding.message
                    )
                    if verdict_unchanged:
                        continue  # same verdict — keep the original, no duplicate
                    finding.supersedes = prior.finding_id
                    self._history.append(prior)
                self._active[key] = finding
                emitted.append(finding)

        return emitted
