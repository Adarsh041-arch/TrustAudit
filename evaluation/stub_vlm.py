"""Stub VLM client for offline baseline measurement.

Used only when GOOGLE_API_KEY is unavailable or the real Gemini
client fails to construct. Simulates plausible VLM behavior: a
generous PASS for most checks, an attempt at arithmetic via simple
regex on line items text — exactly the failure mode the original
plan identifies as B1.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.schemas import (
    AuditChecklist,
    DocumentAuditResult,
    DocumentSummary,
    FailedChecklistItem,
)


def _read_pdf_text(path: str) -> str:
    try:
        import fitz
        with fitz.open(path) as doc:
            return "\n".join(p.get_text() for p in doc)
    except Exception:
        return ""


_LINE_RE = re.compile(
    r"(?P<desc>[A-Za-z][A-Za-z0-9 /&\-]{2,})\s+"
    r"(?P<qty>\d+(?:\.\d+)?)\s+"
    r"(?P<rate>[\d,]+(?:\.\d+)?)\s+"
    r"(?P<amount>[\d,]+(?:\.\d+)?)"
)


def _stub_arithmetic_eval(file_path: str, rules: list) -> tuple[bool, float, list[dict]]:
    """Reproduce V1's LLM-Does-Math behavior deterministically, offline."""
    text = _read_pdf_text(file_path)
    failed: list[dict] = []
    if not text:
        return False, 0.0, []

    for rule in rules:
        rid = getattr(rule, "rule_id", "")
        if rid != "R003":
            continue

        has_line = False
        wrong = False
        for m in _LINE_RE.finditer(text):
            has_line = True
            try:
                qty = float(m["qty"].replace(",", ""))
                rate = float(m["rate"].replace(",", ""))
                stated = float(m["amount"].replace(",", ""))
                expected = round(qty * rate, 2)
                if abs(expected - stated) > 0.01:
                    wrong = True
                    break
            except Exception:
                continue

        if has_line and wrong:
            failed.append({
                "rule_id": "R003",
                "evidence": f"Stub arithmetic detected a mismatch in {Path(file_path).name}",
                "page_number": 1,
            })
        break

    total_rules = max(len(rules), 1)
    failed_count = len(failed)
    score = round(100.0 * (total_rules - failed_count) / total_rules, 2)
    mandatory_failed = any(
        getattr(r, "mandatory", False) for fr in failed
        for r in rules if getattr(r, "rule_id", "") == fr["rule_id"]
    )
    return (not mandatory_failed), score, failed


class StubVLMClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def summarize(self, file_path: str) -> DocumentSummary:
        return DocumentSummary(
            document_name=Path(file_path).name,
            document_type="invoice",
            page_count=1,
            summary=f"Stub summary for {Path(file_path).name}",
            language="English",
            metadata={"stub": True, "path": file_path},
        )

    def audit(
        self, file_path: str, summary: DocumentSummary, checklist: AuditChecklist
    ) -> DocumentAuditResult:
        passed, score, failed_raw = _stub_arithmetic_eval(file_path, checklist.rules)

        failed_rules: list[FailedChecklistItem] = []
        for item in failed_raw:
            fr = FailedChecklistItem(
                rule_id=item["rule_id"],
                rule_title=item.get("rule_id", ""),
                description="",
                severity="high",
                evidence=item.get("evidence", ""),
                page_number=item.get("page_number"),
            )
            failed_rules.append(fr)

        return DocumentAuditResult(
            document_name=summary.document_name,
            passed=passed,
            score=score,
            failed_rules=failed_rules,
            remarks=f"Stub VLM (offline). LLM-Does-Math reproduction active.",
        )


def install_stub_if_no_key() -> None:
    """If GOOGLE_API_KEY is absent, monkey-patch app.vlm.get_vlm_client.

    Returns the stub instance for direct use. Mutates globals in
    app.vlm to avoid touching app.graph module structure.
    """
    if os.getenv("GOOGLE_API_KEY"):
        return
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: F401
    except Exception:
        pass

    import app.vlm as vlm_mod

    def _stub_get(*args: Any, **kwargs: Any) -> StubVLMClient:
        return StubVLMClient()

    vlm_mod.get_vlm_client = _stub_get  # type: ignore[assignment]
    vlm_mod._client = StubVLMClient()  # type: ignore[assignment]
