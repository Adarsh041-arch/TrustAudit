import os
import json
import tempfile
from pathlib import Path

import fitz
import litert_lm

litert_lm.set_min_log_severity(litert_lm.LogSeverity.ERROR)

MODEL_PATH = r"C:\Users\adars\.cache\huggingface\hub\models--litert-community--gemma-4-E2B-it-litert-lm\snapshots\361a4010ad6d88fc5c86e148e333c0342b99763d\gemma-4-E2B-it.litertlm"
SAMPLE_DIR = r"C:\Users\adars\OneDrive\Desktop\AUDIT_AGENT\sample_docs"
CHECKLIST_PATH = r"C:\Users\adars\OneDrive\Desktop\AUDIT_AGENT\checklist.md"
SUPPORTED_EXTS = frozenset({".pdf", ".png", ".jpg", ".jpeg"})
MAX_PDF_PAGES = 10


def pdf_to_images(pdf_path: str) -> list[str]:
    paths = []
    doc = fitz.open(pdf_path)
    total = len(doc)
    pages = min(total, MAX_PDF_PAGES)
    tmpdir = tempfile.mkdtemp(prefix="litert_pages_")
    for i in range(pages):
        pix = doc.load_page(i).get_pixmap(dpi=200)
        img = f"page_{i+1}.jpg"
        out = os.path.join(tmpdir, img)
        pix.save(out)
        paths.append(out)
    doc.close()
    return paths


def cleanup_images(paths: list[str]):
    seen = set()
    for p in paths:
        d = os.path.dirname(p)
        if d not in seen:
            seen.add(d)
            try:
                import shutil
                shutil.rmtree(d)
            except Exception:
                pass


def load_checklist() -> list[dict]:
    import re
    text = Path(CHECKLIST_PATH).read_text(encoding="utf-8")
    rules = []
    for block in re.split(r"\n###\s+", text)[1:]:
        m = re.match(r"(R\d+):\s*(.+)", block.strip())
        if not m:
            continue
        rid = m.group(1)
        title = m.group(2).strip()
        sev = re.search(r"\*\*Severity:\*\*\s*(\S+)", block)
        man = re.search(r"\*\*Mandatory:\*\*\s*(\S+)", block)
        desc = re.search(r"\*\*Description:\*\*\s*(.+)", block, re.DOTALL)
        rules.append({
            "rule_id": rid,
            "title": title,
            "severity": sev.group(1).lower() if sev else "medium",
            "mandatory": man.group(1).lower() == "true" if man else False,
            "description": desc.group(1).strip() if desc else "",
        })
    return rules


_CHECKLIST_CACHE: list[dict] | None = None


def _get_checklist():
    global _CHECKLIST_CACHE
    if _CHECKLIST_CACHE is None:
        _CHECKLIST_CACHE = load_checklist()
    return _CHECKLIST_CACHE


def ask(conversation, text: str, image_paths: list[str]) -> str:
    items = [text]
    for img in image_paths:
        items.append(litert_lm.Content.ImageFile(absolute_path=img))
    content = litert_lm.Contents.of(*items)
    full = []
    stream = conversation.send_message_async(content)
    for chunk in stream:
        for item in chunk.get("content", []):
            if item.get("type") == "text":
                full.append(item["text"])
    return "".join(full)


_KNOWN_RULES = {"R001","R002","R003","R004","R005","R006","R007","R008","R009","R010","R011","R012"}

def _normalize_rule_id(rid: str) -> str:
    return f"R{int(''.join(c for c in rid if c.isdigit())):03d}"


def extract_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {}


def clean_audit(data: dict) -> dict:
    score_raw = data.get("score", 0.0)
    score_raw = float(score_raw)
    if score_raw > 100:
        score_raw = score_raw / 10
    score = max(0.0, min(100.0, score_raw))
    data["score"] = score
    failed = []
    for item in data.get("failed_rules", []):
        if not isinstance(item, dict):
            continue
        rid = _normalize_rule_id(str(item.get("rule_id", "")))
        item["rule_id"] = rid
        failed.append(item)
    data["failed_rules"] = failed
    checklist = _get_checklist()
    passed_fail = sum(1 for f in failed if any(
        r["rule_id"] == f.get("rule_id") and r["mandatory"]
        for r in checklist
    ))
    data["passed"] = passed_fail == 0
    return data


