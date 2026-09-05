"""Pytest configuration for audit_v2 tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from audit_v2.domain.models import (
    CheckCatalog,
    CheckCatalogEntry,
    Coverage,
    DocumentHeader,
    DocumentType,
    EvidenceItem,
    ExtractedDocument,
    LineItem,
    ProvenancedValue,
    ToleranceSpec,
)
from audit_v2.gateway.vlm_gateway import ModelResponse

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _hermetic_no_live_vlm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite offline by default — no live NVIDIA VLM calls.

    The real ``NVIDIA_API_KEY`` loads from ``.env`` on import, so any test that
    uploads through the server would otherwise exercise the live VLM. On the
    saturated shared endpoint that means a 5x120s retry loop (~12 min/doc, see
    ``nvidia_gateway.NvidiaGateway``) — the suite appears to hang. Removing the
    key makes ``activities.extract_with_vlm`` skip the network and fall back to
    regex extraction, which is what the unit suite asserts against anyway.

    Unaffected: gateway unit tests inject their own ``api_key=`` and mock
    ``requests.post``; the recon ask-AI test sets its own key and stubs the
    gateway. Set ``TRUSTAUDIT_LIVE_VLM=1`` to opt back into live calls for a
    deliberate end-to-end VLM check.
    """
    if not os.getenv("TRUSTAUDIT_LIVE_VLM"):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)


@pytest.fixture(scope="session")
def check_catalog() -> CheckCatalog:
    path = REPO_ROOT / "contracts" / "check_catalog.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return CheckCatalog(**data)


@pytest.fixture
def sample_line_item() -> LineItem:
    return LineItem(
        line_number=1,
        description=ProvenancedValue(value="Widget A", raw="Widget A", page=1, confidence=0.98),
        quantity=ProvenancedValue(value="5", raw="5", page=1, confidence=0.99),
        unit_price=ProvenancedValue(value="30.00", raw="$30.00", currency="USD", page=1, confidence=0.97),
        line_total=ProvenancedValue(value="150.00", raw="$150.00", currency="USD", page=1, confidence=0.97),
        hsn_sac=ProvenancedValue(value="8471", raw="8471", page=1, confidence=0.81),
    )


@pytest.fixture
def sample_coverage_full() -> Coverage:
    return Coverage(pages_total=5, pages_examined=5, pages_unreadable=[], coverage_complete=True)


@pytest.fixture
def sample_coverage_partial() -> Coverage:
    return Coverage(pages_total=18, pages_examined=10, pages_unreadable=[11], coverage_complete=False)


@pytest.fixture
def empty_tolerance() -> ToleranceSpec:
    return ToleranceSpec(type="absolute", value="0.00", currency_scaled=True)


@pytest.fixture
def sample_evidence() -> list[EvidenceItem]:
    return [
        EvidenceItem(document_id="doc_001", page=1, bbox=[100, 200, 150, 220], field="quantity", raw="5"),
        EvidenceItem(document_id="doc_001", page=1, bbox=[160, 200, 220, 220], field="unit_price", raw="$30.00"),
    ]


@pytest.fixture
def catalog_entry_arithmetic() -> CheckCatalogEntry:
    return CheckCatalogEntry(
        check_id="CHK-ARITH-LINE-001",
        title="Line-item total equals quantity times unit price",
        category="arithmetic",
        applies_to=["invoice", "purchase_order"],
        severity="critical",
        determinism="deterministic",
        inputs=["line_items"],
        tolerance=ToleranceSpec(type="absolute", value="0.00", currency_scaled=True),
        failure_message="Line {n}: {qty} x {unit_price} = {expected}, stated {actual}",
    )


@pytest.fixture
def deterministic_checks(check_catalog: CheckCatalog) -> list[CheckCatalogEntry]:
    return [c for c in check_catalog.checks if c.determinism.value == "deterministic"]


@pytest.fixture
def all_check_ids(check_catalog: CheckCatalog) -> set[str]:
    return {c.check_id for c in check_catalog.checks}


# ─── Evidence-pipeline test doubles (new_requirements.md Phase 1, plan §8) ────
#
# The pipeline touches the network only through an injected NvidiaGateway and
# OCR only through RapidOcrExtractor. These doubles let the pipeline/server/
# cross-check tests run fully offline and deterministically.


class FakeGateway:
    """In-memory stand-in for :class:`NvidiaGateway`.

    Returns queued replies in order and records every ``extract`` call. A queued
    item that is an ``Exception`` is *raised* (used to simulate a guided_json
    400 → schema-in-prompt fallback, or a hard failure); anything else is
    returned as the ``content`` of a :class:`ModelResponse`. Never touches the
    network. The signature mirrors ``NvidiaGateway.extract`` exactly so it drops
    in wherever a real gateway would.
    """

    def __init__(self, replies: list[Any] | None = None) -> None:
        self._replies: list[Any] = list(replies or [])
        self.calls: list[dict[str, Any]] = []
        self.model = "fake-model"

    def queue(self, *replies: Any) -> "FakeGateway":
        self._replies.extend(replies)
        return self

    def extract(
        self,
        images: list[bytes],
        prompt: str,
        tenant_id: str,
        pii_classes: Any = None,
        response_schema: dict | None = None,
    ) -> ModelResponse:
        self.calls.append(
            {
                "prompt": prompt,
                "images": list(images),
                "response_schema": response_schema,
                "tenant_id": tenant_id,
            }
        )
        if not self._replies:
            raise AssertionError("FakeGateway exhausted its queued replies")
        item = self._replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return ModelResponse(content=item, model_version="fake-model")


@pytest.fixture
def make_gateway():
    """Factory: ``make_gateway('json', RuntimeError('400'), 'json2')`` -> FakeGateway."""

    def _make(*replies: Any) -> FakeGateway:
        return FakeGateway(list(replies))

    return _make


class _UnavailableOcr:
    """OCR double that always reports unavailable — fast and deterministic."""

    def extract_text(self, images: list[bytes]):
        from audit_v2.extraction.ocr_extractor import OcrResult

        return OcrResult(available=False, note="ocr stubbed off in tests")

    def extract_fields(self, images: list[bytes], doc_type: DocumentType) -> dict:
        return {"available": False, "note": "ocr stubbed off in tests"}


@pytest.fixture(autouse=True)
def _stub_pipeline_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default the pipeline's OCR to 'unavailable'.

    Keeps server/pipeline tests fast and hermetic whether or not
    ``rapidocr-onnxruntime`` is installed. Only patches the name the pipeline
    resolves (``evidence_pipeline.RapidOcrExtractor``); the OCR unit tests in
    ``test_ocr_extractor.py`` import the real class directly and are unaffected,
    and tests that need specific OCR behaviour inject their own extractor via
    ``run_document_pipeline(ocr=...)``, which takes precedence.
    """
    monkeypatch.setattr(
        "audit_v2.pipeline.evidence_pipeline.RapidOcrExtractor", _UnavailableOcr
    )
    # Unit/integration tests are hermetic even when a developer happens to have
    # llama-server running. Tests that exercise GLM inject their own gateway.
    monkeypatch.setenv("V2_VISION_BACKEND", "none")
