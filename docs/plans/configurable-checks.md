# Configurable document checks

Implemented 2026-10-02. Access the check manager in Settings → Workspace checks.

## Plan and behavior

1. Overlay the versioned built-in catalog with tenant-owned settings. Users can enable/disable checks, choose document types, priority, exact score deduction, and whether a failure blocks clearance.
2. Create custom conditions over extracted headers, line items, taxes, certificate goods, or contract narrative. Supported conditions: presence, equality/inequality, contains/prefix/suffix, greater/less than, and inclusive numeric range. Repeated rows support every-row or any-row evaluation. Empty collections fail; invalid numeric evidence goes to review.
3. Persist configuration versions and change history in the operational database. Reject stale edits using a version number. Apply changes and re-evaluate existing tenant documents in one transaction, without re-running extraction. Prior operational snapshots retain the original decisions.
4. Record configured score weights in findings and rule versions in document results. Deduct weights from a starting score of 100, capped at zero. Score deductions and blocking decisions are independent. Existing recommended-field defaults remain advisory unless explicitly customized.
5. Expose an accessible editor with search, custom rule builder, reset built-in defaults, delete custom rule, and recent change history. Enforce admin/rule-configurer permission in hosted mode; local loopback mode supports configuration for development.
6. Verify persistence, tenant isolation, role authorization, optimistic concurrency, safe conditions, custom weights, disabled checks, and upload integration. Run the existing backend suite and frontend production build.

## API

- GET `/api/v2/rules`: effective checks, revision, editor permissions, supported fields, recent changes.
- POST `/api/v2/rules`: create a custom check with `expected_revision` and a declarative definition.
- PUT `/api/v2/rules/{check_id}`: edit settings with `expected_revision`.
- DELETE `/api/v2/rules/{check_id}`: reset a built-in override or remove a custom check.

Custom checks evaluate fields the extractor provides. Adding a new field requires extraction support. Existing model-assisted catalog definitions remain clearly labelled as unavailable for automatic execution. Freeform executable code and arbitrary regular expressions are not accepted.

Configured rules alter the tenant's audit scope; statutory rule overrides do not establish legal compliance. Automatic clearance remains governed by the existing release gate.
