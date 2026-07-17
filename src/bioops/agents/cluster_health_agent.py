from pathlib import Path
from statistics import fmean, quantiles
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.cost_tool import CostTool
from bioops.tools.eta_tool import ETATool
from bioops.tools.k8s_health import K8sHealthTool, PodStatus


class ClusterHealthAgent(BaseAgent):
    """Report concise current Kubernetes health for BioOps."""

    name = "cluster_health"
    description = "Checks Kubernetes services, active pipeline steps, cost, and ETA."

    INFRASTRUCTURE = {
        "bioops-api": "bioops-api",
        "qdrant": "qdrant",
    }

    def __init__(
        self,
        health_tool: K8sHealthTool | None = None,
        config_path: str = "configs/agents.yaml",
    ):
        self.config = self._load_config(config_path)
        cluster_config = self.config.get("agents", {}).get(
            "cluster_health",
            {},
        )

        self.health_tool = health_tool or K8sHealthTool(
            namespace=cluster_config.get("namespace", "bioops"),
            request_timeout_seconds=cluster_config.get(
                "request_timeout_seconds",
                5,
            ),
            log_tail_lines=cluster_config.get("log_tail_lines", 50),
            recent_error_minutes=cluster_config.get(
                "recent_error_minutes",
                60,
            ),
        )

        self.cost_tool = CostTool(cluster_config.get("cost", {}))
        self.eta_tool = ETATool(
            cluster_config.get("step_eta_minutes", {})
        )

    def run(self, message: str) -> str:
        try:
            pods = self.health_tool.get_pods()
            errors = self.health_tool.get_recent_errors()
        except Exception as error:
            cost_report = self.cost_tool.estimate_cluster_cost(
                runtime_minutes=0.0
            )
            currency = str(cost_report.currency).upper()

            return (
                "Cluster Health Report\n\n"
                "Overall status: Unavailable\n"
                f"Reason: failed to query Kubernetes: {error}\n\n"
                "Cost:\n"
                f"- Estimated cost: "
                f"{cost_report.total_cost_usd:.2f} {currency}\n"
                f"- Mode: {cost_report.mode}"
            )

        return self._format_report(pods, errors)

    def _load_config(self, config_path: str) -> dict[str, Any]:
        path = Path(config_path)

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def _is_infrastructure_pod(self, pod: PodStatus) -> bool:
        return any(
            pod.name.startswith(prefix)
            for prefix in self.INFRASTRUCTURE.values()
        )

    def _format_pipeline_section(
        self,
        pipeline_pods: list[PodStatus],
    ) -> list[str]:
        total_pods = len(pipeline_pods)
        pods_by_step: dict[str, int] = {}

        for pod in pipeline_pods:
            step = pod.pipeline_step or "unknown"
            pods_by_step[step] = pods_by_step.get(step, 0) + 1

        return [
            (
                f"- {step}: {count} {'pod' if count == 1 else 'pods'} "
                f"({count / total_pods * 100:.1f}% of active pipeline pods)"
            )
            for step, count in sorted(pods_by_step.items())
        ]

    def _format_runtime_statistics_section(
        self,
        pipeline_pods: list[PodStatus],
    ) -> list[str]:
        runtime_pods = [
            pod
            for pod in pipeline_pods
            if pod.runtime_minutes is not None
        ]

        lines = ["", "Active pipeline runtime statistics:"]

        if not runtime_pods:
            lines.append("- No active pipeline runtime data.")
            return lines

        runtimes = sorted(
            float(pod.runtime_minutes)
            for pod in runtime_pods
            if pod.runtime_minutes is not None
        )

        if len(runtimes) == 1:
            q1 = q2 = q3 = runtimes[0]
        else:
            q1, q2, q3 = quantiles(
                runtimes,
                n=4,
                method="inclusive",
            )

        shortest = min(
            runtime_pods,
            key=lambda pod: float(pod.runtime_minutes or 0.0),
        )
        longest = max(
            runtime_pods,
            key=lambda pod: float(pod.runtime_minutes or 0.0),
        )

        lines.extend(
            [
                f"- Pods measured: {len(runtime_pods)}",
                f"- Average runtime: {fmean(runtimes):.1f} min",
                f"- Q1 (25th percentile): {q1:.1f} min",
                f"- Median (Q2): {q2:.1f} min",
                f"- Q3 (75th percentile): {q3:.1f} min",
                (
                    f"- Shortest-running pod: {shortest.name} "
                    f"({shortest.pipeline_step}, "
                    f"{float(shortest.runtime_minutes or 0.0):.1f} min)"
                ),
                (
                    f"- Longest-running pod: {longest.name} "
                    f"({longest.pipeline_step}, "
                    f"{float(longest.runtime_minutes or 0.0):.1f} min)"
                ),
            ]
        )

        return lines

    def _estimate_report_cost(
        self,
        running_pods: list[PodStatus],
    ) -> Any:
        max_runtime_minutes = max(
            [pod.runtime_minutes or 0.0 for pod in running_pods],
            default=0.0,
        )

        return self.cost_tool.estimate_cluster_cost(
            runtime_minutes=max_runtime_minutes,
        )

    def _format_cost_section(
        self,
        running_pods: list[PodStatus],
    ) -> list[str]:
        report = self._estimate_report_cost(running_pods)
        currency = str(report.currency).upper()

        return [
            "",
            "Cost:",
            f"- Estimated cost: "
            f"{report.total_cost_usd:.2f} {currency}",
            f"- Mode: {report.mode}",
            f"- Note: {report.note}",
        ]

    def _format_eta_section(
        self,
        pipeline_pods: list[PodStatus],
    ) -> list[str]:
        configured_steps = set(self.eta_tool.step_eta_minutes)

        eta_pods = [
            pod
            for pod in pipeline_pods
            if pod.pipeline_step in configured_steps
        ]

        lines = ["", "ETA:"]

        if not eta_pods:
            lines.append(
                "- No active pipeline steps with a configured ETA."
            )
            return lines

        reports = self.eta_tool.estimate_for_running_pods(eta_pods)

        remaining_by_step: dict[str, list[float]] = {}

        for report in reports:
            if report.remaining_minutes is None:
                continue

            remaining_by_step.setdefault(
                report.pipeline_step,
                [],
            ).append(float(report.remaining_minutes))

        for step in sorted(remaining_by_step):
            remaining_times = remaining_by_step[step]
            pod_count = len(remaining_times)
            pod_word = "pod" if pod_count == 1 else "pods"

            lines.append(
                f"- {step}: average "
                f"~{fmean(remaining_times):.1f} min remaining "
                f"across {pod_count} {pod_word}"
            )

        if len(lines) == 2:
            lines.append("- No ETA currently available.")

        return lines

    def _infrastructure_status(
        self,
        pods: list[PodStatus],
        prefix: str,
    ) -> tuple[str, bool]:
        matches = [
            pod
            for pod in pods
            if pod.name.startswith(prefix)
        ]

        running = [
            pod
            for pod in matches
            if pod.phase == "Running"
        ]

        if running:
            return "Running", True

        if matches:
            newest = min(
                matches,
                key=lambda pod: pod.runtime_minutes
                if pod.runtime_minutes is not None
                else float("inf"),
            )
            return newest.phase, False

        return "Not found", False

    def _format_report(
        self,
        pods: list[PodStatus],
        errors: list[str],
    ) -> str:
        running_pods = [
            pod for pod in pods
            if pod.phase == "Running"
        ]

        pipeline_pods = [
            pod
            for pod in running_pods
            if pod.pipeline_step
            and not self._is_infrastructure_pod(pod)
        ]

        other_running_pods = [
            pod
            for pod in running_pods
            if not pod.pipeline_step
            and not self._is_infrastructure_pod(pod)
        ]

        infrastructure_lines: list[str] = []
        infrastructure_healthy = True

        for display_name, prefix in self.INFRASTRUCTURE.items():
            status, healthy = self._infrastructure_status(
                pods,
                prefix,
            )
            infrastructure_healthy = (
                infrastructure_healthy and healthy
            )
            infrastructure_lines.append(
                f"- {display_name}: {status}"
            )

        overall_status = (
            "Healthy"
            if infrastructure_healthy and not errors
            else "Degraded"
        )

        lines = [
            "Cluster Health Report",
            "",
            f"Overall status: {overall_status}",
            f"Running pods: {len(running_pods)}",
            "",
            "Infrastructure:",
            *infrastructure_lines,
            "",
            "Active pipeline steps:",
        ]

        if pipeline_pods:
            lines.extend(self._format_pipeline_section(pipeline_pods))
        else:
            lines.append("- No active pipeline workflows.")

        lines.extend(
            self._format_runtime_statistics_section(pipeline_pods)
        )

        if other_running_pods:
            lines.extend(
                [
                    "",
                    f"Other active pods: {len(other_running_pods)}",
                ]
            )

        lines.extend(
            [
                "",
                (
                    f"Recent issues "
                    f"(last {self.health_tool.recent_error_minutes} min):"
                ),
            ]
        )

        if errors:
            lines.extend(f"- {error}" for error in errors[:3])
        else:
            lines.append("- None.")

        lines.extend(self._format_cost_section(running_pods))
        lines.extend(self._format_eta_section(pipeline_pods))

        return "\n".join(lines)
