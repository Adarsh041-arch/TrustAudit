"""Temporal worker entrypoint.

Runs the audit workflow worker connected to the Temporal server
defined in docker-compose.yml (localhost:7233).

Usage:
    python -m audit_v2.orchestration.worker
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

from audit_v2.ingestion.document_store import MemoryDocumentStore, PostgresDocumentStore
from audit_v2.orchestration.activities_temporal import (
    classify_activity,
    extract_activity,
    fetch_document,
    merge_extractions_activity,
    persist_results_activity,
    process_pdf_activity,
    regex_extract_activity,
    security_scan_activity,
    set_activity_store,
    validate_and_dedup,
    validate_and_emit_activity,
    vlm_extract_activity,
    vlm_text_extract_activity,
)
from audit_v2.orchestration.product_workflow import ProductAuditWorkflow, audit_product_batch
from audit_v2.orchestration.temporal_workflow import AuditDocumentWorkflow
from audit_v2.persistence.db import apply_schema
from audit_v2.persistence.db import connect as pg_connect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "audit-documents")
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")


def _build_store() -> MemoryDocumentStore | PostgresDocumentStore:
    dsn = os.getenv("AUDIT_PG_DSN")
    if dsn:
        conn = pg_connect(dsn)
        apply_schema(conn)
        tenant_id = os.getenv("AUDIT_TENANT_ID", "default")
        logger.info("Using PostgresDocumentStore (tenant=%s)", tenant_id)
        return PostgresDocumentStore(conn, tenant_id)
    logger.info("Using MemoryDocumentStore")
    return MemoryDocumentStore()


async def main() -> None:
    client = await Client.connect(TEMPORAL_HOST)

    store = _build_store()
    set_activity_store(store)

    worker = Worker(
        client=client,
        task_queue=TASK_QUEUE,
        workflows=[AuditDocumentWorkflow, ProductAuditWorkflow],
        activities=[
            audit_product_batch,
            fetch_document,
            validate_and_dedup,
            process_pdf_activity,
            classify_activity,
            regex_extract_activity,
            vlm_extract_activity,
            vlm_text_extract_activity,
            merge_extractions_activity,
            extract_activity,
            security_scan_activity,
            validate_and_emit_activity,
            persist_results_activity,
        ],
    )

    logger.info("Worker connected to %s, task queue: %s", TEMPORAL_HOST, TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
