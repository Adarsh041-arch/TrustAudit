import os
import re
from typing import List, Optional
from pydantic import BaseModel, Field

class PolicyRule(BaseModel):
    rule_id: str
    title: str
    description: str
    severity: str  # critical, high, medium, low
    mandatory: bool = True
    impact: str = ""
    recommendation: str = ""

class PolicyChecklist(BaseModel):
    audit_name: str
    version: str = "1.0"
    description: str = ""
    rules: List[PolicyRule] = Field(default_factory=list)

def parse_policy_markdown(file_path: str) -> PolicyChecklist:
    """
    Parses a checklist.md markdown file into a structured PolicyChecklist object.
    Includes fallback generation for impact and recommendation if not present.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Checklist not found at {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    name_match = re.search(r"\*\*Audit Name:\*\*\s*(.+)", text)
    ver_match = re.search(r"\*\*Version:\*\*\s*(.+)", text)
    desc_match = re.search(r"\*\*Description:\*\*\s*(.+)", text)

    audit_name = name_match.group(1).strip() if name_match else "Standard Document Audit"
    version = ver_match.group(1).strip() if ver_match else "1.0"
    description = desc_match.group(1).strip() if desc_match else ""

    rules: List[PolicyRule] = []
    # Split by ### R001: ... headings
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

        # Extract full content block to look for description
        desc_text = desc_match.group(1).strip() if desc_match else ""
        # Remove subsequent headers if any got caught in re.DOTALL
        desc_text = re.split(r"\n#", desc_text)[0].strip()

        # Build explainable templates based on rule characteristics
        impact = _get_default_impact(rule_id, title, severity)
        recommendation = _get_default_recommendation(rule_id, title)

        rules.append(PolicyRule(
            rule_id=rule_id,
            title=title,
            description=desc_text,
            severity=severity,
            mandatory=mandatory,
            impact=impact,
            recommendation=recommendation
        ))

    return PolicyChecklist(
        audit_name=audit_name,
        version=version,
        description=description,
        rules=rules
    )

def _get_default_impact(rule_id: str, title: str, severity: str) -> str:
    impacts = {
        "R001": "Unlegible documents impede physical audits, potentially hiding regulatory non-compliance, resulting in process blocks and legal audit rejection.",
        "R002": "Missing standard operational identifiers (Tax ID, PO number, Address) leads to audit failures, contract disputes, and non-compliance with commercial tax codes.",
        "R003": "Arithmetic discrepancies can indicate financial leakages, miscalculations of tax liabilities, or vendor overbilling, raising serious compliance penalties.",
        "R004": "Lack of valid signatures or authorization represents unauthorized procurement transactions, causing internal control failures and potential legal disputes.",
        "R005": "Expired/future dates create chronological anomalies, impacting validity of business expense claims and tax audit approvals.",
        "R006": "Inconsistent currencies lead to reconciliation errors and balance sheet inaccuracies, causing currency conversion compliance violations.",
        "R007": "Incomplete contact details of the supplier or client voids tax invoices and disqualifies input tax credits (ITC).",
        "R008": "Invalid document numbering patterns hinder traceabilty, which can lead to double invoicing and duplicate payments.",
        "R009": "Vague payment terms could lead to penalties, late fees, and cash flow forecasting mismatch.",
        "R010": "Non-compliant tax details risk corporate fines from revenue authorities, denial of tax rebates, and vendor blacklisting.",
        "R011": "Vague descriptions of items could lead to classification errors under customs tariffs or internal inventory logs.",
        "R012": "Absence of referenced schedules or contracts limits structural audits and audit evidence validity."
    }
    return impacts.get(rule_id, f"Failure to comply with rule {rule_id} ({title}) creates compliance risks of {severity} severity, affecting operational transparency and internal controls.")

def _get_default_recommendation(rule_id: str, title: str) -> str:
    recs = {
        "R001": "Request a high-resolution scan or original copy from the issuer, and ensure contrast and readability are preserved.",
        "R002": "Contact the vendor or business unit to issue an updated document containing all mandatory fields (dates, amounts, addresses).",
        "R003": "Perform calculations again, and contact the vendor to request a corrected credit note or adjusted invoice for the mismatch amount.",
        "R004": "Obtain authorized signatory approval, stamp, or digital signature certificate (DSC) validation before continuing.",
        "R005": "Update/amend the date, verify chronological timestamps, and confirm expiration certificates are renewed.",
        "R006": "Establish single-currency documentation, or secure a revision outlining specific exchange rates and tax split values.",
        "R007": "Acquire the supplier's registered street address and active contact identifiers before making payments.",
        "R008": "Enforce strict invoice registration rules to verify numbering format sequences and prevent duplications.",
        "R009": "Ensure Net payment periods, penalties, and discounts are clearly written on the final document page.",
        "R010": "Instruct the supplier to provide their official VATIN/GSTIN registry number and correct tax calculations.",
        "R011": "Require detailed itemized logs with standard classification codes (HSN/SAC) for products or services.",
        "R012": "Ensure all referenced appendices, schedules, and attachments are uploaded together with the parent document."
    }
    return recs.get(rule_id, f"Review documentation, cross-reference policy guidelines for '{title}', and amend missing information with the issuer.")
