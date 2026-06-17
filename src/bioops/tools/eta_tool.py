from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bioops.tools.k8s_health import PodStatus


@dataclass
class ETAReport:
    """ETA estimate for one running Kubernetes pod."""

    pod_name: str
    pipeline_step: str
    runtime_minutes: float | None
    expected_minutes: float | None
    remaining_minutes: float | None
    source: str


class ETATool:
    """Estimates remaining time for running pipeline steps."""

    def __init__(self, step_eta_minutes: dict[str, Any] | None = None):
        self.step_eta_minutes = step_eta_minutes or {}

    def estimate_for_pod(self, pod: PodStatus) -> ETAReport:
        step = pod.pipeline_step or "unknown step"
        runtime = pod.runtime_minutes

        expected_raw = self.step_eta_minutes.get(step)
        expected = float(expected_raw) if expected_raw is not None else None

        if expected is None:
            return ETAReport(
                pod_name=pod.name,
                pipeline_step=step,
                runtime_minutes=runtime,
                expected_minutes=None,
                remaining_minutes=None,
                source="unavailable: no expected duration configured for this step",
            )

        if runtime is None:
            return ETAReport(
                pod_name=pod.name,
                pipeline_step=step,
                runtime_minutes=None,
                expected_minutes=expected,
                remaining_minutes=None,
                source="unavailable: pod runtime is not available",
            )

        remaining = max(expected - runtime, 0.0)

        return ETAReport(
            pod_name=pod.name,
            pipeline_step=step,
            runtime_minutes=runtime,
            expected_minutes=expected,
            remaining_minutes=round(remaining, 2),
            source="configured expected duration minus current pod runtime",
        )

    def estimate_for_running_pods(self, pods: list[PodStatus]) -> list[ETAReport]:
        return [
            self.estimate_for_pod(pod)
            for pod in pods
            if pod.phase == "Running"
        ]
