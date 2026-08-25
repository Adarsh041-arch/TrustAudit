"""Temporal workflow definition for the audit pipeline.

This replaces AuditWorkflow.run() with a proper @workflow.defn that is
durable, replayable, and restart-safe (§2). Each IO step is an
activity with retry policies matching §3.3 failure classes.

Workflow code is deterministic — no IO, no random, no datetime.now().
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy, VersioningBehavior

from audit_v2.domain.models import TEXT_DOC_TYPES, FailureClass
from audit_v2.orchestration.activities_temporal import (
    ClassifyInput,
    ClassifyResult,
    ExtractInput,
    ExtractResult,
    FetchDocumentInput,
    FetchDocumentResult,
    MergeInput,
    MergeResult,
    PersistResultInput,
    ProcessPdfInput,
    ProcessPdfResult,
    SecurityScanInput,
    SecurityScanResult,
    ValidateAndEmitInput,
    ValidateAndEmitResult,
    ValidateInput,
    ValidateResult,
    classify_activity,
    fetch_document,
    merge_extractions_activity,
    persist_results_activity,
    process_pdf_activity,
    regex_extract_activity,
    security_scan_activity,
    validate_and_dedup,
    validate_and_emit_activity,
    vlm_extract_activity,
    vlm_text_extract_activity,
)

with workflow.unsafe.imports_passed_through():
    pass


@dataclass
class AuditWorkflowInput:
    document_id: str
    tenant_id: str
    ruleset_version: str
    data: bytes | None = None
    mime_type: str | None = None
    file_size: int | None = None
    prompt_version: str = "prompt_v3"
    model_version: str = "gemini-2.5-flash"
    tenant_policy: str = "standard"
    current_date: str | None = None


@dataclass
class AuditWorkflowOutput:
    document_id: str
    finding_ids: list[str]
    status: str
    findings: list = field(default_factory=list)
    duplicate_of: str | None = None
    error: str | None = None
    routing_rule_id: str | None = None
    failure_class: FailureClass | None = None
    requires_human_review: bool = False


# §3.3 retry mapping. Temporal applies exponential backoff (server adds
# jitter via the backoff coefficient), which is the §3.3 TRANSIENT policy.
_RETRY_TRANSIENT = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)

# §3.3 POISON: "1 retry then quarantine" = 2 attempts total.
_RETRY_POISON = RetryPolicy(maximum_attempts=2)
# No retry at all. NOTE: maximum_attempts=0 means UNLIMITED in Temporal;
# 1 is the correct value for "run once".
_RETRY_NONE = RetryPolicy(maximum_attempts=1)
_ACTIVITY_TIMEOUT = timedelta(seconds=300)


@workflow.defn(sandboxed=False, versioning_behavior=VersioningBehavior.AUTO_UPGRADE)
class AuditDocumentWorkflow:
    @workflow.run
    async def run(self, inp: AuditWorkflowInput) -> AuditWorkflowOutput:
        # 1. Fetch document record from store
        fetch_result: FetchDocumentResult = await workflow.execute_activity(
            fetch_document,
            FetchDocumentInput(
                document_id=inp.document_id,
                tenant_id=inp.tenant_id,
            ),
            retry_policy=_RETRY_TRANSIENT,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        if fetch_result.error:
            return AuditWorkflowOutput(
                document_id=inp.document_id,
                finding_ids=[],
                status="FAILED",
                error=fetch_result.error,
            )

        if inp.data is None or inp.mime_type is None or inp.file_size is None:
            # No payload: match the plain workflow (workflows.py) — mark READY.
            return AuditWorkflowOutput(
                document_id=inp.document_id,
                finding_ids=[],
                status="READY",
            )

        # 2. Validate document + check dedup
        validate_result: ValidateResult = await workflow.execute_activity(
            validate_and_dedup,
            ValidateInput(
                document_id=inp.document_id,
                tenant_id=inp.tenant_id,
                data=inp.data,
                mime_type=inp.mime_type,
                file_size=inp.file_size,
            ),
            retry_policy=_RETRY_TRANSIENT,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        if not validate_result.valid:
            return AuditWorkflowOutput(
                document_id=inp.document_id,
                finding_ids=[],
                status=validate_result.quarantine_type or "FAILED",
                duplicate_of=validate_result.duplicate_of,
                error=validate_result.error,
                failure_class=validate_result.failure_class,
            )

        # 3. Process PDF pages (if applicable)
        if inp.mime_type == "application/pdf":
            pdf_result: ProcessPdfResult = await workflow.execute_activity(
                process_pdf_activity,
                ProcessPdfInput(
                    document_id=inp.document_id,
                    data=inp.data,
                ),
                retry_policy=_RETRY_POISON,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            if pdf_result.error:
                return AuditWorkflowOutput(
                    document_id=inp.document_id,
                    finding_ids=[],
                    status="QUARANTINED",
                    error=pdf_result.error,
                    failure_class=FailureClass.POISON,
                )

        # 4. Classify, then extract:
        #    - text documents (contract/letter): VLM-only (report + key fields)
        #    - tabular documents: regex and VLM passes in parallel, then merge
        classify_result: ClassifyResult = await workflow.execute_activity(
            classify_activity,
            ClassifyInput(data=inp.data, mime_type=inp.mime_type),
            retry_policy=_RETRY_NONE,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        if classify_result.error:
            return AuditWorkflowOutput(
                document_id=inp.document_id,
                finding_ids=[],
                status="FAILED",
                error=classify_result.error,
                failure_class=FailureClass.LOGIC,
            )

        text_doc = classify_result.doc_type in TEXT_DOC_TYPES
        if text_doc:
            extract_result: ExtractResult = await workflow.execute_activity(
                vlm_text_extract_activity,
                ExtractInput(
                    document_id=inp.document_id,
                    tenant_id=inp.tenant_id,
                    data=inp.data,
                    mime_type=inp.mime_type,
                ),
                retry_policy=_RETRY_POISON,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
        else:
            regex_future = workflow.execute_activity(
                regex_extract_activity,
                ExtractInput(
                    document_id=inp.document_id,
                    tenant_id=inp.tenant_id,
                    data=inp.data,
                    mime_type=inp.mime_type,
                ),
                retry_policy=_RETRY_POISON,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            vlm_future = workflow.execute_activity(
                vlm_extract_activity,
                ExtractInput(
                    document_id=inp.document_id,
                    tenant_id=inp.tenant_id,
                    data=inp.data,
                    mime_type=inp.mime_type,
                ),
                retry_policy=_RETRY_POISON,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            regex_result, vlm_result = await asyncio.gather(regex_future, vlm_future)
            merge_result: MergeResult = await workflow.execute_activity(
                merge_extractions_activity,
                MergeInput(
                    document_id=inp.document_id,
                    regex_document=regex_result.document,
                    vlm_document=vlm_result.document,
                ),
                retry_policy=_RETRY_NONE,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            if merge_result.error:
                return AuditWorkflowOutput(
                    document_id=inp.document_id,
                    finding_ids=[],
                    status="FAILED",
                    error=merge_result.error,
                    failure_class=FailureClass.POISON,
                )
            extract_result = ExtractResult(
                document=merge_result.document,
                raw_text=regex_result.raw_text or vlm_result.raw_text,
            )

        if extract_result.error or extract_result.document is None:
            return AuditWorkflowOutput(
                document_id=inp.document_id,
                finding_ids=[],
                status="FAILED",
                error=extract_result.error or "Extraction returned None",
                failure_class=FailureClass.POISON,
            )

        # 5. Security scan (§5 prompt-injection detection)
        scan_result: SecurityScanResult = await workflow.execute_activity(
            security_scan_activity,
            SecurityScanInput(
                document_id=inp.document_id,
                raw_text=extract_result.raw_text,
                data=inp.data,
            ),
            retry_policy=_RETRY_NONE,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        if scan_result.is_suspicious:
            return AuditWorkflowOutput(
                document_id=inp.document_id,
                finding_ids=[],
                status="QUARANTINED_SECURITY",
                error=f"Security scan failed: {scan_result.summary}",
                failure_class=FailureClass.POLICY,
            )

        # 6. Route + run validators + emit findings
        emit_result: ValidateAndEmitResult = await workflow.execute_activity(
            validate_and_emit_activity,
            ValidateAndEmitInput(
                tenant_policy=inp.tenant_policy,
                ruleset_version=inp.ruleset_version,
                prompt_version=inp.prompt_version,
                model_version=inp.model_version,
                document=extract_result.document,
                current_date=inp.current_date,
            ),
            retry_policy=_RETRY_TRANSIENT,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        if emit_result.error:
            return AuditWorkflowOutput(
                document_id=inp.document_id,
                finding_ids=[],
                status="FAILED",
                error=emit_result.error,
                failure_class=FailureClass.LOGIC,
            )

        # 7. Persist final status
        final_status = "READY" if emit_result.coverage_complete else "INCOMPLETE"
        await workflow.execute_activity(
            persist_results_activity,
            PersistResultInput(
                document_id=inp.document_id,
                findings=emit_result.findings,
                status=final_status,
            ),
            start_to_close_timeout=timedelta(seconds=10),
        )

        return AuditWorkflowOutput(
            document_id=inp.document_id,
            finding_ids=[f.finding_id for f in emit_result.findings],
            findings=emit_result.findings,
            status=final_status,
            routing_rule_id=emit_result.routing_rule_id,
            requires_human_review=emit_result.requires_human_review,
        )
