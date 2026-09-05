"""Streaming job registry + SSE sink (new_requirements.md §6, Phase 2).

The synchronous pipeline emits :class:`~audit_v2.pipeline.events.StepEvent`\\s to a
:class:`~audit_v2.pipeline.events.ProgressSink`. To stream them to the browser we
run the (blocking) batch in a worker thread and bridge its events onto the event
loop's :class:`asyncio.Queue` via ``loop.call_soon_threadsafe`` — ``asyncio.Queue``
is *not* thread-safe, so that hop is mandatory, not cosmetic. An SSE
``StreamingResponse`` then drains the queue frame by frame; a terminal
:data:`SENTINEL` tells the generator to stop and emit the final result.

This is a single-process, in-memory store: jobs do not survive a restart and do
not fan out across workers. :class:`JobRegistry` bounds memory with an LRU cap +
TTL so a client that never connects (or never fetches its result) can't leak.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from audit_v2.pipeline.events import StepEvent

#: Enqueued once processing finishes so the SSE generator stops draining.
SENTINEL = object()


@dataclass
class PipelineJob:
    """One streaming upload job and its loop-bound event queue."""

    job_id: str
    tenant_id: str
    queue: asyncio.Queue[Any]
    loop: asyncio.AbstractEventLoop
    status: str = "running"  # running | done | error
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)


class QueueSink:
    """A ``ProgressSink`` that forwards worker-thread events to the loop's queue.

    ``emit`` is called from the worker thread running the pipeline; it must not
    touch the ``asyncio.Queue`` directly. ``call_soon_threadsafe`` schedules the
    ``put_nowait`` on the loop thread that owns the queue.
    """

    def __init__(self, job: PipelineJob) -> None:
        self._job = job

    def emit(self, event: StepEvent) -> None:
        self._job.loop.call_soon_threadsafe(self._job.queue.put_nowait, event)


class JobRegistry:
    """Bounded in-memory registry of streaming jobs (single process only)."""

    def __init__(self, max_jobs: int = 64, ttl_seconds: float = 1800.0) -> None:
        self._jobs: dict[str, PipelineJob] = {}
        self._max_jobs = max_jobs
        self._ttl = ttl_seconds

    def create(self, tenant_id: str, loop: asyncio.AbstractEventLoop) -> PipelineJob:
        """Register a new job. The queue is created *before* the worker starts,
        so events emitted before the SSE client connects are buffered, not lost."""
        self._evict()
        job = PipelineJob(
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            queue=asyncio.Queue(),
            loop=loop,
        )
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> PipelineJob | None:
        return self._jobs.get(job_id)

    def finish(
        self,
        job: PipelineJob,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Mark a job done/errored and signal the SSE generator to terminate.

        ``result`` is set *before* the sentinel is enqueued, so by the time the
        generator reads the sentinel the result is guaranteed visible.
        """
        if error is not None:
            job.status, job.error = "error", error
        else:
            job.status, job.result = "done", result
        job.loop.call_soon_threadsafe(job.queue.put_nowait, SENTINEL)

    def _evict(self) -> None:
        """Drop TTL-expired jobs, then cap the registry to ``max_jobs`` (oldest first)."""
        now = time.monotonic()
        for jid in [j for j, job in self._jobs.items() if now - job.created_at > self._ttl]:
            self._jobs.pop(jid, None)
        overflow = len(self._jobs) - self._max_jobs + 1
        if overflow > 0:
            oldest = sorted(self._jobs.items(), key=lambda kv: kv[1].created_at)
            for jid, _ in oldest[:overflow]:
                self._jobs.pop(jid, None)
