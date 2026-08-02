"""VLM-based extraction for free-text documents (contract, letter).

Text-only documents have no tabular line items, so the regex extractors do
not apply. The VLM produces structured key fields (mapped into the standard
DocumentHeader shape so existing validators still run) plus a free-text
narrative report.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from audit_v2.domain.models import (
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
)
from audit_v2.extraction.base import BaseExtractor
from audit_v2.extraction.vlm_extractor import _pv, render_pages_to_jpeg
from audit_v2.gateway.nvidia_gateway import NvidiaGateway

logger = logging.getLogger(__name__)

TEXT_EXTRACTION_PROMPT = """You are a high-precision document analysis engine.
Analyze the provided document page image(s) — a contract or letter — and
extract its key data fields.

Return ONLY a single valid JSON object with the following exact structure:
{
  "header": {
    "doc_type": "contract|letter",
    "party_a": "sender/party-1 name or null",
    "party_b": "recipient/party-2 name or null",
    "date": "YYYY-MM-DD or null (effective date for contracts, letter date for letters)",
    "expiry_date": "YYYY-MM-DD or null (contracts only)",
    "reference": "document/agreement reference number or null",
    "value_amount": "number as string or null (contract value / amount mentioned)",
    "subject": "short subject line or null"
  },
  "narrative_report": "A concise report (2-5 sentences) summarising the document: "
                      "what it is, the parties, key dates, amounts, and unusual clauses."
}

Important:
1. Do not enclose the JSON in markdown code blocks, or return strictly valid JSON.
2. Monetary amounts must be formatted as strings (e.g. "1250.00").
3. If a field is not present in the document, return null — never guess.
"""


class VlmTextExtractor(BaseExtractor):
    """Extracts key fields + narrative report from contracts and letters."""

    def __init__(self, gateway: NvidiaGateway | None = None) -> None:
        self.gateway = gateway or NvidiaGateway()

    def extract(self, data: bytes, mime_type: str) -> ExtractedDocument:
        images = render_pages_to_jpeg(data, mime_type)
        if not images:
            raise ValueError("No renderable pages found in document")

        response = self.gateway.extract(
            images=images,
            prompt=TEXT_EXTRACTION_PROMPT,
            tenant_id="vlm_text_extractor",
        )
        parsed = self._clean_and_parse_json(response.content)
        return self._build_document(parsed, page_count=len(images))

    def _clean_and_parse_json(self, raw_content: str) -> dict[str, Any]:
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as err:
            logger.error(
                "Failed to parse VLM text response as JSON: %s\nContent: %s",
                err, raw_content,
            )
            raise ValueError(f"Unparseable VLM text response: {err}") from err

    def _build_document(
        self, data: dict[str, Any], page_count: int,
    ) -> ExtractedDocument:
        header_data = data.get("header", {}) or {}
        raw_doc_type = header_data.get("doc_type", "contract")
        try:
            doc_type = DocumentType(raw_doc_type)
        except ValueError:
            doc_type = DocumentType.CONTRACT

        header = DocumentHeader(
            document_id="vlm_text_doc",
            doc_type=doc_type,
            vendor_name=_pv(header_data.get("party_a")),
            buyer_name=_pv(header_data.get("party_b")),
            invoice_date=_pv(header_data.get("date")),
            expiry_date=_pv(header_data.get("expiry_date")),
            po_reference=_pv(header_data.get("reference")),
            grand_total=_pv(header_data.get("value_amount")),
        )
        if header.po_reference is not None and not header.document_id.endswith(
            header.po_reference.value
        ):
            header.document_id = f"vlm_text_{header.po_reference.value}"

        coverage = Coverage(
            pages_total=page_count,
            pages_examined=page_count,
            coverage_complete=True,
        )
        return ExtractedDocument(
            document_id=header.document_id,
            tenant_id="t",
            doc_type=doc_type,
            header=header,
            line_items=[],
            tax_lines=[],
            coverage=coverage,
            page_count=page_count,
            extractor_version="vlm_text_1.0.0",
            narrative_report=data.get("narrative_report"),
        )
