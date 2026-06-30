from dataclasses import dataclass
from typing import Any


@dataclass
class ETAReport:
    pod_name: str
    step_name: str
    expected_minutes: float | None
    runtime_minutes: float | None
    remaining_minutes: float | None
    note: str


class ETATool:
    """Estimate ETA for running Kubernetes pods using configured step runtimes."""

    def __init__(self, step_eta_minutes: dict[str, Any] | None = None) -> None:
        self.step_eta_minutes = step_eta_minutes or {}

    def estimate_for_pod(self, pod: Any) -> ETAReport:
        pod_name = getattr(pod, "name", "unknown-pod")
        step_name = getattr(pod, "pipeline_step", None) or "unknown"
        runtime_minutes = getattr(pod, "runtime_minutes", None)

        expected = self.step_eta_minutes.get(step_name)

        if expected is None:
            return ETAReport(
                pod_name=pod_name,
                step_name=step_name,
                expected_minutes=None,
                runtime_minutes=runtime_minutes,
                remaining_minutes=None,
                note="No configured expected runtime for this pipeline step.",
            )

        expected = float(expected)
        runtime = float(runtime_minutes or 0.0)
        remaining = max(expected - runtime, 0.0)

        return ETAReport(
            pod_name=pod_name,
            step_name=step_name,
            expected_minutes=expected,
            runtime_minutes=runtime,
            remaining_minutes=remaining,
            note="ETA estimated from configured expected runtime minus current pod runtime.",
        )

    def estimate_for_running_pod(self, pod: Any) -> ETAReport:
        return self.estimate_for_pod(pod)

    def estimate_for_running_pods(self, pods: list[Any]) -> list[ETAReport]:
        return [self.estimate_for_pod(pod) for pod in pods]

    def estimate_step_eta(
        self,
        step_name: str | None,
        runtime_minutes: float | None = None,
    ) -> ETAReport:
        class SimplePod:
            pass

        pod = SimplePod()
        pod.name = "unknown-pod"
        pod.pipeline_step = step_name or "unknown"
        pod.runtime_minutes = runtime_minutes
        return self.estimate_for_pod(pod)

    def estimate_remaining_minutes(
        self,
        step_name: str | None,
        runtime_minutes: float | None = None,
    ) -> ETAReport:
        return self.estimate_step_eta(step_name, runtime_minutes)
