"""Retained local job inputs and restart recovery; SQLite remains single-host."""
import asyncio
import uuid

from fastapi import HTTPException

from audit_v2.persistence.artifact_store import ArtifactStore
from audit_v2.pipeline.events import NullProgressSink

_running: dict[tuple[str, str], asyncio.Task] = {}


def register(tenant: str, job_id: str, payload: list[tuple[str, bytes, str]]) -> None:
    from audit_v2 import server

    store = ArtifactStore()
    files = [{"filename": name, "mime_type": mime, "digest": store.put(tenant, data)}
             for name, data, mime in payload]
    with server.OPERATIONAL_STORE.transaction(tenant) as tx:
        state = tx.load() or {}
        state.setdefault("jobs", {})[job_id] = {"files": files, "status": "running"}
        tx.save(state, "job_accepted")


def mark(tenant: str, job_id: str, status: str) -> None:
    from audit_v2 import server

    with server.OPERATIONAL_STORE.transaction(tenant) as tx:
        state = tx.load() or {}
        if job_id in state.get("jobs", {}):
            state["jobs"][job_id]["status"] = status
            tx.save(state, "job_status_changed")


def _state(tenant: str, job_id: str) -> dict:
    from audit_v2 import server

    with server.OPERATIONAL_STORE.transaction(tenant) as tx:
        state = tx.load() or {}
    if job_id not in state.get("jobs", {}):
        raise HTTPException(404, "Unknown job")
    return state


async def _resume(tenant: str, job_id: str, files: list[dict]) -> None:
    from audit_v2 import server

    try:
        store = ArtifactStore()
        payload = [(f["filename"], await asyncio.to_thread(store.get, tenant, f["digest"]),
                    f["mime_type"]) for f in files]
        await asyncio.to_thread(server._process_documents, payload, tenant, NullProgressSink(),
                                operation_id=job_id)
        await asyncio.to_thread(mark, tenant, job_id, "done")
    except Exception:
        await asyncio.to_thread(mark, tenant, job_id, "failed")
    finally:
        _running.pop((tenant, job_id), None)


async def result(tenant: str, job_id: str) -> dict:
    state = await asyncio.to_thread(_state, tenant, job_id)
    receipt = state.get("operations", {}).get(job_id)
    if receipt:
        return {"status": "done", "result": receipt["result"]}
    if job_id in state.get("cancelled_operations", []):
        return {"status": "failed", "error": "Audit was cancelled"}
    job = state["jobs"][job_id]
    if job["status"] == "failed":
        return {"status": "failed", "error": "Audit failed; retry the retained job"}
    if (tenant, job_id) not in _running:
        task = asyncio.create_task(_resume(tenant, job_id, job["files"]))
        _running[(tenant, job_id)] = task
    return {"status": "running"}


async def retry(tenant: str, job_id: str) -> str:
    from audit_v2 import server

    state = await asyncio.to_thread(_state, tenant, job_id)
    if job_id in state.get("operations", {}):
        raise HTTPException(409, "Audit already completed; use its saved result")
    if state["jobs"][job_id]["status"] == "running" and job_id not in state.get("cancelled_operations", []):
        await result(tenant, job_id)
        return job_id
    new_id = "job_" + uuid.uuid4().hex
    with server.OPERATIONAL_STORE.transaction(tenant) as tx:
        latest = tx.load() or {}
        latest.setdefault("jobs", {})[new_id] = {
            "files": state["jobs"][job_id]["files"], "status": "running", "retry_of": job_id,
        }
        tx.save(latest, "job_retry_accepted")
    await result(tenant, new_id)
    return new_id


async def cancel(tenant: str, job_id: str) -> None:
    from audit_v2 import server

    with server.OPERATIONAL_STORE.transaction(tenant) as tx:
        state = tx.load() or {}
        if job_id not in state.get("jobs", {}):
            raise HTTPException(404, "Unknown job")
        if job_id in state.get("operations", {}):
            raise HTTPException(409, "Audit already committed; cancellation cannot undo it")
        if job_id not in state.setdefault("cancelled_operations", []):
            state["cancelled_operations"].append(job_id)
        state["jobs"][job_id]["status"] = "cancelled"
        tx.save(state, "job_cancelled")
