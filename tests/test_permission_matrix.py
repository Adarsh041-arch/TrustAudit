"""Unit tests for permission matrix and separation of duties (PHASES_V2 §4 Phase 2)."""

from audit_v2.persistence.permission_matrix import (
    Action,
    Resource,
    Role,
    can_approve_finding,
    has_permission,
)


class TestPermissionMatrix:
    def test_admin_permissions(self):
        assert has_permission(Role.ADMIN, Resource.DOCUMENT, Action.DELETE) is True
        assert has_permission(Role.ADMIN, Resource.FINDING, Action.APPROVE) is True

    def test_viewer_permissions(self):
        assert has_permission(Role.VIEWER, Resource.DOCUMENT, Action.READ) is True
        assert has_permission(Role.VIEWER, Resource.DOCUMENT, Action.DELETE) is False
        assert has_permission(Role.VIEWER, Resource.FINDING, Action.APPROVE) is False

    def test_separation_of_duties_rule_configurer_cannot_approve_own_rule(self):
        # Reviewer approving finding for rule configured by someone else -> OK
        ok, err = can_approve_finding(
            actor_role=Role.REVIEWER,
            actor_id="reviewer_user",
            rule_configured_by_actor_id="configurer_user",
        )
        assert ok is True
        assert err is None

        # Configurer attempting to approve finding for a rule configured by themselves -> VIOLATION
        ok, err = can_approve_finding(
            actor_role=Role.ADMIN,
            actor_id="configurer_user",
            rule_configured_by_actor_id="configurer_user",
        )
        assert ok is False
        assert "Separation of duties violation" in err

    def test_role_lacking_approve_permission(self):
        ok, err = can_approve_finding(
            actor_role=Role.AUDITOR,
            actor_id="auditor_user",
            rule_configured_by_actor_id="configurer_user",
        )
        assert ok is False
        assert "lacks approval permission" in err
