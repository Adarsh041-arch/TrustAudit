import os
import logging
import datetime
from typing import List, Dict, Any, Optional

from app.vlm import get_vlm_client, VLMContentBuilder
from app.schemas import DocumentSummary
from policy_store.manager import parse_policy_markdown
from rag_engine.retriever import PolicyRetriever
from risk_engine.risk_scorer import RiskScorer
from ml_models.risk_classifier import DocumentRiskClassifier
from document_classifier.classifier import DocumentClassifier

logger = logging.getLogger(__name__)

class ComplianceAuditEngine:
    def __init__(self, db_path: str = "./chroma_db"):
        self.retriever = PolicyRetriever(db_path=db_path)
        self.ml_classifier = DocumentRiskClassifier()
        
    def initialize_policies(self, checklist_path: str):
        """Pre-loads checklist rules into RAG database."""
        self.retriever.index_policies(checklist_path)

    def audit_document(self, file_path: str, checklist_path: str) -> Dict[str, Any]:
        """
        Runs a complete explainable audit on a single document:
        1. Classifies doc type.
        2. Retrieves relevant policies from vector DB (RAG).
        3. Invokes Gemini (VLM) with document + retrieved context.
        4. Calculates compliance score & risk levels.
        5. Runs ML classifier for prediction.
        6. Determines if human review is needed.
        """
        doc_name = os.path.basename(file_path)
        logger.info(f"Starting compliance audit for: {doc_name}")
        
        # 1. Document Classify
        from document_classifier.classifier import DocumentClassifier
        inferred_type = DocumentClassifier.identify_document_type(file_path)
        
        # 2. Extract Document Summary using VLM client (reusing legacy)
        vlm = get_vlm_client()
        summary: DocumentSummary = vlm.summarize(file_path)
        
        # 3. Retrieve policies from RAG
        retrieved_policies = self.retriever.retrieve_relevant_policies(
            query=f"Rules for document type {inferred_type or summary.document_type} with details {summary.summary}",
            top_k=4
        )
        
        # Format the retrieved policies into a prompt snippet
        rag_context = ""
        for i, p in enumerate(retrieved_policies, 1):
            rag_context += f"Policy [{p['rule_id']}]: {p['title']}\n"
            rag_context += f"Description: {p['description']}\n"
            rag_context += f"Typical Impact: {p['impact']}\n"
            rag_context += f"Action Recommended: {p['recommendation']}\n\n"
            
        # Parse full checklist
        checklist = parse_policy_markdown(checklist_path)
        rules_lines = "\n".join(
            f"- [{r.rule_id}] {r.title} ({r.severity}, {'mandatory' if r.mandatory else 'optional'}): {r.description}"
            for r in checklist.rules
        )
        
        # 4. Invoke VLM with RAG Context & Instructions
        content = VLMContentBuilder.build(file_path)
        today = datetime.date.today().isoformat()
        
        import re
        sanitized_doc_name = doc_name
        sanitized_doc_name = re.sub(r'\d{4}-\d{2}-\d{2}\s+at\s+\d{2}\.\d{2}\.\d{2}', '', sanitized_doc_name)
        sanitized_doc_name = re.sub(r'WhatsApp\s+Image\s*', '', sanitized_doc_name, flags=re.IGNORECASE)
        sanitized_doc_name = sanitized_doc_name.strip()
        if not sanitized_doc_name or sanitized_doc_name.startswith('.'):
            sanitized_doc_name = "document" + sanitized_doc_name

        prompt = (
            "You are an expert compliance officer and auditor. Audit the document image(s) below.\n\n"
            f"Document Filename: {sanitized_doc_name}\n"
            f"Document Type: {inferred_type or summary.document_type}\n"
            f"Document Summary: {summary.summary}\n"
            f"Audit Date: {today}\n\n"
            f"Standard Checklist Rules:\n{rules_lines}\n\n"
            f"RAG Compliance Knowledge Base Policy Context:\n{rag_context}\n"
            "INSTRUCTIONS:\n"
            "1. Evaluate the document against the Standard Checklist rules.\n"
            "2. SEVERITY GUIDELINES:\n"
            "   - Core Financial Integrity (R003: Math Accuracy, R005: Future/Invalid Dates, R006: Currency/Amount Consistency) are HIGH / CRITICAL severity.\n"
            "   - Document-Dependent Fields (R001: Legibility, R002: Fields, R004: Signatures/Stamps, R007: Vendor Address/IDs, R010: Tax Breakdown) are MEDIUM or LOW severity because requirements vary by document format (e.g. computer invoices or point-of-sale receipts often omit physical stamps or secondary addresses).\n"
            "3. Recalculate line totals (qty x price), subtotal, tax splits, and grand totals under R003. Flag any math errors.\n"
            "4. DATE VALIDITY & FUTURE DATES (Rule R005) - Compare the document date to the Audit Date. A document is ONLY future-dated if its date is strictly after the Audit Date (document_date > Audit Date). If document_date <= Audit Date, the document is NOT in the future, even if the year is 2026. For example: July 2026 is BEFORE August 2026, so a document dated 20 July 2026 is in the PAST relative to the Audit Date 2026-08-23, and it complies with R005.\n"
            "5. For every rule that fails, create a highly descriptive explainable violation block. Do NOT report rules that are complied with.\n"
            "6. For each violation, produce:\n"
            "   - 'rule_id': e.g. 'R003'\n"
            "   - 'finding': A short summary of the violation\n"
            "   - 'evidence': Specific text, numerical values, or missing field in the document\n"
            "   - 'impact': Financial or regulatory penalty or operational process block\n"
            "   - 'recommendation': Specific mitigation steps to fix this issue\n"
            "   - 'severity': 'critical', 'high', 'medium', or 'low'\n"
            "   - 'page_number': the page number (int) where the error was seen (or null)\n\n"
            "Return ONLY a valid JSON object with the following fields:\n"

            "{\n"
            '  "passed_all_mandatory": boolean, // true if all mandatory rules complied with\n'
            '  "failed_rules": [\n'
            "    {\n"
            '      "rule_id": "R003",\n'
            '      "finding": "Subtotal math mismatch",\n'
            '      "evidence": "Widget A: Qty=2, Price=$50. Stated total $120. Expected $100.",\n'
            '      "impact": "Inaccurate financial reports and potential overbilling tax liabilities.",\n'
            '      "recommendation": "Request a corrected credit note or invoice adjustments.",\n'
            '      "severity": "critical",\n'
            '      "page_number": 1\n'
            "    }\n"
            "  ],\n"
            '  "confidence_score": float, // your confidence in the audit parsing accuracy (0-100)\n'
            '  "remarks": "Overall summary of the compliance posture"\n'
            "}\n"
            "DO NOT include markdown block markers (like ```json) in your return. Just raw JSON text."
        )
        
        content.insert(0, {"type": "text", "text": prompt})
        
        # Invoke VLM Model
        raw_response = vlm._invoke(content)
        parsed_data = vlm._parse_json(
            raw_response, 
            {"passed_all_mandatory": False, "failed_rules": [], "confidence_score": 80.0, "remarks": "Fallback parsing due to model error"}
        )
        
        # Process and clean up findings with RAG definitions if VLM missed details
        failed_violations = []
        for item in parsed_data.get("failed_rules", []):
            rid = item.get("rule_id", "unknown")
            # Lookup default checklist rule
            matching_rule = next((r for r in checklist.rules if r.rule_id == rid), None)
            rule_title = matching_rule.title if matching_rule else rid
            
            # Enrich using RAG metadata if missing
            retrieved_match = next((p for p in retrieved_policies if p["rule_id"] == rid), None)
            
            impact = item.get("impact") or (retrieved_match["impact"] if retrieved_match else "")
            recommendation = item.get("recommendation") or (retrieved_match["recommendation"] if retrieved_match else "")
            severity = item.get("severity") or (matching_rule.severity if matching_rule else "medium")
            
            failed_violations.append({
                "rule_id": rid,
                "rule_title": rule_title,
                "finding": item.get("finding", "Compliance violation"),
                "evidence": item.get("evidence", "Evidence not stated"),
                "impact": impact,
                "recommendation": recommendation,
                "severity": severity,
                "page_number": item.get("page_number")
            })
            
        # 5. Risk Scoring Engine
        score, risk_level, risk_explanation = RiskScorer.calculate_compliance_score(
            failed_rules=failed_violations,
            total_rules_count=len(checklist.rules)
        )
        
        # 6. ML Risk Classification
        ml_res = self.ml_classifier.predict_risk(
            doc_type=inferred_type or summary.document_type,
            page_count=vlm._count_pages(file_path),
            score=score,
            failed_rules=failed_violations
        )
        
        # 7. Confidence Score & Human Review Recommendation
        vlm_conf = float(parsed_data.get("confidence_score", 85.0))
        ml_conf = max(ml_res["probabilities"].values()) if "probabilities" in ml_res else 85.0
        # Aggregated confidence
        final_confidence = round(0.7 * vlm_conf + 0.3 * ml_conf, 2)
        
        human_review_required = final_confidence < 75.0 or risk_level == "High Risk"
        
        # Populate result
        result = {
            "document_name": doc_name,
            "document_type": inferred_type or summary.document_type,
            "passed": parsed_data.get("passed_all_mandatory", False) and (risk_level != "High Risk"),
            "score": score,
            "risk_level": risk_level,
            "risk_explanation": risk_explanation,
            "failed_rules": failed_violations,
            "ml_prediction": ml_res,
            "confidence_score": final_confidence,
            "human_review_recommended": human_review_required,
            "remarks": parsed_data.get("remarks", ""),
            "page_count": vlm._count_pages(file_path),
            "summary_text": summary.summary,
            "metadata": summary.metadata
        }
        
        return result
