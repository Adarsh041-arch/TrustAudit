import time
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ComplianceEvaluator:
    @staticmethod
    def evaluate_performance(predictions: List[Dict[str, Any]], ground_truth: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Computes evaluation metrics based on predictions vs ground truth labels.
        predictions: list of dicts with keys: 'document_name', 'passed' (bool), 'score' (float), 'confidence' (float), 'latency' (float)
        ground_truth: list of dicts with keys: 'document_name', 'passed_actual' (bool)
        """
        total_eval = len(ground_truth)
        if total_eval == 0:
            return {"status": "No data for evaluation"}

        # Align predictions and ground truth by document_name
        aligned = []
        for gt in ground_truth:
            name = gt.get("document_name")
            pred = next((p for p in predictions if p.get("document_name") == name), None)
            if pred:
                aligned.append({
                    "name": name,
                    "pred_passed": pred.get("passed", False),
                    "actual_passed": gt.get("passed_actual", False),
                    "confidence": pred.get("confidence", 100.0),
                    "latency": pred.get("latency", 0.0)
                })

        tp = 0 # True Positives (Actual Passed, Pred Passed)
        tn = 0 # True Negatives (Actual Failed, Pred Failed)
        fp = 0 # False Positives (Actual Failed, Pred Passed)
        fn = 0 # False Negatives (Actual Passed, Pred Failed)
        
        latencies = []
        confidences = []
        
        for item in aligned:
            pred = item["pred_passed"]
            actual = item["actual_passed"]
            
            latencies.append(item["latency"])
            confidences.append(item["confidence"])
            
            if pred == True and actual == True:
                tp += 1
            elif pred == False and actual == False:
                tn += 1
            elif pred == True and actual == False:
                fp += 1
            elif pred == False and actual == True:
                fn += 1

        total_cases = tp + tn + fp + fn
        if total_cases == 0:
            return {"status": "No aligned test cases found."}

        # Calculate metrics
        accuracy = (tp + tn) / total_cases
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        # FPR & FNR
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
        
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1_score, 4),
            "false_positive_rate": round(fpr, 4),
            "false_negative_rate": round(fnr, 4),
            "average_latency_seconds": round(avg_latency, 2),
            "average_confidence_score": round(avg_confidence, 2),
            "matrix": {
                "true_positives": tp,
                "true_negatives": tn,
                "false_positives": fp,
                "false_negatives": fn
            }
        }

if __name__ == "__main__":
    # Standard CLI evaluation validation helper
    import sys
    print("------------------------------------------------------------------")
    print("TrustAudit Compliance Engine Validation Framework")
    print("------------------------------------------------------------------")
    
    # Mock ground truth and predicted output for verification
    mock_predictions = [
        {"document_name": "INV-1.pdf", "passed": True, "score": 95.0, "confidence": 88.5, "latency": 2.1},
        {"document_name": "PO-1.pdf", "passed": True, "score": 90.0, "confidence": 85.0, "latency": 1.9},
        {"document_name": "REC-1.jpg", "passed": False, "score": 45.0, "confidence": 92.0, "latency": 1.5},
        {"document_name": "INV-2.pdf", "passed": False, "score": 60.0, "confidence": 70.0, "latency": 2.4},
        {"document_name": "CONTRACT-1.pdf", "passed": True, "score": 100.0, "confidence": 95.0, "latency": 3.1}
    ]
    
    mock_ground_truth = [
        {"document_name": "INV-1.pdf", "passed_actual": True},
        {"document_name": "PO-1.pdf", "passed_actual": True},
        {"document_name": "REC-1.jpg", "passed_actual": False},
        {"document_name": "INV-2.pdf", "passed_actual": False},
        {"document_name": "CONTRACT-1.pdf", "passed_actual": True}
    ]
    
    results = ComplianceEvaluator.evaluate_performance(mock_predictions, mock_ground_truth)
    import json
    print(json.dumps(results, indent=4))
    print("------------------------------------------------------------------")
