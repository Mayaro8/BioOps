from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
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

    def run(self, message: str) -> str:
        try:
            pods = self.health_tool.get_pods()
            errors = self.health_tool.get_recent_errors()
        except Exception as error:
            return (
                "Cluster Health Report\n\n"
                "Status: unavailable\n"
                f"Reason: failed to query Kubernetes: {error}\n"
                "\n"
                "Cost estimate: unavailable — cloud billing access is not configured yet.\n"
                "ETA estimate: unavailable — historical runtime data is not configured yet."
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
            f", runtime: {pod.runtime_minutes} min"
            if pod.runtime_minutes is not None
            else ""
        )

        return f"- {step}: {pod.name} [{pod.phase}{runtime}]"

    def _format_report(self, pods: list[PodStatus], errors: list[str]) -> str:
        if not pods:
            return (
                "Cluster Health Report\n\n"
                "No active pipeline pods found.\n"
                "\n"
                "Cost estimate: unavailable — cloud billing access is not configured yet.\n"
                "ETA estimate: unavailable — historical runtime data is not configured yet."
            )

        running_pods = [pod for pod in pods if pod.phase == "Running"]
        unhealthy_pods = [
            pod for pod in pods
            if pod.phase not in {"Running", "Succeeded"}
        ]

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

        lines.extend(
            [
                "",
                "Cost estimate: unavailable — cloud billing access is not configured yet.",
                "ETA estimate: unavailable — historical runtime data is not configured yet.",
            ]
        )

        return "\n".join(lines)
