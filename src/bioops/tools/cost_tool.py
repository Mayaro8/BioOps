from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CostReport:
    """Cost estimate for the Kubernetes environment."""

    total_cost_usd: float
    currency: str
    mode: str
    source: str
    note: str


class CostTool:
    """Estimates cluster cost using configurable modes.

    Supported MVP modes:
    - local_free: reports $0.00 for local/minikube/free-tier demo clusters.
    - manual_rate: estimates cost from runtime and a configured hourly rate.

    This tool does not call a real cloud billing API yet.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.mode = self.config.get("mode", "local_free")
        self.currency = self.config.get("currency", "USD")

    def estimate_cluster_cost(self, runtime_minutes: float | None = None) -> CostReport:
        if self.mode == "local_free":
            return CostReport(
                total_cost_usd=0.0,
                currency=self.currency,
                mode=self.mode,
                source="local/free Kubernetes environment",
                note="No cloud billing API is connected; local/free mode reports direct cloud cost as zero.",
            )

        if self.mode == "manual_rate":
            hourly_rate = float(self.config.get("hourly_cluster_rate_usd", 0.0))
            runtime_hours = (runtime_minutes or 0.0) / 60.0
            total_cost = hourly_rate * runtime_hours

            return CostReport(
                total_cost_usd=round(total_cost, 4),
                currency=self.currency,
                mode=self.mode,
                source="manual hourly cluster rate",
                note=(
                    f"Estimated from runtime_minutes={runtime_minutes or 0.0:.2f} "
                    f"and hourly rate={hourly_rate:.4f}."
                ),
            )

        return CostReport(
            total_cost_usd=0.0,
            currency=self.currency,
            mode=self.mode,
            source="unconfigured",
            note=f"Cost mode '{self.mode}' is not implemented yet.",
        )

