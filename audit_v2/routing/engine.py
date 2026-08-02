from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from audit_v2.domain.models import DocumentType
from audit_v2.routing.models import RoutingDecision, RoutingRule

_DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "routing_rules.yaml"
)


@lru_cache(maxsize=8)
def load_rules(path: str | None = None) -> tuple[RoutingRule, ...]:
    resolved = Path(path) if path is not None else _DEFAULT_RULES_PATH
    with open(resolved) as f:
        data = yaml.safe_load(f)
    return tuple(RoutingRule(**r) for r in data["rules"])


def resolve(
    doc_type: DocumentType,
    total_value: Decimal | None,
    tenant_policy: str,
    catalog_check_ids: list[str],
    rules: list[RoutingRule] | None = None,
) -> RoutingDecision:
    if rules is None:
        rules = list(load_rules())

    for rule in rules:
        if rule.doc_type != doc_type.value:
            continue
        if total_value is not None:
            if Decimal(rule.value_band_min) > total_value:
                continue
            if Decimal(rule.value_band_max) < total_value:
                continue
        if rule.tenant_policy != tenant_policy:
            continue

        included = [c for c in rule.include_checks if c in catalog_check_ids]
        skipped = {
            c: f"Not applicable for {doc_type.value} per routing rule {rule.rule_id}"
            for c in catalog_check_ids
            if c not in included and c not in rule.exclude_checks
        }
        skipped.update({
            c: f"Excluded per routing rule {rule.rule_id}" for c in rule.exclude_checks
        })
        return RoutingDecision(
            rule_id=rule.rule_id,
            included_check_ids=included,
            skipped_check_ids=skipped,
        )

    return RoutingDecision(
        rule_id="NO_RULE",
        included_check_ids=[],
        skipped_check_ids={
            c: "No routing rule matched document" for c in catalog_check_ids
        },
    )
