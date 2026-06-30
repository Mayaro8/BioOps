from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.cost_tool import CostTool
from bioops.tools.eta_tool import ETATool
from bioops.tools.k8s_health import K8sHealthTool, PodStatus


class ClusterHealthAgent(BaseAgent):
    """Reports Kubernetes cluster health for BioOps pipeline runs."""

    name = "cluster_health"
    description = "Checks k8s pod health, running pipeline steps, logs, cost, and ETA."

    def __init__(
        self,
        health_tool: K8sHealthTool | None = None,
        config_path: str = "configs/agents.yaml",
    ):
        self.config = self._load_config(config_path)
        cluster_config = self.config.get("agents", {}).get("cluster_health", {})

        self.health_tool = health_tool or K8sHealthTool(
            namespace=cluster_config.get("namespace", "bioops"),
            request_timeout_seconds=cluster_config.get("request_timeout_seconds", 5),
            log_tail_lines=cluster_config.get("log_tail_lines", 50),
        )

        self.cost_tool = CostTool(cluster_config.get("cost", {}))
        self.eta_tool = ETATool(cluster_config.get("step_eta_minutes", {}))

    def run(self, message: str) -> str:
        try:
            pods = self.health_tool.get_pods()
            errors = self.health_tool.get_recent_errors()
        except Exception as error:
            cost_report = self.cost_tool.estimate_cluster_cost(runtime_minutes=0.0)

            return (
                "Cluster Health Report\n\n"
                "Status: unavailable\n"
                f"Reason: failed to query Kubernetes: {error}\n"
                "\n"
                "Cost:\n"
                f"- Estimated cost: ${cost_report.total_cost_usd:.2f} {cost_report.currency}\n"
                f"- Source: {cost_report.source}\n"
                f"- Mode: {cost_report.mode}\n"
                f"- Note: {cost_report.note}\n"
                "\n"
                "ETA:\n"
                "- Unavailable: Kubernetes pod runtime data is not available."
            )

        return self._format_report(pods, errors)

    def _load_config(self, config_path: str) -> dict[str, Any]:
        path = Path(config_path)

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def _format_pod_line(self, pod: PodStatus) -> str:
        step = pod.pipeline_step or "unknown step"
        runtime = (
            f", runtime: {pod.runtime_minutes:.1f} min"
            if pod.runtime_minutes is not None
            else ""
        )

        return f"- {step}: {pod.name} [{pod.phase}{runtime}]"

    def _estimate_report_cost(self, running_pods: list[PodStatus]) -> Any:
        max_runtime_minutes = max(
            [pod.runtime_minutes or 0.0 for pod in running_pods],
            default=0.0,
        )

        return self.cost_tool.estimate_cluster_cost(
            runtime_minutes=max_runtime_minutes,
        )

    def _format_cost_section(self, running_pods: list[PodStatus]) -> list[str]:
        cost_report = self._estimate_report_cost(running_pods)

        return [
            "",
            "Cost:",
            f"- Estimated cost: ${cost_report.total_cost_usd:.2f} {cost_report.currency}",
            f"- Source: {cost_report.source}",
            f"- Mode: {cost_report.mode}",
            f"- Note: {cost_report.note}",
        ]

    def _format_eta_section(self, running_pods: list[PodStatus]) -> list[str]:
        eta_reports = self.eta_tool.estimate_for_running_pods(running_pods)

        lines = [
            "",
            "ETA:",
        ]

        if not running_pods:
            lines.append("- Unavailable: no running pods detected.")
            return lines

        if not eta_reports:
            lines.append("- Unavailable: no ETA reports generated.")
            return lines

        for eta in eta_reports:
            if eta.remaining_minutes is None:
                lines.append(
                    f"- {eta.pipeline_step}: unavailable for pod {eta.pod_name} "
                    f"({eta.source})"
                )
            else:
                lines.append(
                    f"- {eta.pipeline_step}: ~{eta.remaining_minutes:.1f} min remaining "
                    f"for pod {eta.pod_name} "
                    f"(runtime: {eta.runtime_minutes:.1f}/{eta.expected_minutes:.1f} min)"
                )

        return lines

    def _format_report(self, pods: list[PodStatus], errors: list[str]) -> str:
        running_pods = [pod for pod in pods if pod.phase == "Running"]
        unhealthy_pods = [
            pod for pod in pods
            if pod.phase not in {"Running", "Succeeded"}
        ]

        if not pods:
            lines = [
                "Cluster Health Report",
                "",
                "No active pipeline pods found.",
            ]

            lines.extend(self._format_cost_section(running_pods))
            lines.extend(self._format_eta_section(running_pods))

            return "\n".join(lines)

        lines = [
            "Cluster Health Report",
            "",
            f"Total pods: {len(pods)}",
            f"Running pods: {len(running_pods)}",
            f"Unhealthy / waiting pods: {len(unhealthy_pods)}",
            "",
            "Currently running pipeline steps:",
        ]

        if running_pods:
            for pod in running_pods:
                lines.append(self._format_pod_line(pod))
        else:
            lines.append("- No running pipeline steps found.")

        lines.extend(
            [
                "",
                "All observed pod statuses:",
            ]
        )

        for pod in pods:
            lines.append(self._format_pod_line(pod))

        lines.extend(
            [
                "",
                "Errors:",
            ]
        )

        if errors:
            for error in errors[:10]:
                lines.append(f"- {error}")
        else:
            lines.append("- No recent errors found.")

        lines.extend(self._format_cost_section(running_pods))
        lines.extend(self._format_eta_section(running_pods))

        return "\n".join(lines)
