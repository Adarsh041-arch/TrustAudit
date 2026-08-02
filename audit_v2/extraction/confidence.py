from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfidenceConfig:
    vlm_only_penalty: float = 0.15
    disagreement_penalty: float = 0.50
    text_layer_bonus: float = 0.05
    low_agreement_threshold: float = 0.80
    high_agreement_threshold: float = 0.95


DEFAULT_CONFIDENCE_CONFIG = ConfidenceConfig()


def compute_field_confidence(
    field_name: str,
    text_layer_confidence: float | None,
    vlm_confidence: float | None,
    agreement: float | None,
    config: ConfidenceConfig | None = None,
) -> float:
    cfg = config or DEFAULT_CONFIDENCE_CONFIG

    if text_layer_confidence is not None and vlm_confidence is not None:
        base = max(text_layer_confidence, vlm_confidence)
        if agreement is not None and agreement < cfg.low_agreement_threshold:
            base -= cfg.disagreement_penalty * (1.0 - agreement)
        elif agreement is not None and agreement > cfg.high_agreement_threshold:
            base = min(1.0, base + cfg.text_layer_bonus)
        return max(0.0, min(1.0, base))

    if text_layer_confidence is not None:
        return max(0.0, min(1.0, text_layer_confidence))

    if vlm_confidence is not None:
        return max(0.0, min(1.0, vlm_confidence - cfg.vlm_only_penalty))

    return 0.5


def agreement_score(extraction_a: dict[str, str], extraction_b: dict[str, str]) -> float:
    common_keys = set(extraction_a) & set(extraction_b)
    if not common_keys:
        return 1.0

    agreements = sum(
        1 for key in common_keys
        if extraction_a[key].strip().lower() == extraction_b[key].strip().lower()
    )

    return agreements / len(common_keys)
