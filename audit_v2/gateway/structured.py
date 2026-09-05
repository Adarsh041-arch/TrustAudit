"""Robust structured extraction over a schema-capable vision gateway.

``extract_structured`` returns a validated Pydantic instance regardless of
whether the hosted model honours guided decoding:

1. Ask with ``response_schema`` (llama.cpp/OpenAI-compatible JSON schema).
2. If the endpoint rejects guided decoding (``RuntimeError`` from a 400/422),
   fall back to embedding the schema in the prompt and parsing the free reply.
3. Validate against the target model. On ``ValidationError`` do one correction
   round-trip that echoes the errors, then give up (raise).

Network is only ever touched through the injected gateway, so tests mock it.
"""
from __future__ import annotations

import json
import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from audit_v2.extraction.vlm_extractor import parse_vlm_json
from audit_v2.gateway.vision_gateway import VisionGateway

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _schema_prompt(prompt: str, schema: dict) -> str:
    return (
        f"{prompt}\n\n"
        "Return ONLY a single JSON object conforming to this JSON Schema. "
        "No prose, no markdown fences — nothing before the opening { or after "
        f"the closing }}.\n\nJSON Schema:\n{json.dumps(schema)}"
    )


def _request_content(
    gateway: VisionGateway,
    images: list[bytes],
    prompt: str,
    schema: dict,
    tenant_id: str,
    max_tokens: int | None,
) -> str:
    """First attempt: guided_json, falling back to prompt-embedded schema."""
    try:
        limited = getattr(gateway, "extract_limited", None)
        if max_tokens is not None and callable(limited):
            resp = limited(
                images=images, prompt=prompt, tenant_id=tenant_id,
                response_schema=schema, max_tokens=max_tokens,
            )
        else:
            resp = gateway.extract(
                images=images, prompt=prompt, tenant_id=tenant_id,
                response_schema=schema,
            )
        return resp.content
    except RuntimeError as err:
        # Permanent rejection (e.g. HTTP 400/422): the hosted model likely does
        # not support guided_json. Retry once without it, schema in the prompt.
        logger.info(
            "guided_json rejected for tenant %s (%s); retrying schema-in-prompt",
            tenant_id, err,
        )
        limited = getattr(gateway, "extract_limited", None)
        if max_tokens is not None and callable(limited):
            resp = limited(
                images=images,
                prompt=_schema_prompt(prompt, schema),
                tenant_id=tenant_id,
                max_tokens=max_tokens,
            )
        else:
            resp = gateway.extract(
                images=images,
                prompt=_schema_prompt(prompt, schema),
                tenant_id=tenant_id,
            )
        return resp.content


def extract_structured(
    gateway: VisionGateway,
    images: list[bytes],
    prompt: str,
    schema_model: type[T],
    tenant_id: str,
    max_validation_retries: int = 1,
    max_tokens: int | None = None,
) -> T:
    """Extract and validate a structured result, robust to endpoint capability."""
    schema = schema_model.model_json_schema()
    content = _request_content(gateway, images, prompt, schema, tenant_id, max_tokens)

    last_err: Exception | None = None
    for attempt in range(max_validation_retries + 1):
        try:
            parsed = parse_vlm_json(content)
        except ValueError as err:
            last_err = err
            parsed = None

        if parsed is not None:
            try:
                return schema_model.model_validate(parsed)
            except ValidationError as err:
                last_err = err

        if attempt >= max_validation_retries:
            break

        # One correction round-trip echoing what went wrong.
        correction = (
            f"{prompt}\n\nYour previous reply could not be used: {last_err}\n"
            "Return corrected JSON only, conforming to this schema:\n"
            f"{json.dumps(schema)}"
        )
        limited = getattr(gateway, "extract_limited", None)
        if max_tokens is not None and callable(limited):
            content = limited(
                images=images, prompt=correction, tenant_id=tenant_id,
                max_tokens=max_tokens,
            ).content
        else:
            content = gateway.extract(
                images=images, prompt=correction, tenant_id=tenant_id,
            ).content

    raise ValueError(
        f"Structured extraction failed for {schema_model.__name__}: {last_err}"
    ) from last_err
