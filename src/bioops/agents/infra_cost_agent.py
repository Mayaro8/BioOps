from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.infra_cost_tool import InfraCostSummary, InfraCostTool


class InfraCostAgent(BaseAgent):
    """Reports infrastructure and cost monitoring readiness/status."""

    name = "infra_cost"
    description = "Monitors infrastructure health, cloud cost, ClickHouse, queues, and Cloud Functions."

    def __init__(
        self,
        infra_tool: InfraCostTool | None = None,
        config_path: str = "configs/agents.yaml",
    ):
        self.config = self._load_config(config_path)
        self.infra_config = self.config.get("agents", {}).get("infra_cost", {})

        self.infra_tool = infra_tool or InfraCostTool(
            yandex_cloud_id=self.infra_config.get("yandex_cloud_id"),
            yandex_folder_id=self.infra_config.get("yandex_folder_id"),
            yandex_service_account_key_path=self.infra_config.get(
                "yandex_service_account_key_path"
            ),
            clickhouse_dsn=self.infra_config.get("clickhouse_dsn"),
            queue_url=self.infra_config.get("queue_url"),
            cloud_functions_endpoint=self.infra_config.get(
                "cloud_functions_endpoint"
            ),
        )

    def run(self, message: str) -> str:
        summary = self.infra_tool.summarize()
        return self._format_report(summary)

    def _load_config(self, config_path: str) -> dict[str, Any]:
        path = Path(config_path)

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def _format_bool(self, value: bool) -> str:
        return "configured" if value else "not configured"

    def _format_report(self, summary: InfraCostSummary) -> str:
        lines = [
            "Infra / Cost Monitoring Report",
            "",
            f"Status: {summary.status}",
            "",
            "Integration status:",
            f"- Yandex Cloud: {self._format_bool(summary.yandex_cloud_configured)}",
            f"- ClickHouse: {self._format_bool(summary.clickhouse_configured)}",
            f"- Queue: {self._format_bool(summary.queue_configured)}",
            f"- Cloud Functions: {self._format_bool(summary.cloud_functions_configured)}",
            "",
            "Available now:",
        ]

        lines.extend(f"- {item}" for item in summary.checks_available_now)

        lines.extend(["", "Blocked until access/config is available:"])
        lines.extend(f"- {item}" for item in summary.checks_blocked_until_access)

        lines.extend(["", "Missing configuration:"])

        if summary.missing_config:
            lines.extend(f"- {item}" for item in summary.missing_config)
        else:
            lines.append("- none")

        lines.extend(["", "No cloud resources were modified."])

        return "\n".join(lines)
