from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReconciliationResult:
    accepted: int
    completed: int
    quarantined: int
    failed: int
    in_flight: int
    discrepancy: int


def reconcile(
    accepted: int,
    completed: int,
    quarantined: int,
    failed: int,
    in_flight: int,
) -> ReconciliationResult:
    total = completed + quarantined + failed + in_flight
    return ReconciliationResult(
        accepted=accepted,
        completed=completed,
        quarantined=quarantined,
        failed=failed,
        in_flight=in_flight,
        discrepancy=accepted - total,
    )
