import os, json, base64, tempfile, re
from pathlib import Path

import fitz
import requests

INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "google/diffusiongemma-26b-a4b-it"


SAMPLE_DIR = r"C:\Users\adars\OneDrive\Desktop\AUDIT_AGENT\sample_docs"
CHECKLIST_PATH = r"C:\Users\adars\OneDrive\Desktop\AUDIT_AGENT\checklist.md"
SUPPORTED_EXTS = frozenset({".pdf", ".png", ".jpg", ".jpeg"})
MAX_PDF_PAGES = 10


def pdf_to_b64_images(pdf_path: str) -> list[str]:
    images = []
    doc = fitz.open(pdf_path)
    pages = min(len(doc), MAX_PDF_PAGES)
    for i in range(pages):
        pix = doc.load_page(i).get_pixmap(dpi=200)
        buf = pix.tobytes("jpeg")
        images.append(base64.b64encode(buf).decode("utf-8"))
    doc.close()
    return images


def load_checklist() -> list[dict]:
    text = Path(CHECKLIST_PATH).read_text(encoding="utf-8")
    rules = []
    for block in re.split(r"\n###\s+", text)[1:]:
        m = re.match(r"(R\d+):\s*(.+)", block.strip())
        if not m: continue
        rid = m.group(1)
        sev = re.search(r"\*\*Severity:\*\*\s*(\S+)", block)
        man = re.search(r"\*\*Mandatory:\*\*\s*(\S+)", block)
        desc = re.search(r"\*\*Description:\*\*\s*(.+)", block, re.DOTALL)
        rules.append({
            "rule_id": rid,
            "title": m.group(2).strip(),
            "severity": sev.group(1).lower() if sev else "medium",
            "mandatory": man.group(1).lower() == "true" if man else False,
            "description": desc.group(1).strip() if desc else "",
        })
    return rules


def _normalize_rule_id(rid: str) -> str:
    return f"R{int(''.join(c for c in rid if c.isdigit())):03d}"


def clean_audit(data: dict) -> dict:
    score = float(data.get("score", 0.0))
    if score > 100: score /= 10
    score = max(0.0, min(100.0, score))
    data["score"] = score
    failed = []
    for item in data.get("failed_rules", []):
        if not isinstance(item, dict): continue
        item["rule_id"] = _normalize_rule_id(str(item.get("rule_id", "")))
        failed.append(item)
    data["failed_rules"] = failed
    checklist = load_checklist()
    data["passed"] = not any(
        f["rule_id"] in {r["rule_id"] for r in checklist if r["mandatory"]}
        for f in failed
    )
    return data


def call_nvidia(messages: list) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 4096,
        "temperature": 0.1,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
    }
    resp = requests.post(INVOKE_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


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


def main():
    rules = load_checklist()
    files = sorted([
        os.path.join(SAMPLE_DIR, f) for f in os.listdir(SAMPLE_DIR)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS
    ])
    if not files:
        print("No documents found.")
        return

    results = []
    for doc_path in files:
        doc_name = os.path.basename(doc_path)
        print(f"\n{'='*60}")
        print(f"DOCUMENT: {doc_name}")

        b64_images = pdf_to_b64_images(doc_path)
        print(f"  Pages: {len(b64_images)}")

        # Build image content parts
        image_parts = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            for b64 in b64_images
        ]

        # --- SUMMARIZE ---
        print(f"  --- Summarizing...")
        content = [{"type": "text", "text": (
            "You are a document analysis assistant. Extract structured information from "
            "the provided document image(s).\n\n"
            'Return ONLY valid JSON with: "document_type", "summary", "language", '
            '"key_fields" (document_number, date, total_amount, currency, vendor_name, customer_name).'
        )}] + image_parts
        raw = call_nvidia([{"role": "user", "content": content}])
        summary_data = extract_json(raw)
        print(f"  Type: {summary_data.get('document_type', '?')}")

        # --- AUDIT ---
        print(f"  --- Auditing...")
        rules_lines = "\n".join(
            f"- [{r['rule_id']}] {r['title']} ({r['severity']}, "
            f"{'mandatory' if r['mandatory'] else 'optional'}): {r['description']}"
            for r in rules
        )
        content = [{"type": "text", "text": (
            "You are an audit compliance agent. Audit this document against the checklist.\n\n"
            f"Document: {doc_name}\n"
            f"Type: {summary_data.get('document_type', 'unknown')}\n"
            f"Summary: {summary_data.get('summary', '')}\n\n"
            f"Checklist:\n{rules_lines}\n\n"
            'Return ONLY JSON: {"passed": bool, "score": 0-100, "failed_rules": [{"rule_id": "...", "evidence": "...", "page_number": null}], "remarks": "..."}'
        )}] + image_parts
        raw = call_nvidia([{"role": "user", "content": content}])
        audit_data = clean_audit(extract_json(raw))

        summary_data.setdefault("document_type", "unknown")
        summary_data.setdefault("summary", "")
        summary_data.setdefault("language", "unknown")
        summary_data.setdefault("key_fields", {})
        results.append({
            "document": doc_name,
            "summary": summary_data,
            "audit": audit_data,
        })

        status = "PASS" if audit_data["passed"] else "FAIL"
        print(f"  Result: {status} (score: {audit_data['score']:.1f}%)")
        for f in audit_data.get("failed_rules", []):
            print(f"    - {f['rule_id']}: {f.get('evidence', '')[:150]}")

    # Write report
    passed = sum(1 for r in results if r["audit"]["passed"])
    avg_score = sum(r["audit"]["score"] for r in results) / len(results) if results else 0
    report_path = Path(__file__).parent / "audit_report_nvidia.md"
    lines = [
        "# Audit Report — NVIDIA DiffusionGemma 26B",
        "",
        f"- **Model:** `{MODEL}`",
        f"- **Checklist:** `{CHECKLIST_PATH}` ({len(rules)} rules)",
        f"- **Documents:** {len(results)} processed, {passed} passed",
        f"- **Average Score:** {avg_score:.1f}%",
        "",
    ]
    for res in results:
        d, s, a = res["document"], res["summary"], res["audit"]
        status = "PASS" if a["passed"] else "FAIL"
        lines += [
            f"---", "",
            f"## {d}", "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| Type | {s.get('document_type', '?')} |",
            f"| Language | {s.get('language', '?')} |",
            f"| Summary | {s.get('summary', '')} |",
        ]
        kf = s.get("key_fields", {})
        if kf:
            for k, v in kf.items():
                if v is not None: lines.append(f"| {k} | {v} |")
        lines += [
            f"| **Result** | **{status}** |",
            f"| **Score** | **{a['score']:.1f}%** |", "",
        ]
        failed = a.get("failed_rules", [])
        if failed:
            lines += [f"### Failed Rules ({len(failed)})", "", f"| Rule | Evidence |", f"|------|----------|"]
            for f in failed:
                lines.append(f"| {f['rule_id']} | {f.get('evidence', '')} |")
        else:
            lines.append("**All rules complied.**")
        lines.append("")
        if a.get("remarks"):
            lines.append(f"**Remarks:** {a['remarks']}\n")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to: {report_path}")


if __name__ == "__main__":
    main()
