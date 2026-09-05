"""Pipeline package — the evidence-based audit pipeline (new_requirements.md).

Phase 1 exposes the synchronous pipeline (:func:`run_document_pipeline`) and its
progress seam (:mod:`events`); Phase 2 will attach an SSE ``ProgressSink`` to
stream steps to the browser.
"""
from audit_v2.pipeline.events import (
    NullProgressSink,
    PipelineStep,
    ProgressSink,
    StepEvent,
    StepStatus,
)
from audit_v2.pipeline.evidence_pipeline import (
    DocumentPipelineResult,
    run_document_pipeline,
)

__all__ = [
    "DocumentPipelineResult",
    "run_document_pipeline",
    "NullProgressSink",
    "PipelineStep",
    "ProgressSink",
    "StepEvent",
    "StepStatus",
]
