import os

class DocumentClassifier:
    @staticmethod
    def identify_document_type(file_path: str) -> str:
        """
        Classifies document type based on metadata / filename.
        Options: invoice, receipt, purchase_order, contract, certificate, unknown
        """
        filename = os.path.basename(file_path).lower()
        if "invoice" in filename or "inv-" in filename or "bill" in filename:
            return "invoice"
        elif "receipt" in filename or "rec-" in filename or "rcpt" in filename:
            return "receipt"
        elif "po-" in filename or "purchase order" in filename or "po_" in filename:
            return "purchase_order"
        elif "contract" in filename or "agreement" in filename or "lease" in filename:
            return "contract"
        elif "certificate" in filename or "cert-" in filename or "license" in filename:
            return "certificate"
        else:
            return "unknown"
