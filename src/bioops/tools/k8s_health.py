from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException


@dataclass
class PodStatus:
    name: str
    namespace: str
    phase: str
    node_name: str | None
    pipeline_step: str | None
    started_at: str | None
    runtime_minutes: float | None


class K8sHealthTool:
    """Read current Kubernetes pod health and recent failures."""

    def __init__(
        self,
        namespace: str = "bioops",
        request_timeout_seconds: int = 5,
        log_tail_lines: int = 50,
        recent_error_minutes: int = 60,
    ) -> None:
        self.namespace = namespace
        self.request_timeout_seconds = request_timeout_seconds
        self.log_tail_lines = log_tail_lines
        self.recent_error_minutes = recent_error_minutes

        self._load_kubernetes_config()
        self.core_api = client.CoreV1Api()

    def _load_kubernetes_config(self) -> None:
        try:
            config.load_incluster_config()
        except ConfigException:
            config.load_kube_config()

    def get_pods(self) -> list[PodStatus]:
        pods = self.core_api.list_namespaced_pod(
            namespace=self.namespace,
            _request_timeout=self.request_timeout_seconds,
        )

        now = datetime.now(timezone.utc)
        pod_statuses: list[PodStatus] = []

        for pod in pods.items:
            labels = pod.metadata.labels or {}
            started_at = pod.status.start_time

            runtime_minutes = None
            if started_at is not None:
                runtime_minutes = round(
                    (now - started_at).total_seconds() / 60,
                    1,
                )

            pod_statuses.append(
                PodStatus(
                    name=pod.metadata.name,
                    namespace=pod.metadata.namespace,
                    phase=pod.status.phase,
                    node_name=pod.spec.node_name,
                    pipeline_step=labels.get("pipeline_step"),
                    started_at=started_at.isoformat() if started_at else None,
                    runtime_minutes=runtime_minutes,
                )
            )

        return pod_statuses

    def get_pod_logs(
        self,
        pod_name: str,
        tail_lines: int | None = None,
    ) -> str:
        effective_tail_lines = (
            tail_lines
            if tail_lines is not None
            else self.log_tail_lines
        )

        try:
            logs = self.core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.namespace,
                tail_lines=effective_tail_lines,
                _request_timeout=self.request_timeout_seconds,
            )

            if isinstance(logs, bytes):
                return logs.decode("utf-8", errors="replace")

            if isinstance(logs, str) and logs.startswith("b'"):
                return (
                    logs.removeprefix("b'")
                    .removesuffix("'")
                    .replace("\\n", "\n")
                )

            if isinstance(logs, str) and logs.startswith('b"'):
                return (
                    logs.removeprefix('b"')
                    .removesuffix('"')
                    .replace("\\n", "\n")
                )

            return str(logs)

        except ApiException as exc:
            return f"Could not read logs for {pod_name}: {exc.reason}"

    def _pod_event_time(self, pod: Any) -> datetime | None:
        event_times: list[datetime] = []

        if pod.status.start_time is not None:
            event_times.append(pod.status.start_time)

        statuses = [
            *(getattr(pod.status, "init_container_statuses", None) or []),
            *(getattr(pod.status, "container_statuses", None) or []),
        ]

        for container_status in statuses:
            terminated = container_status.state.terminated

            if terminated is not None and terminated.finished_at is not None:
                event_times.append(terminated.finished_at)

        return max(event_times) if event_times else None

    def _is_recent(self, pod: Any) -> bool:
        event_time = self._pod_event_time(pod)

        if event_time is None:
            return True

        age_minutes = (
            datetime.now(timezone.utc) - event_time
        ).total_seconds() / 60

        return age_minutes <= self.recent_error_minutes

    def _extract_error_summary(self, logs: str) -> str | None:
        if logs.startswith("Could not read logs"):
            return None

        keywords = (
            "forbidden",
            "oomkilled",
            "notfounderror",
            "permission denied",
            "connection refused",
            "timeout",
            "exception",
            "error",
            "failed",
        )

        for raw_line in reversed(logs.splitlines()):
            line = " ".join(raw_line.strip().split())
            lowered = line.lower()

            if not line:
                continue

            if "forbidden" in lowered:
                return "Kubernetes RBAC denied the requested operation."

            if "oomkilled" in lowered:
                return "Container was terminated because it exceeded its memory limit."

            if any(keyword in lowered for keyword in keywords):
                if len(line) > 220:
                    line = f"{line[:217]}..."

                return line

        return None

    def _container_problem(self, pod: Any) -> str | None:
        statuses = [
            *(getattr(pod.status, "init_container_statuses", None) or []),
            *(getattr(pod.status, "container_statuses", None) or []),
        ]

        for container_status in statuses:
            waiting = container_status.state.waiting

            if waiting is not None:
                detail = waiting.reason or "unknown reason"

                if waiting.message:
                    message = " ".join(waiting.message.split())
                    detail = f"{detail}: {message[:160]}"

                return (
                    f"{pod.metadata.name}/{container_status.name} "
                    f"is waiting: {detail}"
                )

        for container_status in statuses:
            terminated = container_status.state.terminated

            if terminated is not None and terminated.exit_code != 0:
                reason = terminated.reason or "Error"

                return (
                    f"{pod.metadata.name}/{container_status.name} "
                    f"terminated with {reason}, exit code "
                    f"{terminated.exit_code}"
                )

        return None

    def get_recent_errors(self) -> list[str]:
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=self.namespace,
                _request_timeout=self.request_timeout_seconds,
            )
        except ApiException as exc:
            return [
                f"Could not read pods from namespace "
                f"{self.namespace}: {exc.reason}"
            ]

        errors: list[str] = []

        for pod in pods.items:
            phase = pod.status.phase
            container_problem = self._container_problem(pod)

            # Running pods are only reported when a container is waiting.
            if phase == "Running" and container_problem is None:
                continue

            # Successful pods are historical noise.
            if phase == "Succeeded":
                continue

            # Old failures are omitted from a current-health report.
            if not self._is_recent(pod) and container_problem is None:
                continue

            summary = container_problem

            # Read logs only for simple single-container failed pods.
            container_statuses = (
                getattr(pod.status, "container_statuses", None) or []
            )

            if (
                summary is None
                and phase == "Failed"
                and len(container_statuses) <= 1
            ):
                log_summary = self._extract_error_summary(
                    self.get_pod_logs(pod.metadata.name)
                )

                if log_summary:
                    summary = f"{pod.metadata.name} failed: {log_summary}"

            if summary is None:
                summary = f"{pod.metadata.name} is in phase {phase}"

            if summary not in errors:
                errors.append(summary)

        return errors
