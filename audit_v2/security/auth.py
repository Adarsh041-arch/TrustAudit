"""Server-owned identities. Local development is loopback-only and single-tenant."""

import asyncio
import hashlib
import hmac
import json
import os
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from audit_v2.persistence.permission_matrix import Role


@dataclass(frozen=True)
class Principal:
    actor_id: str
    tenant_id: str
    role: Role


CURRENT_PRINCIPAL: ContextVar[Principal | None] = ContextVar("audit_principal", default=None)


def principal() -> Principal:
    value = CURRENT_PRINCIPAL.get()
    if value is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return value


def require_reviewer() -> Principal:
    value = principal()
    if value.role not in {Role.REVIEWER, Role.ADMIN}:
        raise HTTPException(status_code=403, detail="Reviewer permission required")
    return value


async def authenticate(request: Request, call_next):
    if request.url.path == "/api/v2/health" or request.method == "OPTIONS":
        return await call_next(request)
    mode = os.getenv("V2_AUTH_MODE", "local")
    if mode == "local":
        if not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse(
                {"detail": "Local mode accepts loopback clients only"}, status_code=403
            )
        identity = Principal("local_reviewer", "tenant_default", Role.REVIEWER)
    elif mode == "token":
        credential = request.headers.get("authorization", "")
        if not credential.startswith("Bearer "):
            return JSONResponse({"detail": "Bearer authentication required"}, status_code=401)
        digest = hashlib.sha256(credential[7:].encode()).hexdigest()
        try:
            accounts = json.loads(os.environ.get("V2_AUTH_ACCOUNTS", "[]"))
            account = next(
                (a for a in accounts if hmac.compare_digest(a["token_sha256"], digest)), None
            )
            if account is None:
                return JSONResponse({"detail": "Invalid credentials"}, status_code=401)
            identity = Principal(account["actor_id"], account["tenant_id"], Role(account["role"]))
        except (ValueError, KeyError, TypeError):
            return JSONResponse(
                {"detail": "Authentication configuration unavailable"}, status_code=503
            )
    else:
        return JSONResponse({"detail": "Invalid authentication mode"}, status_code=503)
    if any(t != identity.tenant_id for t in request.query_params.getlist("tenant_id")):
        return JSONResponse({"detail": "Tenant access denied"}, status_code=403)
    # Populate legacy query parameters from authenticated scope, never the caller's identity.
    query = [(k, v) for k, v in request.query_params.multi_items() if k != "tenant_id"]
    query.append(("tenant_id", identity.tenant_id))
    request.scope["query_string"] = urlencode(query).encode()
    read_only_posts = {"/api/v2/audit/report", "/api/v2/copilot/chat", "/api/recon/report"}
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and identity.role in {Role.VIEWER, Role.AUDITOR, Role.RULE_CONFIGURER}
        and request.url.path not in read_only_posts
    ):
        return JSONResponse({"detail": "Write permission required"}, status_code=403)
    token = CURRENT_PRINCIPAL.set(identity)
    try:
        if request.url.path.startswith("/api/v2/"):
            from audit_v2.server import hydrate_tenant

            await asyncio.to_thread(hydrate_tenant, identity.tenant_id)
        return await call_next(request)
    finally:
        CURRENT_PRINCIPAL.reset(token)
