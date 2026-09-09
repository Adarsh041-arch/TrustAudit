"""Production workflow for the SAME evidence pipeline exposed by the V2 API."""

import asyncio
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy


@activity.defn
async def audit_product_batch(payload: dict) -> dict:
    import json

    from audit_v2.persistence.artifact_store import ArtifactStore
    from audit_v2.pipeline.events import NullProgressSink
    from audit_v2.server import _process_documents

    store = ArtifactStore()
    tenant = payload["tenant_id"]
    batch = [
        (f["filename"], store.get(tenant, f["digest"]), f["mime_type"]) for f in payload["files"]
    ]
    task = asyncio.create_task(
        asyncio.to_thread(
            _process_documents, batch, tenant, NullProgressSink(),
            operation_id=payload["operation_id"],
        )
    )
    try:
        while not task.done():
            activity.heartbeat("Audit processing")
            await asyncio.wait({task}, timeout=10)
        result = await task
        digest = await asyncio.to_thread(
            store.put, tenant, json.dumps(result, default=str).encode()
        )
        return {"result_digest": digest, "tenant_id": tenant}
    finally:
        # A cancellation does not authorize clearing any persisted audit state.
        if not task.done():
            task.cancel()


@workflow.defn
class ProductAuditWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> dict:
        return await workflow.execute_activity(
            "audit_product_batch",
            payload,
            start_to_close_timeout=timedelta(hours=2),
            heartbeat_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
