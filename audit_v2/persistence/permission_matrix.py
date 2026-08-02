"""Permission Matrix & Separation of Duties — Phase 2 Governance (PHASES_V2 §4 Phase 2).

Enforces Role-Based Access Control (RBAC) and Separation of Duties:
- Identity that configures rules cannot approve findings against those rules.
- Permission matrix per role x resource x action.
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    RULE_CONFIGURER = "rule_configurer"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class Resource(StrEnum):
    DOCUMENT = "document"
    FINDING = "finding"
    RULESET = "ruleset"
    AUDIT_LOG = "audit_log"
    TENANT_CONFIG = "tenant_config"


class Action(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    APPROVE = "approve"
    REJECT = "reject"


PERMISSION_MATRIX: dict[Role, dict[Resource, set[Action]]] = {
    Role.ADMIN: {
        Resource.DOCUMENT: {Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE},
        Resource.FINDING: {
            Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE, Action.APPROVE, Action.REJECT
        },

        Resource.RULESET: {Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE},
        Resource.AUDIT_LOG: {Action.READ},
        Resource.TENANT_CONFIG: {Action.READ, Action.UPDATE},
    },
    Role.RULE_CONFIGURER: {
        Resource.RULESET: {Action.CREATE, Action.READ, Action.UPDATE},
        Resource.DOCUMENT: {Action.READ},
        Resource.FINDING: {Action.READ},
        Resource.AUDIT_LOG: {Action.READ},
    },
    Role.REVIEWER: {
        Resource.DOCUMENT: {Action.READ},
        Resource.FINDING: {Action.READ, Action.APPROVE, Action.REJECT},
        Resource.RULESET: {Action.READ},
        Resource.AUDIT_LOG: {Action.READ},
    },
    Role.AUDITOR: {
        Resource.DOCUMENT: {Action.READ},
        Resource.FINDING: {Action.READ},
        Resource.RULESET: {Action.READ},
        Resource.AUDIT_LOG: {Action.READ},
    },
    Role.VIEWER: {
        Resource.DOCUMENT: {Action.READ},
        Resource.FINDING: {Action.READ},
    },
}


def has_permission(role: Role, resource: Resource, action: Action) -> bool:
    """Check if role has permission to perform action on resource."""
    role_perms = PERMISSION_MATRIX.get(role, {})
    allowed_actions = role_perms.get(resource, set())
    return action in allowed_actions


def can_approve_finding(
    actor_role: Role,
    actor_id: str,
    rule_configured_by_actor_id: str | None,
) -> tuple[bool, str | None]:
    """Check if actor can approve finding, enforcing Separation of Duties.

    Separation of Duties (PHASES_V2 §4 Phase 2):
    The identity that configures rules cannot approve findings against those rules.
    """
    if not has_permission(actor_role, Resource.FINDING, Action.APPROVE):
        return False, f"Role {actor_role} lacks approval permission"

    if rule_configured_by_actor_id is not None and actor_id == rule_configured_by_actor_id:
        return False, "Separation of duties violation: rule configurer cannot approve finding"

    return True, None
