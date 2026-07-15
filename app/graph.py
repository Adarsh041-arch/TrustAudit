import os
import re
from typing import Literal

from langgraph.graph import StateGraph, START, END

from app.state import AuditState
from app.schemas import DocumentSummary, AuditChecklist, AuditRule, DocumentAuditResult, FinalAuditReport
from app.vlm import get_vlm_client
from app.logger import logger

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"})
CHECKLIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "checklist.md")


def parse_checklist_md(file_path: str) -> AuditChecklist:
    with open(file_path, encoding="utf-8") as f:
        text = f.read()

    name_match = re.search(r"\*\*Audit Name:\*\*\s*(.+)", text)
    ver_match = re.search(r"\*\*Version:\*\*\s*(.+)", text)
    audit_name = name_match.group(1).strip() if name_match else "Untitled Checklist"
    version = ver_match.group(1).strip() if ver_match else "1.0"

    rules: list[AuditRule] = []
    rule_blocks = re.split(r"\n###\s+", text)[1:]

    for block in rule_blocks:
        rid_match = re.match(r"(R\d+):\s*(.+)", block.strip())
        if not rid_match:
            continue
        rule_id = rid_match.group(1)
        title = rid_match.group(2).strip()
        sev_match = re.search(r"\*\*Severity:\*\*\s*(\S+)", block)
        man_match = re.search(r"\*\*Mandatory:\*\*\s*(\S+)", block)
        desc_match = re.search(r"\*\*Description:\*\*\s*(.+)", block, re.DOTALL)
        severity = sev_match.group(1).lower() if sev_match else "medium"
        mandatory = man_match.group(1).lower() == "true" if man_match else False
        description = desc_match.group(1).strip() if desc_match else ""

        rules.append(AuditRule(
            rule_id=rule_id, title=title, description=description,
            severity=severity, mandatory=mandatory,
        ))

    return AuditChecklist(audit_name=audit_name, version=version, rules=rules)


def discover_documents(folder_path: str) -> list[str]:
    if not os.path.isdir(folder_path):
        return []
    paths: list[str] = []
    for entry in os.scandir(folder_path):
        if entry.is_file():
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                paths.append(entry.path)
    return sorted(paths)


def upload_folder_node(state: AuditState) -> dict:
    logger.info("-- STEP 1/5: Upload Folder --------------------------------")
    logger.info("Scanning: %s", state.uploaded_folder)
    documents = discover_documents(state.uploaded_folder)
    logger.info("Discovered %d supported document(s)", len(documents))
    for d in documents:
        logger.info("  - %s", os.path.basename(d))
    return {"documents": documents}


def summarize_documents_node(state: AuditState) -> dict:
    logger.info("-- STEP 2/5: Summarize Documents --------------------------")
    vlm = get_vlm_client()
    total = len(state.documents)
    summaries: list[DocumentSummary] = []
    for i, doc_path in enumerate(state.documents, 1):
        doc_name = os.path.basename(doc_path)
        logger.info("[%d/%d] Summarizing: %s", i, total, doc_name)
        summary = vlm.summarize(doc_path)
        logger.info("  OK Type: %s | Pages: %s | Lang: %s",
                     summary.document_type, summary.page_count or "?", summary.language or "?")
        summaries.append(summary)
    logger.info("Summaries complete: %d document(s)", len(summaries))
    return {"document_summaries": summaries}


def load_checklist_node(state: AuditState) -> dict:
    logger.info("-- STEP 3/5: Load Audit Checklist -------------------------")
    if os.path.isfile(CHECKLIST_PATH):
        logger.info("Reading: %s", CHECKLIST_PATH)
        checklist = parse_checklist_md(CHECKLIST_PATH)
        logger.info("Loaded \"%s\" v%s - %d rule(s)", checklist.audit_name, checklist.version, len(checklist.rules))
        for r in checklist.rules:
            logger.info("  %s [%s] %s", r.rule_id, r.severity.upper(), r.title)
    else:
        logger.warning("Checklist file not found at %s - using empty checklist", CHECKLIST_PATH)
        checklist = AuditChecklist(audit_name="Default", version="1.0", rules=[])
    return {"audit_checklist": checklist}


