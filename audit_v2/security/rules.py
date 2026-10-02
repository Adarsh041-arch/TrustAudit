"""Tenant-scoped rule configuration API with optimistic concurrency."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from audit_v2.domain.models import (
    CheckCatalogEntry,
    CustomRuleDefinition,
    DocumentType,
    Severity,
    ToleranceSpec,
)
from audit_v2.domain.rule_configuration import (
    EDITABLE_BUILTIN_FIELDS,
    normalize_rule_configuration,
    rule_response,
)
from audit_v2.domain.validators.custom import ALLOWED_FIELDS
from audit_v2.persistence.permission_matrix import Resource
from audit_v2.security.auth import principal, require_rule_configurer

router = APIRouter(prefix="/api/v2/rules", tags=["rules"])


class RulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    title: str | None = Field(default=None, min_length=3, max_length=160)
    failure_message: str | None = Field(default=None, min_length=3, max_length=500)
    enabled: bool | None = None
    severity: Severity | None = None
    score_weight: float | None = Field(default=None, ge=0, le=100)
    score_impact: bool | None = None
    blocking: bool | None = None
    requires_human_review: bool | None = None
    applies_to: list[DocumentType] | None = Field(default=None, min_length=1)
    custom_definition: CustomRuleDefinition | None = None

    @model_validator(mode="after")
    def validate_document_types(self) -> RulePatch:
        if self.applies_to and DocumentType.UNKNOWN in self.applies_to:
            raise ValueError("Select known document types")
        return self


class CustomRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    title: str = Field(min_length=3, max_length=160)
    failure_message: str = Field(min_length=3, max_length=500)
    severity: Severity = Severity.MEDIUM
    score_weight: float = Field(default=10, ge=0, le=100)
    score_impact: bool = True
    blocking: bool = True
    requires_human_review: bool = False
    enabled: bool = True
    applies_to: list[DocumentType] = Field(min_length=1)
    definition: CustomRuleDefinition

    @model_validator(mode="after")
    def reject_unknown_documents(self) -> CustomRuleCreate:
        if DocumentType.UNKNOWN in self.applies_to:
            raise ValueError("Custom checks cannot target unknown document types")
        return self


class RevisionRequest(BaseModel):
    expected_revision: int = Field(ge=0)


def _load(server: Any, tenant: str) -> dict[str, Any]:
    return normalize_rule_configuration(server.RULE_CONFIG_STORE.get(tenant))


def _assert_revision(config: dict[str, Any], expected: int) -> None:
    if config["revision"] != expected:
        raise HTTPException(409, "Rules changed; reload before saving")


def _commit(server: Any, actor: Any, config: dict[str, Any], action: str, check_id: str) -> dict:
    config["revision"] += 1
    config["history"].append(
        {
            "revision": config["revision"],
            "action": action,
            "check_id": check_id,
            "actor_id": actor.actor_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    config["history"] = config["history"][-500:]
    with server._PROCESS_LOCK, server.OPERATIONAL_STORE.transaction(actor.tenant_id) as tx:
        state = tx.load() or {}
        current = normalize_rule_configuration(state.get("rule_configuration"))
        _assert_revision(current, config["revision"] - 1)
        server._restore(actor.tenant_id, state)
        try:
            server.RULE_CONFIG_STORE[actor.tenant_id] = config
            server.AUDIT_LOG.log(
                entry_id=f"log_{uuid.uuid4().hex[:8]}",
                tenant_id=actor.tenant_id,
                action=action,
                resource_type=Resource.RULESET,
                resource_id=check_id,
                actor_id=actor.actor_id,
                payload={"revision": config["revision"]},
            )
            server._process_documents_impl([], actor.tenant_id, server.NullProgressSink())
            tx.save(server._snapshot(actor.tenant_id), "rule_configuration_changed")
        except Exception:
            server._restore(actor.tenant_id, state)
            raise
    return rule_response(server.CATALOG, config)


@router.get("")
def list_rules() -> dict:
    from audit_v2 import server

    actor = principal()
    response = rule_response(server.CATALOG, _load(server, actor.tenant_id))
    response["fields"] = sorted(ALLOWED_FIELDS)
    response["can_edit"] = (
        actor.role.value in {"admin", "rule_configurer"}
        or os.getenv("V2_AUTH_MODE", "local") == "local"
    )
    return response


@router.post("")
def create_rule(payload: CustomRuleCreate) -> dict:
    from audit_v2 import server

    actor = require_rule_configurer()
    config = _load(server, actor.tenant_id)
    _assert_revision(config, payload.expected_revision)
    if len(config["custom_rules"]) >= 100:
        raise HTTPException(422, "A tenant can configure at most 100 custom checks")
    rule_token = uuid.uuid4().hex[:12].upper().translate(str.maketrans("0123456789", "GHIJKLMNOP"))
    check_id = f"CHK-CUSTOM-{rule_token}-001"
    entry = CheckCatalogEntry.model_validate(
        dict(
            check_id=check_id,
            title=payload.title,
            category="format_completeness",
            applies_to=payload.applies_to,
            severity=payload.severity,
            determinism="deterministic",
            inputs=[payload.definition.field_path],
            tolerance=ToleranceSpec(type="none", value="0"),
            failure_message=payload.failure_message,
            requires_human_review=payload.requires_human_review,
            blocking=payload.blocking,
            requirement_level="control",
            score_impact=payload.score_impact,
            score_weight=payload.score_weight,
            enabled=payload.enabled,
            source="custom",
            custom_definition=payload.definition,
        )
    )
    config["custom_rules"].append(entry.model_dump(mode="json"))
    return _commit(server, actor, config, "custom_rule_created", check_id)


@router.put("/{check_id}")
def update_rule(check_id: str, payload: RulePatch) -> dict:
    from audit_v2 import server

    actor = require_rule_configurer()
    config = _load(server, actor.tenant_id)
    _assert_revision(config, payload.expected_revision)
    updates = payload.model_dump(exclude={"expected_revision"}, exclude_none=True, mode="json")
    built_in = next((c for c in server.CATALOG.checks if c.check_id == check_id), None)
    if built_in is not None:
        forbidden = set(updates) - EDITABLE_BUILTIN_FIELDS
        if forbidden:
            raise HTTPException(
                422, f"Built-in check fields cannot be changed: {sorted(forbidden)}"
            )
        merged = {**config["overrides"].get(check_id, {}), **updates}
        CheckCatalogEntry.model_validate({**built_in.model_dump(mode="json"), **merged})
        config["overrides"][check_id] = merged
    else:
        index = next(
            (i for i, row in enumerate(config["custom_rules"]) if row["check_id"] == check_id),
            None,
        )
        if index is None:
            raise HTTPException(404, "Rule not found")
        candidate = {**config["custom_rules"][index], **updates}
        candidate["inputs"] = [candidate["custom_definition"]["field_path"]]
        config["custom_rules"][index] = CheckCatalogEntry.model_validate(candidate).model_dump(
            mode="json"
        )
    return _commit(server, actor, config, "rule_updated", check_id)


@router.delete("/{check_id}")
def delete_or_reset_rule(check_id: str, payload: RevisionRequest) -> dict:
    from audit_v2 import server

    actor = require_rule_configurer()
    config = _load(server, actor.tenant_id)
    _assert_revision(config, payload.expected_revision)
    if any(c.check_id == check_id for c in server.CATALOG.checks):
        if check_id not in config["overrides"]:
            raise HTTPException(404, "Built-in rule has no tenant override")
        del config["overrides"][check_id]
        action = "builtin_rule_reset"
    else:
        before = len(config["custom_rules"])
        config["custom_rules"] = [
            row for row in config["custom_rules"] if row["check_id"] != check_id
        ]
        if len(config["custom_rules"]) == before:
            raise HTTPException(404, "Rule not found")
        action = "custom_rule_deleted"
    return _commit(server, actor, config, action, check_id)
