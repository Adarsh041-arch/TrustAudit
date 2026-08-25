import base64
import datetime
import json
import os
from io import BytesIO
from functools import lru_cache
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

import sys

# langchain_core.language_models.base does an optional `from transformers import
# GPT2TokenizerFast` at import time; importing transformers scans all 600+ installed
# dists via importlib.metadata and takes 50-90s here (looks like a hang). Nothing in
# this project uses transformers, so block the optional import entirely.
# ponytail: remove if we ever actually need transformers.
sys.modules.setdefault("transformers", None)

import fitz
from PIL import Image
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama

from app.schemas import (
    AuditChecklist,
    DocumentAuditResult,
    DocumentSummary,
    FailedChecklistItem,
)
from app.logger import logger

SUPPORTED_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"})
MAX_PDF_PAGES = 10


class VLMContentBuilder:
    @staticmethod
    def _pil_to_b64(image: Image.Image) -> str:
        buf = BytesIO()
        image.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    @staticmethod
    def _file_to_b64(path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def _pdf_to_images(path: str) -> list[Image.Image]:
        images: list[Image.Image] = []
        doc = fitz.open(path)
        total = len(doc)
        pages = min(total, MAX_PDF_PAGES)
        if pages > 1:
            logger.info("  [VLM] Converting PDF (%d pages, rendering %d)", total, pages)
        for i in range(pages):
            pix = doc.load_page(i).get_pixmap()
            images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        doc.close()
        return images

    @classmethod
    def build(cls, file_path: str) -> list:
        # Callers mutate the returned list (insert prompt text at index 0),
        # so cache the immutable b64 payloads and rebuild the list per call.
        return [dict(part) for part in cls._build_cached(file_path)]

    @classmethod
    @lru_cache(maxsize=32)
    def _build_cached(cls, file_path: str) -> tuple:
        ext = os.path.splitext(file_path)[1].lower()
        content: list = []

        if ext in SUPPORTED_IMAGE_EXTS:
            b64 = cls._file_to_b64(file_path)
            mime = f"image/{ext.lstrip('.')}"
            if ext == ".jpg":
                mime = "image/jpeg"
            elif ext == ".tiff" or ext == ".tif":
                mime = "image/tiff"
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        elif ext == ".pdf":
            for img in cls._pdf_to_images(file_path):
                b64 = cls._pil_to_b64(img)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })

        return tuple(content)


def _detect_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}:
        return f"image/{ext.lstrip('.')}"
    return "application/octet-stream"


_SEVERITY_VALUES = frozenset({"critical", "high", "medium", "low"})


def _lookup_rule(checklist: AuditChecklist, rule_id: str) -> tuple[str, str, str]:
    for r in checklist.rules:
        if r.rule_id == rule_id:
            return r.title, r.description, r.severity
    return rule_id, "", "medium"


def _safe_failed_item(item: dict, checklist: AuditChecklist) -> FailedChecklistItem:
    rid = str(item.get("rule_id", "unknown"))
    title, description, severity = _lookup_rule(checklist, rid)

    if severity not in _SEVERITY_VALUES:
        severity = "medium"

    return FailedChecklistItem(
        rule_id=rid,
        rule_title=title,
        description=description,
        severity=severity,
        evidence=str(item.get("evidence", "")),
        page_number=item.get("page_number"),
    )


def _dedupe_keys(pairs: list) -> dict:
    seen: dict[str, int] = {}
    result: dict = {}
    for key, val in pairs:
        if key in seen:
            seen[key] += 1
        else:
            seen[key] = 1
        result[key] = val
    return result


