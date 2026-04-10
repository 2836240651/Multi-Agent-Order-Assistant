from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


SUPPORTED_VARIANTS = ("baseline_v1", "optimized_v2", "current_v3")


@dataclass
class RolloutDecision:
    selected_variant: str
    source: str


class RolloutManager:
    def __init__(self, weights: dict[str, int] | None = None):
        self._weights = self._normalize(weights or {"baseline_v1": 10, "optimized_v2": 20, "current_v3": 70})

    @staticmethod
    def _normalize(weights: dict[str, int]) -> dict[str, int]:
        normalized = {variant: max(0, int(weights.get(variant, 0))) for variant in SUPPORTED_VARIANTS}
        total = sum(normalized.values())
        if total <= 0:
            return {"baseline_v1": 0, "optimized_v2": 0, "current_v3": 100}
        return normalized

    def update_weights(self, weights: dict[str, int]) -> dict[str, int]:
        self._weights = self._normalize(weights)
        return self._weights

    def get_weights(self) -> dict[str, int]:
        return dict(self._weights)

    def decide(self, *, user_id: str, requested_variant: str | None = None) -> RolloutDecision:
        if requested_variant:
            if requested_variant not in SUPPORTED_VARIANTS:
                raise ValueError(f"Unsupported rollout variant: {requested_variant}")
            return RolloutDecision(selected_variant=requested_variant, source="request_override")

        total = sum(self._weights.values())
        if total <= 0:
            return RolloutDecision(selected_variant="current_v3", source="default_fallback")

        score = int(hashlib.sha256(user_id.encode("utf-8")).hexdigest(), 16) % total
        cursor = 0
        for variant in SUPPORTED_VARIANTS:
            weight = self._weights.get(variant, 0)
            cursor += weight
            if score < cursor:
                return RolloutDecision(selected_variant=variant, source="weighted_rollout")
        return RolloutDecision(selected_variant="current_v3", source="default_fallback")

    def summary(self) -> dict[str, Any]:
        total = sum(self._weights.values()) or 1
        return {
            "weights": self.get_weights(),
            "percentages": {
                variant: round(self._weights.get(variant, 0) / total, 4)
                for variant in SUPPORTED_VARIANTS
            },
            "supported_variants": list(SUPPORTED_VARIANTS),
        }
