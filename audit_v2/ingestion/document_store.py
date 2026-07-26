from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime


class DocumentRecord:
    def __init__(
        self,
        document_id: str,
        tenant_id: str,
        content_hash: str,
        status: str = "RECEIVED",
        doc_type: str | None = None,
        batch_id: str | None = None,
        page_count: int | None = None,
        source_uri: str | None = None,
        duplicate_of: str | None = None,
    ):
        self.document_id = document_id
        self.tenant_id = tenant_id
        self.content_hash = content_hash
        self.status = status
        self.doc_type = doc_type
        self.batch_id = batch_id
        self.page_count = page_count
        self.source_uri = source_uri
        self.duplicate_of = duplicate_of


class DocumentStore(ABC):
    @abstractmethod
    def create(
        self,
        tenant_id: str,
        content_hash: str,
        doc_type: str | None = None,
        batch_id: str | None = None,
        source_uri: str | None = None,
    ) -> DocumentRecord:
        ...

    @abstractmethod
    def get(self, document_id: str) -> DocumentRecord | None:
        ...

    @abstractmethod
    def update_status(self, document_id: str, status: str) -> None:
        ...

    @abstractmethod
    def get_by_hash(self, tenant_id: str, content_hash: str) -> DocumentRecord | None:
        ...

    @abstractmethod
    def count_by_status(self, tenant_id: str) -> dict[str, int]:
        ...


class MemoryDocumentStore(DocumentStore):
    def __init__(self):
        self._records: dict[str, DocumentRecord] = {}
        self._counter = 0

    def create(
        self,
        tenant_id: str,
        content_hash: str,
        doc_type: str | None = None,
        batch_id: str | None = None,
        source_uri: str | None = None,
    ) -> DocumentRecord:
        existing = self.get_by_hash(tenant_id, content_hash)
        if existing is not None:
            return DocumentRecord(
                document_id=self._next_id(),
                tenant_id=tenant_id,
                content_hash=content_hash,
                status=existing.status,
                doc_type=doc_type,
                batch_id=batch_id,
                source_uri=source_uri,
                duplicate_of=existing.document_id,
            )
        self._counter += 1
        doc_id = self._next_id()
        record = DocumentRecord(
            document_id=doc_id,
            tenant_id=tenant_id,
            content_hash=content_hash,
            status="RECEIVED",
            doc_type=doc_type,
            batch_id=batch_id,
            source_uri=source_uri,
        )
        self._records[doc_id] = record
        return record

    def get(self, document_id: str) -> DocumentRecord | None:
        return self._records.get(document_id)

    def update_status(self, document_id: str, status: str) -> None:
        rec = self._records.get(document_id)
        if rec is not None:
            rec.status = status

    def get_by_hash(self, tenant_id: str, content_hash: str) -> DocumentRecord | None:
        for rec in self._records.values():
            if rec.tenant_id == tenant_id and rec.content_hash == content_hash:
                return rec
        return None

    def count_by_status(self, tenant_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for rec in self._records.values():
            if rec.tenant_id == tenant_id:
                counts[rec.status] = counts.get(rec.status, 0) + 1
        return counts

    def _next_id(self) -> str:
        ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        return f"doc_{ts}_{self._counter:04d}"
