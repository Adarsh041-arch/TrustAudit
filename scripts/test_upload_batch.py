"""Test uploading the 5 generated sample documents to the Audit V2 API."""

import json
from pathlib import Path
import requests

DOCS_DIR = Path(__file__).resolve().parent.parent / "sample_docs" / "test_rules_batch"
URL = "http://127.0.0.1:8100/api/v2/audit/upload"

files = []
for p in sorted(DOCS_DIR.glob("*.pdf")):
    files.append(("files", (p.name, p.read_bytes(), "application/pdf")))

print(f"Uploading {len(files)} files to {URL}...")
res = requests.post(URL, files=files, timeout=120)

if res.status_code != 200:
    print("Failed:", res.status_code, res.text[:500])
else:
    data = res.json()
    print("\n================== AUDIT BATCH RESULTS ==================")
    print(f"Total: {len(data.get('document_results', []))} | Passed: {data.get('documents_passed')} | Needs Review: {data.get('documents_review_required')}")
    print(f"Executive Summary: {data.get('executive_summary')}\n")

    for doc in data.get("document_results", []):
        name = doc.get("document_name")
        doc_type = doc.get("document_type")
        decision = doc.get("decision", {})
        status = decision.get("status")
        passed = doc.get("passed")
        blockers = decision.get("blockers", [])
        failed_rules = doc.get("failed_rules", [])

        print(f"[{status}] {name} (Type: {doc_type})")
        print(f"    Clearance Passed: {passed}")
        if failed_rules:
            print("    Failed Rules:")
            for fr in failed_rules:
                print(f"      - [{fr.get('rule_id')}]: {fr.get('finding')}")
        if blockers:
            print(f"    Blockers:")
            for b in blockers:
                print(f"      - {b}")
        print()