def audit_agent_node(state: AuditState) -> dict:
    idx = state.processing_index
    total = len(state.documents)
    if idx >= total:
        return {}

    doc_path = state.documents[idx]
    doc_name = os.path.basename(doc_path)
    doc_summary = state.document_summaries[idx] if idx < len(state.document_summaries) else DocumentSummary(document_name=doc_name)
    checklist = state.audit_checklist or AuditChecklist(audit_name="empty")

    logger.info("-- STEP 4/5: Audit Agent [%d/%d] --------------------------", idx + 1, total)
    logger.info("Document: %s", doc_name)
    logger.info("Checklist: %d rule(s) to evaluate", len(checklist.rules))

    vlm = get_vlm_client()
    result = vlm.audit(doc_path, doc_summary, checklist)

    status = "PASS" if result.passed else "FAIL"
    logger.info("  Result: %s (score: %.1f%%)", status, result.score)
    if result.failed_rules:
        logger.info("  Failed rule(s): %d", len(result.failed_rules))
        for fr in result.failed_rules:
            logger.info("    - %s: %s", fr.rule_id, fr.evidence[:120] if fr.evidence else "no evidence")
    if result.remarks:
        logger.info("  Remarks: %s", result.remarks)

    updated_results = list(state.audit_results)
    updated_results.append(result)

    return {
        "audit_results": updated_results,
        "processing_index": idx + 1,
    }


def report_aggregator_node(state: AuditState) -> dict:
    logger.info("-- STEP 5/5: Aggregate Results ----------------------------")

    total = len(state.audit_results)
    passed = sum(1 for r in state.audit_results if r.passed)
    failed = total - passed

    if total > 0:
        overall_score = sum(r.score for r in state.audit_results) / total
    else:
        overall_score = 100.0

    if overall_score >= 80.0:
        overall_result = "PASS"
    elif overall_score >= 50.0:
        overall_result = "REVIEW REQUIRED"
    else:
        overall_result = "FAIL"

    logger.info("Documents: %d total, %d passed, %d failed", total, passed, failed)
    logger.info("Overall score: %.1f%%", overall_score)
    logger.info("Overall result: %s", overall_result)

    if state.audit_results:
        logger.info("Per-document breakdown:")
        for dr in state.audit_results:
            s = "PASS" if dr.passed else "FAIL"
            logger.info("  %s -> %s (%.1f%%)", dr.document_name, s, dr.score)

    report = FinalAuditReport(
        audit_title=state.audit_title or "Untitled Audit",
        documents_processed=total,
        documents_passed=passed,
        documents_failed=failed,
        overall_score=round(overall_score, 2),
        overall_result=overall_result,
        summary=_generate_summary(passed, failed, total, overall_result),
        document_results=list(state.audit_results),
    )

    logger.info("Final report generated")
    return {"final_report": report}


def _generate_summary(passed: int, failed: int, total: int, result: str) -> str:
    return (
        f"Audit complete. {total} document(s) processed: "
        f"{passed} passed, {failed} failed. "
        f"Overall result: {result}."
    )


def _route_from_checklist(state: AuditState) -> Literal["audit_agent", "aggregate_results"]:
    if len(state.documents) == 0:
        return "aggregate_results"
    return "audit_agent"


def _route_after_audit(state: AuditState) -> Literal["audit_agent", "aggregate_results"]:
    if state.processing_index < len(state.documents):
        return "audit_agent"
    return "aggregate_results"


def build_graph() -> StateGraph:
    graph = StateGraph(AuditState)

    graph.add_node("upload_folder", upload_folder_node)
    graph.add_node("summarize_documents", summarize_documents_node)
    graph.add_node("load_checklist", load_checklist_node)
    graph.add_node("audit_agent", audit_agent_node)
    graph.add_node("aggregate_results", report_aggregator_node)

    graph.add_edge(START, "upload_folder")
    graph.add_edge("upload_folder", "summarize_documents")
    graph.add_edge("summarize_documents", "load_checklist")

    graph.add_conditional_edges(
        "load_checklist",
        _route_from_checklist,
        {
            "audit_agent": "audit_agent",
            "aggregate_results": "aggregate_results",
        },
    )

    graph.add_conditional_edges(
        "audit_agent",
        _route_after_audit,
        {
            "audit_agent": "audit_agent",
            "aggregate_results": "aggregate_results",
        },
    )

    graph.add_edge("aggregate_results", END)

    return graph.compile()


__all__ = ["build_graph"]
