from bioops.agents.base import BaseAgent
from bioops.tools.k8s_health import K8sHealthTool, PodStatus


class ClusterHealthAgent(BaseAgent):
    """Reports Kubernetes cluster health for BioOps pipeline runs."""

    name = "cluster_health"
    description = "Checks k8s pod health, running pipeline steps, logs, cost, and ETA."

    def __init__(self, health_tool: K8sHealthTool | None = None):
        self.health_tool = health_tool or K8sHealthTool()

    def run(self, message: str) -> str:
        pods = self.health_tool.get_pods()
        errors = self.health_tool.get_recent_errors()

        return self._format_report(pods, errors)

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
            return "Cluster Health Report\n\nNo active pipeline pods found."

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

        lines.append("")
        lines.append("Errors:")

        if errors:
            for error in errors:
                lines.append(f"- {error}")
        else:
            lines.append("- No recent errors found.")

        lines.extend(
            [
                "",
                "Cost estimate: not implemented yet.",
                "ETA estimate: not implemented yet.",
            ]
        )

        return "\n".join(lines)