def main():
    rules = _get_checklist()
    REPORT_PATH = Path(__file__).parent / "audit_report_litert.md"
    files = sorted([
        os.path.join(SAMPLE_DIR, f) for f in os.listdir(SAMPLE_DIR)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS
    ])
    if not files:
        print("No documents found.")
        return

    print(f"Model: {MODEL_PATH}")
    print(f"Samples: {SAMPLE_DIR}")
    print(f"Checklist: {len(rules)} rules")
    print()

    results = []

    with litert_lm.Engine(
        model_path=MODEL_PATH,
        backend=litert_lm.Backend.GPU(),
        vision_backend=litert_lm.Backend.GPU(),
        audio_backend=litert_lm.Backend.CPU(),
        enable_speculative_decoding=False,
    ) as engine:
        for doc_path in files:
            doc_name = os.path.basename(doc_path)
            print(f"\n{'='*60}")
            print(f"DOCUMENT: {doc_name}")
            print(f"{'='*60}")

            images = pdf_to_images(doc_path)
            print(f"  Pages: {len(images)}")

            with engine.create_conversation() as conv:
                print(f"  --- Summarizing...")
                raw = ask(conv, (
                    "You are a document analysis assistant. Extract structured information from "
                    "the provided document image(s).\n\n"
                    'Return a JSON object with: "document_type", "summary", "language", '
                    '"key_fields" (document_number, date, total_amount, currency, vendor_name, customer_name).\n'
                    "Return ONLY valid JSON."
                ), images)
                summary_data = extract_json(raw)
                print(f"  Type: {summary_data.get('document_type', '?')}")

                print(f"  --- Auditing...")
                rules_lines = "\n".join(
                    f"- [{r['rule_id']}] {r['title']} ({r['severity']}, "
                    f"{'mandatory' if r['mandatory'] else 'optional'}): {r['description']}"
                    for r in rules
                )
                audit_prompt = (
                    "You are an audit compliance agent. Audit this document against the checklist.\n\n"
                    f"Document: {doc_name}\n"
                    f"Type: {summary_data.get('document_type', 'unknown')}\n"
                    f"Summary: {summary_data.get('summary', '')}\n\n"
                    f"Checklist:\n{rules_lines}\n\n"
                    'Return ONLY JSON: {"passed": bool, "score": 0-100, "failed_rules": [{"rule_id": "...", "evidence": "...", "page_number": null}], "remarks": "..."}'
                )
                raw = ask(conv, audit_prompt, images)
                audit_data = clean_audit(extract_json(raw))

            cleanup_images(images)

            summary_data.setdefault("document_type", "unknown")
            summary_data.setdefault("summary", "")
            summary_data.setdefault("language", "unknown")
            summary_data.setdefault("key_fields", {})
            results.append({
                "document": doc_name,
                "summary": summary_data,
                "audit": audit_data,
            })

            r = audit_data
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  Result: {status} (score: {r['score']:.1f}%)")
            for f in r.get("failed_rules", []):
                print(f"    - {f['rule_id']}: {f.get('evidence', '')[:120]}")

    # Write report
    passed = sum(1 for r in results if r["audit"]["passed"])
    avg_score = sum(r["audit"]["score"] for r in results) / len(results) if results else 0
    lines = [
        "# Audit Report — LiteRT Gemma 4 E2B",
        "",
        f"- **Model:** `gemma-4-E2B-it` (LiteRT)",
        f"- **Checklist:** `{CHECKLIST_PATH}` ({len(rules)} rules)",
        f"- **Documents:** {len(results)} processed, {passed} passed",
        f"- **Average Score:** {avg_score:.1f}%",
        "",
    ]
    for res in results:
        d = res["document"]
        s = res["summary"]
        a = res["audit"]
        status = "PASS" if a["passed"] else "FAIL"
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## {d}")
        lines.append(f"")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| Type | {s.get('document_type', '?')} |")
        lines.append(f"| Language | {s.get('language', '?')} |")
        lines.append(f"| Summary | {s.get('summary', '')} |")
        kf = s.get("key_fields", {})
        if kf:
            for k, v in kf.items():
                if v is not None:
                    lines.append(f"| {k} | {v} |")
        lines.append(f"| **Result** | **{status}** |")
        lines.append(f"| **Score** | **{a['score']:.1f}%** |")
        lines.append(f"")
        failed = a.get("failed_rules", [])
        if failed:
            lines.append(f"### Failed Rules ({len(failed)})")
            lines.append(f"")
            lines.append(f"| Rule | Evidence |")
            lines.append(f"|------|----------|")
            for f in failed:
                lines.append(f"| {f['rule_id']} | {f.get('evidence', '')} |")
        else:
            lines.append(f"**All rules complied.**")
        lines.append(f"")
        remarks = a.get("remarks", "")
        if remarks:
            lines.append(f"**Remarks:** {remarks}")
            lines.append(f"")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
