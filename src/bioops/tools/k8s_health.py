from dataclasses import dataclass
from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


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
    """Reads pod health and log errors from a real Kubernetes cluster."""

    def __init__(self, namespace: str = "bioops"):
        self.namespace = namespace
        config.load_kube_config()
        self.core_api = client.CoreV1Api()

    def get_pods(self) -> list[PodStatus]:
        pods = self.core_api.list_namespaced_pod(namespace=self.namespace)

        pod_statuses = []

        for pod in pods.items:
            labels = pod.metadata.labels or {}

            started_at = pod.status.start_time

            runtime_minutes = None
            if started_at is not None:
                runtime_minutes = round(
                    (datetime.now(timezone.utc) - started_at).total_seconds() / 60,
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

    def get_pod_logs(self, pod_name: str, tail_lines: int = 50) -> str:
        """Read recent logs from one pod."""
        try:
            logs = self.core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.namespace,
                tail_lines=tail_lines,
            )

            if isinstance(logs, bytes):
                return logs.decode("utf-8", errors="replace")

            if isinstance(logs, str) and logs.startswith("b'"):
                return logs.removeprefix("b'").removesuffix("'").replace("\\n", "\n")

            if isinstance(logs, str) and logs.startswith('b"'):
                return logs.removeprefix('b"').removesuffix('"').replace("\\n", "\n")

            return str(logs)

        except ApiException as exc:
            return f"Could not read logs for {pod_name}: {exc}"

    def _extract_error_lines(self, logs: str) -> list[str]:
        """Extract suspicious log lines."""
        error_keywords = [
            "error",
            "failed",
            "failure",
            "exception",
            "traceback",
            "oomkilled",
            "killed",
            "cannot",
            "denied",
        ]

        suspicious_lines = []

        for line in logs.splitlines():
            lowered_line = line.lower()

            if any(keyword in lowered_line for keyword in error_keywords):
                suspicious_lines.append(line.strip())

        return suspicious_lines[:5]

    def get_recent_errors(self) -> list[str]:
        errors = []

        try:
            pods = self.core_api.list_namespaced_pod(namespace=self.namespace)
        except ApiException as exc:
            return [f"Could not read pods from namespace {self.namespace}: {exc}"]

        for pod in pods.items:
            pod_name = pod.metadata.name
            phase = pod.status.phase

            if phase not in {"Running", "Succeeded"}:
                errors.append(f"{pod_name} is in phase {phase}.")

                logs = self.get_pod_logs(pod_name)
                error_lines = self._extract_error_lines(logs)

                for line in error_lines:
                    errors.append(f"{pod_name} log error: {line}")

            for container_status in pod.status.container_statuses or []:
                waiting = container_status.state.waiting
                terminated = container_status.state.terminated

                if waiting is not None:
                    errors.append(
                        f"{pod_name}/{container_status.name} waiting: "
                        f"{waiting.reason}"
                    )

                if terminated is not None and terminated.exit_code != 0:
                    errors.append(
                        f"{pod_name}/{container_status.name} terminated: "
                        f"{terminated.reason}, exit code {terminated.exit_code}"
                    )

        if not errors:
            return ["No recent errors found."]

        return errors