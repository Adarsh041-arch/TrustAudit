from typing import List, Dict, Any, Tuple

SEVERITY_WEIGHTS = {
    "critical": 40.0,
    "high": 25.0,
    "medium": 10.0,
    "low": 5.0
}

class RiskScorer:
    @staticmethod
    def calculate_compliance_score(failed_rules: List[Dict[str, Any]], total_rules_count: int) -> Tuple[float, str, str]:
        """
        Calculates compliance score, risk level, and generates a risk explanation.
        failed_rules: list of dicts with key 'severity'
        total_rules_count: total rules applied in checklist
        """
        if total_rules_count <= 0:
            return 100.0, "Low Risk", "No active rules checked. Compliance stands at 100%."

        # Compute total maximum possible deduct points or weighted deduction
        total_deduction = 0.0
        has_critical_failure = False
        has_high_failure = False
        
        failed_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        
        for rule in failed_rules:
            sev = rule.get("severity", "medium").lower()
            weight = SEVERITY_WEIGHTS.get(sev, 10.0)
            total_deduction += weight
            
            if sev == "critical":
                has_critical_failure = True
            elif sev == "high":
                has_high_failure = True
                
            if sev in failed_counts:
                failed_counts[sev] += 1
            else:
                failed_counts["medium"] += 1

        # Score is bounded between 0 and 100
        compliance_score = max(0.0, 100.0 - total_deduction)
        
        # Risk classification
        if compliance_score < 70.0 or has_critical_failure:
            risk_level = "High Risk"
        elif compliance_score < 85.0 or has_high_failure:
            risk_level = "Medium Risk"
        else:
            risk_level = "Low Risk"

        # Generate a detailed risk explanation
        explanation_parts = []
        if len(failed_rules) == 0:
            explanation_parts.append(
                f"The document complies with all {total_rules_count} audited policy regulations. "
                "No compliance violations were observed. The document is classified as Low Risk."
            )
        else:
            explanation_parts.append(
                f"The document has a compliance rating of {compliance_score:.1f}% due to {len(failed_rules)} "
                f"observed compliance violations. "
            )
            
            failures_list = []
            for sev, count in failed_counts.items():
                if count > 0:
                    failures_list.append(f"{count} {sev}")
            explanation_parts.append("Violations detected: " + ", ".join(failures_list) + ". ")
            
            if has_critical_failure:
                explanation_parts.append(
                    "CRITICAL WARNING: The audit revealed critical compliance infractions. "
                    "This automatically escalates the file to High Risk, requiring immediate operational escalation."
                )
            elif has_high_failure:
                explanation_parts.append(
                    "High severity violations are present, affecting essential fields or signature validations. "
                    "Escalation to Medium Risk category requires review of policy compliance."
                )
            else:
                explanation_parts.append(
                    "Observed issues are of minor or medium severity. Remediation is advised "
                    "but does not block standard processing."
                )
                
        explanation = " ".join(explanation_parts)
        return round(compliance_score, 2), risk_level, explanation
