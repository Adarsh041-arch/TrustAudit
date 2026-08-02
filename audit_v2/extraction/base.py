from __future__ import annotations

from abc import ABC, abstractmethod

from audit_v2.domain.models import Coverage, DocumentHeader, ExtractedDocument, LineItem, TaxLine


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, data: bytes, mime_type: str) -> ExtractedDocument:
        ...

    def extract_header(self) -> DocumentHeader:
        raise NotImplementedError

    def extract_line_items(self) -> list[LineItem]:
        raise NotImplementedError

    def extract_tax_lines(self) -> list[TaxLine]:
        raise NotImplementedError

    def get_coverage(self) -> Coverage:
        raise NotImplementedError
