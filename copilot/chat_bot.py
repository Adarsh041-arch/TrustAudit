import logging
from typing import List, Dict, Any, Optional
from app.vlm import get_vlm_client
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

class CopilotChatbot:
    @staticmethod
    def answer_query(
        query: str, 
        audit_results: List[Dict[str, Any]], 
        cross_verification: Optional[Dict[str, Any]] = None,
        chat_history: List[Dict[str, str]] = None
    ) -> str:
        """
        Uses Gemini to answer questions about the current audit workspace, 
        fully grounded in findings, policies, and cross-document reconciliation.
        """
        if chat_history is None:
            chat_history = []

        # 1. Format findings context
        findings_context = ""
        for doc in audit_results:
            findings_context += f"Document: {doc['document_name']} (Type: {doc.get('document_type', 'unknown')})\n"
            findings_context += f"Compliance Score: {doc.get('score', 0.0)}% | Risk Level: {doc.get('risk_level', 'unknown')}\n"
            findings_context += f"Summary: {doc.get('summary_text', '')}\n"
            
            failed = doc.get("failed_rules", [])
            if failed:
                findings_context += f"Failed Rules & Violations ({len(failed)}):\n"
                for r in failed:
                    findings_context += f"  - Rule: {r.get('rule_id')} ({r.get('rule_title')})\n"
                    findings_context += f"    Finding: {r.get('finding')}\n"
                    findings_context += f"    Evidence: {r.get('evidence')}\n"
                    findings_context += f"    Impact: {r.get('impact')}\n"
                    findings_context += f"    Recommendation: {r.get('recommendation')}\n"
            else:
                findings_context += "No rule violations detected.\n"
            findings_context += "\n"

        # 2. Format cross verification context
        cross_context = "No cross-document validation performed.\n"
        if cross_verification:
            cross_context = f"Status: {cross_verification.get('status', 'unknown')}\n"
            cross_context += f"Summary: {cross_verification.get('reconciliation_summary', '')}\n"
            discs = cross_verification.get("discrepancies", [])
            if discs:
                cross_context += "Discrepancy Details:\n"
                for d in discs:
                    cross_context += f"  - Check: {d.get('check_type')} | Status: {d.get('status')} | Severity: {d.get('severity')}\n"
                    cross_context += f"    Details: {d.get('details')}\n"

        # 3. Compile history context
        history_str = ""
        for msg in chat_history[-6:]:  # Last 6 turns
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            history_str += f"{role}: {content}\n"

        # 4. VLM System prompt
        prompt = (
            "You are 'TrustAudit Auditor Copilot', a conversational expert in audit compliance, financial reconciliation, and document risk analytics.\n"
            "An auditor is asking you a question about the document audit results they just ran.\n\n"
            "Here is the GROUND TRUTH audit data and cross-verification results:\n\n"
            "--- AUDIT RESULT DETAILS ---\n"
            f"{findings_context}\n"
            "--- THREE-WAY MATCHING RECONCILIATION ---\n"
            f"{cross_context}\n"
            "----------------------------------------\n\n"
            "CHAT CONVERSATION HISTORY:\n"
            f"{history_str}\n"
            f"USER QUERY: {query}\n\n"
            "Instructions:\n"
            "- Ground all your answers strictly in the audit data and verification context provided above.\n"
            "- If the user asks 'Why did it fail?' or 'Which policies were violated?', refer directly to the failed rules, evidence, and RAG policy references in the dataset.\n"
            "- Offer concrete professional recommendations on how to mitigate risks and proceed.\n"
            "- Keep your tone professional, authoritative, helpful, and concise.\n"
            "- Do not guess or hallucinate any numbers or values not shown in the ground truth."
        )

        vlm = get_vlm_client()
        content = [{"type": "text", "text": prompt}]
        
        try:
            response = vlm._invoke(content)
            # Remove markdown code styling if Gemini outputs them
            if response.startswith("```"):
                response = response.strip("`").strip()
                if response.startswith("markdown"):
                    response = response[8:].strip()
            return response
        except Exception as e:
            logger.error(f"Error invoking VLM Copilot: {e}")
            return f"Error communicating with AI Copilot: {str(e)}"
