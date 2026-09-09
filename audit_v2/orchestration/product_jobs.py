"""Tenant-authorized Temporal dispatch with small content-addressed references."""

import asyncio
import hashlib
import json
import os
import uuid

from fastapi import HTTPException
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from audit_v2.persistence.artifact_store import ArtifactStore


async def client():
    return await Client.connect(os.getenv("TEMPORAL_HOST", "localhost:7233"))


def _prefix(tenant: str) -> str:
    return "audit-" + hashlib.sha256(tenant.encode()).hexdigest()[:24] + "-"


async def submit(tenant: str, payload: list[tuple[str, bytes, str]]) -> str:
    store = ArtifactStore()
    files = []
    for name, data, mime in payload:
        files.append(
            {
                "filename": name,
                "mime_type": mime,
                "digest": await asyncio.to_thread(store.put, tenant, data),
            }
        )
    job_id = _prefix(tenant) + uuid.uuid4().hex
    from audit_v2.orchestration.local_jobs import register

    await asyncio.to_thread(register, tenant, job_id, payload)
    await (await client()).start_workflow(
        "ProductAuditWorkflow",
        {"tenant_id": tenant, "files": files, "operation_id": job_id},
        id=job_id,
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "audit-documents"),
    )
    return job_id


async def cancel(tenant: str, job_id: str) -> None:
    from audit_v2.orchestration import local_jobs

    if not job_id.startswith(_prefix(tenant)):
        raise HTTPException(404, "Unknown job")
    await local_jobs.cancel(tenant, job_id)
    await (await client()).get_workflow_handle(job_id).cancel()


async def retry(tenant: str, job_id: str) -> str:
    from audit_v2 import server
    from audit_v2.orchestration.local_jobs import _state

    state = await asyncio.to_thread(_state, tenant, job_id)
    if job_id in state.get("operations", {}):
        raise HTTPException(409, "Audit already completed; use its saved result")
    current = await result(tenant, job_id)
    if current["status"] == "running":
        return job_id
    new_id = _prefix(tenant) + uuid.uuid4().hex
    files = state["jobs"][job_id]["files"]
    with server.OPERATIONAL_STORE.transaction(tenant) as tx:
        latest = tx.load() or {}
        latest.setdefault("jobs", {})[new_id] = {
            "files": files, "status": "running", "retry_of": job_id,
        }
        tx.save(latest, "job_retry_accepted")
    await (await client()).start_workflow(
        "ProductAuditWorkflow", {"tenant_id": tenant, "files": files, "operation_id": new_id},
        id=new_id, task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "audit-documents"),
    )
    return new_id


async def result(tenant: str, job_id: str) -> dict:
    if not job_id.startswith(_prefix(tenant)):
        raise HTTPException(404, "Unknown job")
    try:
        handle = (await client()).get_workflow_handle(job_id)
        description = await handle.describe()
        if description.status == WorkflowExecutionStatus.RUNNING:
            return {"status": "running"}
        if description.status != WorkflowExecutionStatus.COMPLETED:
            return {
                "status": "failed",
                "error": "Audit job did not complete; retry from the retained source files",
            }
        reference = await handle.result()
        if reference.get("tenant_id") != tenant:
            raise HTTPException(404, "Unknown job")
        data = await asyncio.to_thread(ArtifactStore().get, tenant, reference["result_digest"])
        return {"status": "done", "result": json.loads(data)}
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(404, "Unknown job") from None
        raise HTTPException(503, "Durable job service unavailable") from None
