from dataclasses import dataclass
from collections import Counter, defaultdict

from bioops.tools.k8s_health import K8sHealthTool, PodStatus


@dataclass
class BatchStepStatus:
    step: str
    total: int
    running: int
    failed: int
    succeeded: int
    pending: int
    pods: list[str]


@dataclass
class BatchStatusReport:
    total_pods: int
    running: int
    failed: int
    succeeded: int
    pending: int
    steps: list[BatchStepStatus]


class BatchStatusTool:
    """Summarizes pipeline/batch status from Kubernetes pod states."""

    def __init__(self, health_tool: K8sHealthTool | None = None):
        self.health_tool = health_tool or K8sHealthTool()

    def get_status(self) -> BatchStatusReport:
        pods = self.health_tool.get_pods()

        phase_counts = Counter(pod.phase for pod in pods)
        steps = self._summarize_steps(pods)

        return BatchStatusReport(
            total_pods=len(pods),
            running=phase_counts.get("Running", 0),
            failed=phase_counts.get("Failed", 0),
            succeeded=phase_counts.get("Succeeded", 0),
            pending=phase_counts.get("Pending", 0),
            steps=steps,
        )

    def _summarize_steps(self, pods: list[PodStatus]) -> list[BatchStepStatus]:
        grouped: dict[str, list[PodStatus]] = defaultdict(list)

        for pod in pods:
            step = pod.pipeline_step or "unknown"
            grouped[step].append(pod)

        step_statuses: list[BatchStepStatus] = []

        for step, step_pods in sorted(grouped.items()):
            phase_counts = Counter(pod.phase for pod in step_pods)

            step_statuses.append(
                BatchStepStatus(
                    step=step,
                    total=len(step_pods),
                    running=phase_counts.get("Running", 0),
                    failed=phase_counts.get("Failed", 0),
                    succeeded=phase_counts.get("Succeeded", 0),
                    pending=phase_counts.get("Pending", 0),
                    pods=[pod.name for pod in step_pods],
                )
            )

        return step_statuses
