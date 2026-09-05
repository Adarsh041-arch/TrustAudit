"""Evidence-based pipeline domain types (new_requirements.md §2–§5).

These are additive to the existing `EvidenceItem`/`Finding` model in
``audit_v2.domain.models`` — deterministic validators keep emitting the flat
``EvidenceItem`` they always have. This module adds the *richer* provenance
types the evidence pipeline needs:

- ``PipelineEvidence`` — one observation from one extraction method, tagged with
  its ``nature`` (the spec's discriminator) and ``source``.
- ``Contradiction`` — a single conflict the LLM cross-check found between
  evidences, in exactly the structured shape the spec's §5 dictates.
- ``CrossCheckResult`` — the LLM's whole structured verdict for one document.

The LLM never overturns a deterministic verdict: contradictions are advisory
signals that the server reconciles against authoritative findings in code.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from audit_v2.domain.models import Severity


class EvidenceNature(StrEnum):
    """The nature of an evidence item — values verbatim from new_requirements.md §5."""

    METADATA = "metadata"
    EXTRACTED_FIELDS = "extracted_fields"
    ARITHMETIC_COMPUTATION = "arithmetic_computation"
    VLM_OBSERVATIONS = "vlm_observations"
    OCR_REGEX_OBSERVATIONS = "ocr+regex_observations"


class PipelineEvidence(BaseModel):
    """One observation produced by one step of the evidence pipeline.

    ``payload`` carries the machine-readable observation (extracted fields,
    computed sums, recognized text …); ``summary`` is a short human-readable
    line the frontend and the cross-check LLM can read at a glance.
    """

    evidence_id: str = Field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:12]}")
    document_id: str
    nature: EvidenceNature
    #: regex | rapidocr | vlm | vlm_corrected | arithmetic | metadata | merge
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    page: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Contradiction(BaseModel):
    """A single contradiction the LLM cross-check surfaced (new_requirements.md §5).

    Mirrors the spec's required output exactly: the nature of the evidence, the
    evidence itself, the reason for the contradiction, the degree of confidence,
    and the severity of the violation.
    """

    document_id: str
    nature: EvidenceNature
    #: the evidence text/value the contradiction is about
    evidence: str
    #: why it contradicts the other evidences
    reason: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    severity: Severity = Severity.MEDIUM
    #: which other evidence (nature/source/field) this conflicts with, if known
    conflicting_with: str | None = None


class CrossCheckResult(BaseModel):
    """The LLM's structured verdict over one document's full evidence list (§5)."""

    document_id: str
    supported: bool = True
    contradictions: list[Contradiction] = Field(default_factory=list)
    summary: str = ""