class VLMClient:
    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        api_key: Optional[str] = None,
        provider: str = "google",
    ):
        if provider == "ollama":
            self.model = ChatOllama(
                model=model_name,
                temperature=0.1,
                num_predict=16384,
            )
        elif provider == "nvidia":
            from langchain_openai import ChatOpenAI

            self.model = ChatOpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=api_key or os.getenv("NVIDIA_API_KEY"),
                model=model_name,
                temperature=0.1,
                max_tokens=16384,
            )
        else:
            self.model = ChatGoogleGenerativeAI(
                model=model_name,
                api_key=api_key or os.getenv("GOOGLE_API_KEY"),
                temperature=0.1,
                max_output_tokens=16384,
            )
        self._provider = provider

    # ------------------------------------------------------------------
    # Document summarization
    # ------------------------------------------------------------------
    def summarize(self, file_path: str) -> DocumentSummary:
        doc_name = os.path.basename(file_path)
        logger.info("  [VLM] Summarizing %s ...", doc_name)
        content = VLMContentBuilder.build(file_path)
        if not content:
            return DocumentSummary(
                document_name=os.path.basename(file_path),
                document_type="unknown",
                summary="Unsupported or empty document.",
                language="unknown",
                metadata={"path": file_path, "error": "unable to load content"},
            )

        content.insert(
            0,
            {
                "type": "text",
                "text": (
                    "You are a document analysis assistant. Extract structured information from "
                    "the provided document image(s).\n\n"
                    "Return a JSON object with exactly these fields:\n"
                    '- "document_type": one of invoice, receipt, purchase_order, '
                    "delivery_challan, contract, certificate, or unknown\n"
                    '- "summary": 2-4 sentence summary covering: who the document is from and to, '
                    "what it is about, key dates, and total monetary amounts (if any)\n"
                    '- "language": the primary language detected (e.g. English, Spanish, French)\n'
                    '- "key_fields": an object with these optional extracted fields (use null if not found):\n'
                    '    * "document_number": the document identifier / invoice number / PO number\n'
                    '    * "date": the issue date of the document\n'
                    '    * "total_amount": the grand total as a number (omit currency symbol)\n'
                    '    * "currency": the currency code or symbol used\n'
                    '    * "vendor_name": the name of the issuer/supplier\n'
                    '    * "customer_name": the name of the recipient/buyer\n'
                    "Return ONLY valid JSON. No other text."
                ),
            },
        )

        text = self._invoke(content)
        if "error" in text:
            logger.info("  [VLM] API error - using fallback defaults")
        else:
            logger.info("  [VLM] Summary received (%.0f tokens)", len(text) / 4)
        data = self._parse_json(text, {"document_type": "unknown", "summary": "", "language": "unknown", "key_fields": {}})

        metadata: dict = {"path": file_path, "mime_type": _detect_mime_type(file_path)}
        key_fields = data.get("key_fields")
        if isinstance(key_fields, dict):
            for k, v in key_fields.items():
                if v is not None:
                    metadata[k] = v

        return DocumentSummary(
            document_name=os.path.basename(file_path),
            document_type=str(data.get("document_type", "unknown")),
            page_count=self._count_pages(file_path),
            summary=str(data.get("summary", "")),
            language=str(data.get("language", "unknown")),
            metadata=metadata,
        )

    @staticmethod
    def _count_pages(file_path: str) -> int:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            try:
                doc = fitz.open(file_path)
                n = len(doc)
                doc.close()
                return n
            except Exception:
                return 1
        return 1

    # ------------------------------------------------------------------
    # Single-document audit
    # ------------------------------------------------------------------
    def audit(
        self,
        file_path: str,
        summary: DocumentSummary,
        checklist: AuditChecklist,
    ) -> DocumentAuditResult:
        logger.info("  [VLM] Sending document + %d rules to Gemini ...", len(checklist.rules))
        content = VLMContentBuilder.build(file_path)

        rules_lines = "\n".join(
            f"- [{r.rule_id}] {r.title} ({r.severity}, "
            f"{'mandatory' if r.mandatory else 'optional'}): {r.description}"
            for r in checklist.rules
        )

        import re
        sanitized_name = summary.document_name
        sanitized_name = re.sub(r'\d{4}-\d{2}-\d{2}\s+at\s+\d{2}\.\d{2}\.\d{2}', '', sanitized_name)
        sanitized_name = re.sub(r'WhatsApp\s+Image\s*', '', sanitized_name, flags=re.IGNORECASE)
        sanitized_name = sanitized_name.strip()
        if not sanitized_name or sanitized_name.startswith('.'):
            sanitized_name = "document" + sanitized_name

        today = datetime.date.today()
        prompt = (
            "You are an audit compliance agent. Your task is to audit a business document "
            "against a compliance checklist.\n\n"
            f"Document: {sanitized_name}\n"
            f"Type: {summary.document_type}\n"
            f"Summary: {summary.summary}\n"
            f"Audit Date: {today.isoformat()}\n\n"
            f"Audit Checklist:\n{rules_lines}\n\n"
            "Instructions:\n"
            "1. Read each rule carefully, including its severity and whether it is mandatory.\n"
            "2. Examine the document image(s) for evidence related to that rule.\n"
            "3. MATHEMATICAL ACCURACY (Rule R003) — perform this check independently for every "
            "document, regardless of its type:\n"
            "   a. For each line item with quantity, unit price, and stated total:\n"
            "      - Extract: item name, quantity (Q), unit price (UP), stated total (ST)\n"
            "      - Compute: expected_total = Q × UP\n"
            "      - If expected_total != ST, this is a FAIL.\n"
            "        Report ALL three numbers in evidence, e.g.:\n"
            '        "Widget B: Q=5, UP=$30.00, expected $150.00 but stated $200.00 (overstated by $50.00)"\n'
            "   b. After checking every line, verify roll-ups:\n"
            "      - Calculate sum of all (correct) line-item totals\n"
            "      - Verify subtotal matches that sum\n"
            "      - If a tax percentage is given, compute: subtotal × rate / 100\n"
            "      - Verify the stated tax amount matches (allow $0.01 rounding)\n"
            "      - Verify grand total = subtotal + tax − discounts\n"
            "   c. Report EVERY arithmetic discrepancy — even $0.01 — with the exact numbers.\n"
            "      If all arithmetic is correct, do NOT report R003 as a failure.\n\n"
            "4. DATE VALIDITY & FUTURE DATES (Rule R005) - Compare the document date to the Audit Date. A document is ONLY future-dated if its date is strictly after the Audit Date (document_date > Audit Date). If document_date <= Audit Date, the document is NOT in the future, even if the year is 2026. For example: July 2026 is BEFORE August 2026, so a document dated 20 July 2026 is in the PAST relative to the Audit Date 2026-08-23, and it complies with R005.\n\n"
            "5. For each remaining rule (excluding R003 and R005 which are handled above), decide COMPLY or NOT COMPLY:\n"
            '   - COMPLY: The document clearly satisfies the rule. Specific evidence is visible.\n'
            '   - NOT COMPLY: The document violates the rule, or required information is clearly '
            "missing from the document. If the document type does not require a given rule "
            "(e.g., signature rule on a simple receipt), treat it as COMPLY.\n"
            "6. Only report rules that are NOT COMPLY in the failed_rules list.\n"
            "   Rules that COMPLY must be omitted from failed_rules.\n\n"
            'Return ONLY valid JSON with these fields:\n'
            '- "passed": boolean — true ONLY if ALL mandatory rules comply. '
            "Optional rules do not affect passed.\n"
            '- "score": float — percentage of ALL rules (mandatory + optional) that comply, 0-100\n'
            '- "failed_rules": list of objects for NOT COMPLY rules only, each with:\n'
            '    * "rule_id": string\n'
            '    * "evidence": specific quote, observation, or description from the document '
            "that demonstrates the failure. Be precise.\n"
            '    * "page_number": int or null — the page where the issue was observed. '
            "If you mention a specific page in the evidence, include its number here.\n"
            '- "remarks": string — brief summary of overall compliance posture and any notable '
            "observations or context\n"
            "Return ONLY valid JSON."
        )
        content.insert(0, {"type": "text", "text": prompt})

        text = self._invoke(content)
        if "error" in text:
            logger.info("  [VLM] API error - using fallback defaults")
        else:
            logger.info("  [VLM] Audit response received (%.0f tokens)", len(text) / 4)
        data = self._parse_json(text, {"passed": False, "score": 0.0, "failed_rules": [], "remarks": ""})

        failed = data.get("failed_rules", [])
        return DocumentAuditResult(
            document_name=summary.document_name,
            passed=bool(data.get("passed", False)),
            score=float(data.get("score", 0.0)),
            failed_rules=[_safe_failed_item(item, checklist) for item in failed if isinstance(item, dict)],
            remarks=str(data.get("remarks", "")),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _invoke(self, content: list) -> str:
        msg = HumanMessage(content=content)
        provider = getattr(self, "_provider", "google")
        logger.info("  [VLM] Calling %s ...", {"ollama": "Ollama", "nvidia": "NVIDIA API"}.get(provider, "Gemini API"))
        try:
            resp = self.model.invoke([msg])
            response_len = len(resp.content) if resp.content else 0
            logger.info("  [VLM] API responded (%d chars)", response_len)
            return resp.content if resp.content else ""
        except Exception as exc:
            logger.info("  [VLM] API call failed: %s", exc)
            return json.dumps({"error": str(exc)})

    @staticmethod
    def _parse_json(raw: str, fallback: dict) -> dict:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            pairs = json.loads(cleaned, object_pairs_hook=_dedupe_keys)
            return pairs if isinstance(pairs, dict) else fallback
        except json.JSONDecodeError:
            return fallback


_client: Optional[VLMClient] = None


def get_vlm_client(
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
) -> VLMClient:
    global _client
    if _client is None:
        provider = os.getenv("LLM_PROVIDER", "google")
        default_model = {
            "ollama": "gemma4:31b-cloud",
            "nvidia": "google/diffusiongemma-26b-a4b-it",
        }.get(provider, "gemini-2.5-flash")
        resolved = model_name or os.getenv("GEMINI_MODEL", default_model)
        _client = VLMClient(model_name=resolved, api_key=api_key, provider=provider)
    return _client
