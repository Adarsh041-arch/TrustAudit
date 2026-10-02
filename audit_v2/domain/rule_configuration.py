"""Tenant rule overlays over the versioned built-in catalog."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from audit_v2.domain.models import CheckCatalog, CheckCatalogEntry

EDITABLE_BUILTIN_FIELDS = {
    "enabled",
    "severity",
    "score_weight",
    "score_impact",
    "blocking",
    "applies_to",
    "requires_human_review",
}


def empty_rule_configuration() -> dict[str, Any]:
    return {"revision": 0, "overrides": {}, "custom_rules": [], "history": []}


def normalize_rule_configuration(value: dict[str, Any] | None) -> dict[str, Any]:
    base = empty_rule_configuration()
    if not isinstance(value, dict):
        return base
    base["revision"] = max(0, int(value.get("revision", 0)))
    base["overrides"] = deepcopy(value.get("overrides", {}))
    base["custom_rules"] = deepcopy(value.get("custom_rules", []))
    base["history"] = deepcopy(value.get("history", []))[-500:]
    return base


def effective_checks(
    base_catalog: CheckCatalog,
    configuration: dict[str, Any] | None,
    *,
    include_disabled: bool = False,
) -> list[CheckCatalogEntry]:
    config = normalize_rule_configuration(configuration)
    checks: list[CheckCatalogEntry] = []
    for original in base_catalog.checks:
        raw_override = config["overrides"].get(original.check_id, {})
        override = {
            key: value for key, value in raw_override.items() if key in EDITABLE_BUILTIN_FIELDS
        }
        entry = CheckCatalogEntry.model_validate({**original.model_dump(), **override})
        if include_disabled or entry.enabled:
            checks.append(entry)
    for raw in config["custom_rules"]:
        entry = CheckCatalogEntry.model_validate(raw)
        if include_disabled or entry.enabled:
            checks.append(entry)
    return checks


def rule_response(base_catalog: CheckCatalog, configuration: dict[str, Any] | None) -> dict:
    config = normalize_rule_configuration(configuration)
    configured_ids = set(config["overrides"])
    rules = []
    for entry in effective_checks(base_catalog, config, include_disabled=True):
        row = entry.model_dump(mode="json")
        row["configured"] = entry.source == "custom" or entry.check_id in configured_ids
        rules.append(row)
    return {
        "catalog_version": base_catalog.catalog_version,
        "revision": config["revision"],
        "rules": rules,
        "history": config["history"][-30:],
    }
