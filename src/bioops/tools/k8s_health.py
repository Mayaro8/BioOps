from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException
from kubernetes.utils.quantity import parse_quantity


@dataclass
class PodStatus:
    name: str
    namespace: str
    phase: str
    node_name: str | None
    pipeline_step: str | None
    started_at: str | None
    runtime_minutes: float | None
    workflow_name: str | None = None
    batch_id: str | None = None
    sample_id: str | None = None


@dataclass
class NodePressureStatus:
    name: str
    ready: bool
    memory_pressure: bool
    disk_pressure: bool
    pid_pressure: bool
    network_unavailable: bool


@dataclass
class NodePressureReport:
    nodes: list[NodePressureStatus]
    active_pods: int
    pod_capacity: int
    cpu_usage_percent: float | None
    memory_usage_percent: float | None
    metrics_nodes: int
    unschedulable_workflow_pods: int
    scheduling_reasons: dict[str, int]


class K8sHealthTool:
    """Read Argo workflow pod health and recent pod errors."""

    WORKFLOW_LABEL = "workflows.argoproj.io/workflow"
    BATCH_LABEL = "bioops.dev/batch-id"
    SAMPLE_LABEL = "bioops.dev/sample-id"

    PROBLEM_WAITING_REASONS = {
        "CrashLoopBackOff",
        "CreateContainerConfigError",
        "CreateContainerError",
        "ErrImagePull",
        "ImagePullBackOff",
        "InvalidImageName",
        "RunContainerError",
    }

    ERROR_KEYWORDS = (
        "forbidden",
        "oomkilled",
        "out of memory",
        "notfounderror",
        "module not found",
        "permission denied",
        "connection refused",
        "timeout",
        "traceback",
        "exception",
        "error",
        "failed",
        "fatal",
    )

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
        response = self.core_api.list_namespaced_pod(
            namespace=self.namespace,
            _request_timeout=self.request_timeout_seconds,
        )

        now = datetime.now(timezone.utc)
        results: list[PodStatus] = []

        for pod in response.items:
            labels = pod.metadata.labels or {}
            started_at = getattr(pod.status, "start_time", None)

            runtime_minutes = None
            if started_at is not None:
                runtime_minutes = round(
                    (now - started_at).total_seconds() / 60,
                    1,
                )

            results.append(
                PodStatus(
                    name=pod.metadata.name,
                    namespace=pod.metadata.namespace,
                    phase=pod.status.phase,
                    node_name=pod.spec.node_name,
                    pipeline_step=labels.get("pipeline_step"),
                    started_at=(
                        started_at.isoformat()
                        if started_at is not None
                        else None
                    ),
                    runtime_minutes=runtime_minutes,
                    workflow_name=labels.get(self.WORKFLOW_LABEL),
                    batch_id=labels.get(self.BATCH_LABEL),
                    sample_id=labels.get(self.SAMPLE_LABEL),
                )
            )

        return results

    @staticmethod
    def _node_condition(node: Any, condition_type: str) -> bool:
        conditions = getattr(node.status, "conditions", None) or []
        return any(
            condition.type == condition_type
            and str(condition.status).lower() == "true"
            for condition in conditions
        )

    @staticmethod
    def _scheduling_reason(pod: Any) -> str:
        conditions = getattr(pod.status, "conditions", None) or []
        condition = next(
            (
                item
                for item in conditions
                if item.type == "PodScheduled"
                and str(item.status).lower() == "false"
            ),
            None,
        )
        detail = " ".join(
            filter(
                None,
                [
                    getattr(condition, "reason", None),
                    getattr(condition, "message", None),
                ],
            )
        ).lower()

        if "insufficient memory" in detail:
            return "Insufficient memory"
        if "insufficient cpu" in detail:
            return "Insufficient CPU"
        if "node affinity" in detail or "node selector" in detail:
            return "Node selector or affinity mismatch"
        if "taint" in detail:
            return "Untolerated node taint"
        return "Other scheduling constraint"

    def get_node_pressure_report(self) -> NodePressureReport:
        nodes_response = self.core_api.list_node(
            _request_timeout=self.request_timeout_seconds,
        )
        pods_response = self.core_api.list_pod_for_all_namespaces(
            _request_timeout=self.request_timeout_seconds,
        )
        raw_nodes = nodes_response.items
        raw_pods = pods_response.items

        nodes = [
            NodePressureStatus(
                name=node.metadata.name,
                ready=self._node_condition(node, "Ready"),
                memory_pressure=self._node_condition(
                    node, "MemoryPressure"
                ),
                disk_pressure=self._node_condition(node, "DiskPressure"),
                pid_pressure=self._node_condition(node, "PIDPressure"),
                network_unavailable=self._node_condition(
                    node, "NetworkUnavailable"
                ),
            )
            for node in raw_nodes
        ]

        pod_capacity = sum(
            int((node.status.allocatable or {}).get("pods", 0))
            for node in raw_nodes
        )
        active_pods = sum(
            1
            for pod in raw_pods
            if getattr(pod.status, "phase", None)
            not in {"Succeeded", "Failed"}
        )

        workflow_pending = [
            pod
            for pod in raw_pods
            if getattr(pod.metadata, "namespace", None) == self.namespace
            and (getattr(pod.metadata, "labels", None) or {}).get(
                self.WORKFLOW_LABEL
            )
            and getattr(pod.status, "phase", None) == "Pending"
            and not getattr(pod.spec, "node_name", None)
        ]
        scheduling_reasons: dict[str, int] = {}
        for pod in workflow_pending:
            reason = self._scheduling_reason(pod)
            scheduling_reasons[reason] = (
                scheduling_reasons.get(reason, 0) + 1
            )

        cpu_usage_percent = None
        memory_usage_percent = None
        metrics_nodes = 0
        try:
            metrics = client.CustomObjectsApi().list_cluster_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                plural="nodes",
                _request_timeout=self.request_timeout_seconds,
            )
            metrics_by_name = {
                item["metadata"]["name"]: item
                for item in metrics.get("items", [])
            }
            measured_nodes = [
                node
                for node in raw_nodes
                if node.metadata.name in metrics_by_name
            ]
            metrics_nodes = len(measured_nodes)

            if measured_nodes:
                cpu_capacity = sum(
                    float(
                        parse_quantity(
                            (node.status.allocatable or {}).get("cpu", "0")
                        )
                    )
                    for node in measured_nodes
                )
                memory_capacity = sum(
                    float(
                        parse_quantity(
                            (node.status.allocatable or {}).get(
                                "memory", "0"
                            )
                        )
                    )
                    for node in measured_nodes
                )
                cpu_usage = sum(
                    float(
                        parse_quantity(
                            metrics_by_name[node.metadata.name]["usage"][
                                "cpu"
                            ]
                        )
                    )
                    for node in measured_nodes
                )
                memory_usage = sum(
                    float(
                        parse_quantity(
                            metrics_by_name[node.metadata.name]["usage"][
                                "memory"
                            ]
                        )
                    )
                    for node in measured_nodes
                )
                if cpu_capacity:
                    cpu_usage_percent = cpu_usage / cpu_capacity * 100
                if memory_capacity:
                    memory_usage_percent = (
                        memory_usage / memory_capacity * 100
                    )
        except (ApiException, KeyError, TypeError, ValueError):
            pass

        return NodePressureReport(
            nodes=nodes,
            active_pods=active_pods,
            pod_capacity=pod_capacity,
            cpu_usage_percent=cpu_usage_percent,
            memory_usage_percent=memory_usage_percent,
            metrics_nodes=metrics_nodes,
            unschedulable_workflow_pods=len(workflow_pending),
            scheduling_reasons=scheduling_reasons,
        )

    def get_pod_logs(
        self,
        pod_name: str,
        tail_lines: int | None = None,
        container_name: str | None = None,
        since_seconds: int | None = None,
    ) -> str:
        effective_tail_lines = (
            tail_lines
            if tail_lines is not None
            else self.log_tail_lines
        )

        arguments: dict[str, Any] = {
            "name": pod_name,
            "namespace": self.namespace,
            "tail_lines": effective_tail_lines,
            "_request_timeout": self.request_timeout_seconds,
        }

        if container_name:
            arguments["container"] = container_name

        if since_seconds is not None:
            arguments["since_seconds"] = since_seconds

        try:
            logs = self.core_api.read_namespaced_pod_log(
                **arguments,
            )
        except ApiException as error:
            return (
                f"Could not read logs for {pod_name}: "
                f"{error.reason}"
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

    def _container_statuses(self, pod: Any) -> list[Any]:
        return [
            *(
                getattr(
                    pod.status,
                    "init_container_statuses",
                    None,
                )
                or []
            ),
            *(
                getattr(
                    pod.status,
                    "container_statuses",
                    None,
                )
                or []
            ),
        ]

    def _pod_event_time(self, pod: Any) -> datetime | None:
        event_times: list[datetime] = []

        start_time = getattr(pod.status, "start_time", None)
        if start_time is not None:
            event_times.append(start_time)

        for container_status in self._container_statuses(pod):
            state = getattr(container_status, "state", None)
            terminated = getattr(state, "terminated", None)

            if (
                terminated is not None
                and terminated.finished_at is not None
            ):
                event_times.append(terminated.finished_at)

        return max(event_times) if event_times else None

    def _pod_sort_key(self, pod: Any) -> datetime:
        return self._pod_event_time(pod) or datetime.min.replace(
            tzinfo=timezone.utc
        )

    def _container_problem(self, pod: Any) -> str | None:
        for container_status in self._container_statuses(pod):
            state = getattr(container_status, "state", None)
            waiting = getattr(state, "waiting", None)

            if (
                waiting is not None
                and waiting.reason in self.PROBLEM_WAITING_REASONS
            ):
                detail = waiting.reason or "unknown reason"

                if waiting.message:
                    message = " ".join(
                        waiting.message.split()
                    )
                    detail = f"{detail}: {message[:160]}"

                return (
                    f"{pod.metadata.name}/"
                    f"{container_status.name} is waiting: "
                    f"{detail}"
                )

        for container_status in self._container_statuses(pod):
            state = getattr(container_status, "state", None)
            terminated = getattr(state, "terminated", None)

            if (
                terminated is not None
                and terminated.exit_code != 0
            ):
                reason = terminated.reason or "Error"

                return (
                    f"{pod.metadata.name}/"
                    f"{container_status.name} terminated "
                    f"with {reason}, exit code "
                    f"{terminated.exit_code}"
                )

        return None

    def _extract_error_lines(
        self,
        logs: str,
        limit: int,
    ) -> list[str]:
        if logs.startswith("Could not read logs"):
            return []

        results: list[str] = []

        # Reverse traversal means the newest matching lines are
        # returned first.
        for raw_line in reversed(logs.splitlines()):
            line = " ".join(raw_line.strip().split())

            if not line:
                continue

            lowered = line.lower()

            if not any(
                keyword in lowered
                for keyword in self.ERROR_KEYWORDS
            ):
                continue

            if len(line) > 220:
                line = f"{line[:217]}..."

            if line not in results:
                results.append(line)

            if len(results) >= limit:
                break

        return results

    def get_recent_errors(
        self,
        limit: int = 3,
    ) -> list[str]:
        """Return up to the latest `limit` pod errors."""

        if limit <= 0:
            return []

        try:
            response = self.core_api.list_namespaced_pod(
                namespace=self.namespace,
                _request_timeout=self.request_timeout_seconds,
            )
        except ApiException as error:
            return [
                (
                    "Could not read pods from namespace "
                    f"{self.namespace}: {error.reason}"
                )
            ]

        errors: list[str] = []
        seen: set[str] = set()

        pods = sorted(
            response.items,
            key=self._pod_sort_key,
            reverse=True,
        )

        since_seconds = self.recent_error_minutes * 60

        def add_error(message: str) -> bool:
            if message not in seen:
                seen.add(message)
                errors.append(message)

            return len(errors) >= limit

        for pod in pods:
            labels = getattr(pod.metadata, "labels", None) or {}

            if not (
                labels.get(self.WORKFLOW_LABEL)
                or labels.get("pipeline_step")
            ):
                continue

            phase = pod.status.phase

            # Successful historical jobs are not current errors.
            if phase == "Succeeded":
                continue

            container_problem = self._container_problem(pod)

            if container_problem and add_error(container_problem):
                return errors

            statuses = self._container_statuses(pod)

            # A running pod with no status data is ignored rather
            # than producing a misleading log error.
            if phase == "Running" and not statuses:
                continue

            container_names = [
                status.name
                for status in statuses
                if getattr(status, "name", None)
            ]

            if not container_names:
                container_names = [None]

            found_log_error = False

            for container_name in container_names:
                logs = self.get_pod_logs(
                    pod_name=pod.metadata.name,
                    container_name=container_name,
                    since_seconds=since_seconds,
                )

                remaining = limit - len(errors)

                for log_error in self._extract_error_lines(
                    logs,
                    remaining,
                ):
                    found_log_error = True

                    source = pod.metadata.name
                    if container_name:
                        source = f"{source}/{container_name}"

                    if add_error(f"{source}: {log_error}"):
                        return errors

            if (
                phase == "Failed"
                and container_problem is None
                and not found_log_error
            ):
                if add_error(
                    f"{pod.metadata.name} is in phase Failed"
                ):
                    return errors

        return errors
