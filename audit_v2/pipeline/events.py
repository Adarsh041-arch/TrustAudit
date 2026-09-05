"""Pipeline progress events + the ``ProgressSink`` seam (new_requirements.md §6).

The pipeline announces each step through a :class:`ProgressSink`. In Phase 1 the
sink is a no-op (:class:`NullProgressSink`) or a logger; in Phase 2 an SSE sink
will push :class:`StepEvent`\\s onto a per-job ``asyncio.Queue`` so the frontend
can show, in real time, which step is running for which document. Keeping the
pipeline talking only to this protocol means Phase 2 changes nothing here.
"""
from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PipelineStep(StrEnum):
    """The ordered steps of the evidence pipeline (spec §3–§7).

    ``RECEIVED``/``SCORE``/``DONE`` bracket the pipeline: they are emitted by the
    server batch (``server._process_documents``), not by ``run_document_pipeline``
    itself, so a streaming client can label a per-document progress row on
    ``RECEIVED`` and close it out on ``DONE``.
    """

    RECEIVED = "received"
    CLASSIFY = "classify"
    EXTRACT_REGEX = "extract_regex"
    EXTRACT_OCR = "extract_ocr"
    EXTRACT_VLM = "extract_vlm"
    VLM_SELFCHECK = "vlm_selfcheck"
    ARITHMETIC = "arithmetic"
    CROSS_CHECK = "cross_check"
    SCORE = "score"
    DONE = "done"


class StepStatus(StrEnum):
    START = "start"
    OK = "ok"
    SKIP = "skip"
    ERROR = "error"


class StepEvent(BaseModel):
    """One progress event: a step for a document changing status."""

    document_id: str
    step: PipelineStep
    status: StepStatus
    detail: str = ""
    #: optional structured extras (e.g. evidence_id, counts) for the UI
    data: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ProgressSink(Protocol):
    """Anything that can receive pipeline progress events."""

    def emit(self, event: StepEvent) -> None: ...


class NullProgressSink:
    """Default sink: log at debug and drop. Used on the synchronous path."""

    def emit(self, event: StepEvent) -> None:
        logger.debug(
            "[pipeline] %s %s %s %s",
            event.document_id, event.step, event.status, event.detail,
        )


def emit(
    sink: ProgressSink,
    document_id: str,
    step: PipelineStep,
    status: StepStatus,
    detail: str = "",
    **data: Any,
) -> None:
    """Convenience helper to build and emit a :class:`StepEvent`."""
    sink.emit(
        StepEvent(
            document_id=document_id,
            step=step,
            status=status,
            detail=detail,
            data=data,
        )
    )
