import os
import random
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Try importing ML packages
try:
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    import joblib
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logger.warning("scikit-learn, pandas, numpy, or joblib not available. Running in fallback rule-based classification mode.")

MODEL_PATH = os.path.join(os.path.dirname(__file__), "saved_models", "rf_classifier.joblib")

class DocumentRiskClassifier:
    def __init__(self):
        self.model = None
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        self.load_model()

    def load_model(self):
        """Loads the pre-trained Random Forest model, or trains a new one if missing."""
        if ML_AVAILABLE:
            if os.path.exists(MODEL_PATH):
                try:
                    self.model = joblib.load(MODEL_PATH)
                    logger.info("Successfully loaded Random Forest risk classifier model.")
                except Exception as e:
                    logger.error(f"Error loading RF model: {e}. Training a new model.")
                    self.train_and_save()
            else:
                logger.info("Model not found. Training a new model.")
                self.train_and_save()

    def train_and_save(self):
        """Generates synthetic training dataset and trains the Random Forest classifier."""
        if not ML_AVAILABLE:
            logger.warning("ML libraries not installed. Skipping ML training.")
            return

        logger.info("Generating synthetic dataset (500+ records) for training Risk Classifier...")
        
        # Features: [doc_type_val, page_count, score, count_crit, count_high, count_med, count_low, math_fail_flag, sig_fail_flag]
        data = []
        labels = [] # 0: Compliant, 1: Partially Compliant, 2: Non-Compliant
        
        doc_types = [0, 1, 2, 3, 4] # invoice, receipt, po, contract, certificate
        
        # Generation loop (600 records)
        for _ in range(600):
            doc_type = random.choice(doc_types)
            pages = random.randint(1, 5)
            
            # Generate rule failure counts based on compliance posture
            roll = random.random()
            if roll < 0.45: # Compliant case
                crit = 0
                high = 0
                med = random.choice([0, 0, 0, 1])
                low = random.choice([0, 1, 2])
                math_fail = 0
                sig_fail = 0
                score = max(85.0, 100.0 - (med * 10.0 + low * 5.0))
                label = 0 # Compliant
            elif roll < 0.80: # Partially Compliant case
                crit = 0
                high = random.choice([0, 1])
                med = random.choice([1, 2])
                low = random.choice([1, 2, 3])
                math_fail = 0
                sig_fail = random.choice([0, 0, 1])
                score = max(50.0, 100.0 - (high * 25.0 + med * 10.0 + low * 5.0))
                label = 1 # Partially Compliant
            else: # Non-Compliant case
                crit = random.choice([1, 2])
                high = random.choice([1, 2, 3])
                med = random.randint(1, 4)
                low = random.randint(1, 4)
                math_fail = random.choice([0, 1])
                sig_fail = random.choice([0, 1])
                score = max(0.0, 100.0 - (crit * 40.0 + high * 25.0 + med * 10.0 + low * 5.0))
                label = 2 # Non-Compliant
                
            data.append([doc_type, pages, score, crit, high, med, low, math_fail, sig_fail])
            labels.append(label)

        # Train model
        X = np.array(data)
        y = np.array(labels)
        
        self.model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=6)
        self.model.fit(X, y)
        
        # Save model
        try:
            joblib.dump(self.model, MODEL_PATH)
            logger.info(f"Random Forest model saved successfully at: {MODEL_PATH}")
        except Exception as e:
            logger.error(f"Error saving model: {e}")

    def extract_features(self, doc_type: str, page_count: int, score: float, failed_rules: List[Dict[str, Any]]) -> List[float]:
        """Converts doc audit outcomes to numerical feature vector."""
        type_mapping = {
            "invoice": 0,
            "receipt": 1,
            "purchase_order": 2,
            "contract": 3,
            "certificate": 4
        }
        doc_type_val = type_mapping.get(doc_type.lower(), 5)
        
        count_crit = 0
        count_high = 0
        count_med = 0
        count_low = 0
        math_fail_flag = 0
        sig_fail_flag = 0
        
        for rule in failed_rules:
            rid = rule.get("rule_id", "")
            sev = rule.get("severity", "medium").lower()
            if sev == "critical":
                count_crit += 1
            elif sev == "high":
                count_high += 1
            elif sev == "medium":
                count_med += 1
            elif sev == "low":
                count_low += 1
                
            if "R003" in rid:
                math_fail_flag = 1
            if "R004" in rid:
                sig_fail_flag = 1
                
        return [doc_type_val, page_count, score, count_crit, count_high, count_med, count_low, math_fail_flag, sig_fail_flag]

    def predict_risk(self, doc_type: str, page_count: int, score: float, failed_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Predicts compliance status: Compliant, Partially Compliant, Non-Compliant."""
        features = self.extract_features(doc_type, page_count, score, failed_rules)
        
        if ML_AVAILABLE and self.model is not None:
            try:
                X_inference = np.array([features])
                prediction_class = int(self.model.predict(X_inference)[0])
                probabilities = self.model.predict_proba(X_inference)[0].tolist() # [p_comp, p_part, p_non]
                
                classes = ["Compliant", "Partially Compliant", "Non-Compliant"]
                prediction = classes[prediction_class]
                
                return {
                    "prediction": prediction,
                    "probabilities": {
                        "compliant": round(probabilities[0] * 100, 2),
                        "partially_compliant": round(probabilities[1] * 100, 2),
                        "non_compliant": round(probabilities[2] * 100, 2),
                    },
                    "features_used": features,
                    "mode": "ML Random Forest"
                }
            except Exception as e:
                logger.error(f"Inference error: {e}. Falling back to rule-based prediction.")
                
        # Rule-based fallback if ML not available or errors out
        score = float(score)
        crit_count = features[3]
        high_count = features[4]
        
        if score >= 85.0 and crit_count == 0 and high_count == 0:
            pred = "Compliant"
            probs = {"compliant": 90.0, "partially_compliant": 8.0, "non_compliant": 2.0}
        elif score >= 50.0 and crit_count == 0:
            pred = "Partially Compliant"
            probs = {"compliant": 15.0, "partially_compliant": 70.0, "non_compliant": 15.0}
        else:
            pred = "Non-Compliant"
            probs = {"compliant": 2.0, "partially_compliant": 18.0, "non_compliant": 80.0}
            
        return {
            "prediction": pred,
            "probabilities": probs,
            "features_used": features,
            "mode": "Rule-based Fallback"
        }
