from __future__ import annotations

import hashlib


def compute_content_hash(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def is_duplicate(
    existing_hash: str,
    incoming_hash: str,
    existing_tenant: str,
    incoming_tenant: str,
) -> bool:
    return existing_hash == incoming_hash and existing_tenant == incoming_tenant
