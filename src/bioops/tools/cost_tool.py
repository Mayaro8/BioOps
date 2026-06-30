from dataclasses import dataclass
from typing import Any


@dataclass
class CostReport:
    total_cost_usd: float
    currency: str
    source: str
    mode: str
    note: str


class CostTool:
    """Estimate Kubernetes runtime cost for Cluster Health reports.

    Current mode is local/free. This keeps the assignment cost field realistic
    without pretending we have real cloud billing access.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.mode = self.config.get("mode", "local_free")
        self.currency = self.config.get("currency", "USD")

    def estimate_cluster_cost(self, runtime_minutes: float = 0.0) -> CostReport:
        if self.mode == "local_free":
            return CostReport(
                total_cost_usd=0.0,
                currency=self.currency,
                source="local_free",
                mode=self.mode,
                note="Local/free Kubernetes environment; no cloud billing API is used.",
            )

        return CostReport(
            total_cost_usd=0.0,
            currency=self.currency,
            source="not_configured",
            mode=self.mode,
            note="Cloud billing API is not configured; cost is reported as placeholder.",
        )
