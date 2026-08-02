from __future__ import annotations

from pydantic import BaseModel


class RoutingRule(BaseModel):
    rule_id: str
    doc_type: str
    value_band_min: str
    value_band_max: str
    tenant_policy: str
    include_checks: list[str]
    exclude_checks: list[str] = []


class RoutingDecision(BaseModel):
    rule_id: str
    included_check_ids: list[str]
    skipped_check_ids: dict[str, str]
