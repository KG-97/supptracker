"""
Scoring engine for supplement interactions.

Computes risk scores and maps them to severity buckets based on
configurable weights and thresholds from risk_rules.yaml.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def make_scoring_engine(rules: dict) -> "ScoringEngine":
    """Create a scoring engine from the loaded rules configuration."""
    return ScoringEngine(rules)


class ScoringEngine:
    """Encapsulates the scoring logic and rule configuration."""

    def __init__(self, rules: dict):
        self.sev_map: Dict[str, int] = rules.get(
            "severity_map", {"None": 0, "Mild": 1, "Moderate": 2, "Severe": 3}
        )
        self.evd_map: Dict[str, int] = rules.get(
            "evidence_grade_map", {"A": 1, "B": 2, "C": 3, "D": 4}
        )
        self.weights: Dict[str, float] = rules.get(
            "weights",
            {"w_sev": 0.9, "w_evd": 0.4, "w_mech": 0.2, "w_dose": 0.3, "w_user": 0.3},
        )
        self.buckets: Dict[str, Dict[str, Any]] = rules.get(
            "buckets",
            {
                "low": {"min": 0.0, "max": 1.5, "label": "Low", "advice": "Low concern. Monitor only."},
                "medium": {"min": 1.5, "max": 3.0, "label": "Medium", "advice": "Use with care."},
                "high": {"min": 3.0, "max": 4.5, "label": "High", "advice": "Avoid combining or consult a clinician."},
                "critical": {"min": 4.5, "max": 100.0, "label": "Critical", "advice": "Do not combine."},
            },
        )

    def compute_score(
        self,
        interaction: Dict[str, Any],
        doses: Optional[str] = None,
        flags: Optional[str] = None,
    ) -> tuple[float, str, str]:
        """Compute a risk score and bucket/action for a given interaction record."""
        sev = self.sev_map.get(str(interaction.get("severity", "None")), 0)
        evd = self.evd_map.get(str(interaction.get("evidence_grade", "D")), 4)
        mech_tags = (
            str(interaction.get("mechanism_tags", "")).split(";")
            if interaction.get("mechanism_tags")
            else []
        )
        mech_boost = 0.05 * len([m for m in mech_tags if m.strip()])
        dose_factor = 0.1 if doses else 0.0
        user_factor = (
            0.1 * len([f for f in (flags or "").split(",") if f.strip()]) if flags else 0.0
        )
        score = (
            self.weights.get("w_sev", 0.9) * sev
            + self.weights.get("w_evd", 0.4) * (1.0 / evd if evd > 0 else 1.0)
            + self.weights.get("w_mech", 0.2) * mech_boost
            + self.weights.get("w_dose", 0.3) * dose_factor
            + self.weights.get("w_user", 0.3) * user_factor
        )
        # Determine bucket from ordered severity thresholds
        bucket_key = "low"
        for bk in ["critical", "high", "medium"]:
            if bk in self.buckets and score >= self.buckets[bk]["min"]:
                bucket_key = bk
                break

        bucket_cfg = self.buckets.get(bucket_key, self.buckets.get("low", {}))
        bucket_label = bucket_cfg.get("label", "Low")
        action = interaction.get("action") or bucket_cfg.get("advice", "No action needed")
        return round(float(score), 3), bucket_label, str(action)
