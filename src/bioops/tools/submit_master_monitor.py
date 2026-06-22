from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from bioops.tools.argo_tool import ArgoTool, ArgoWorkflowStatus
from bioops.tools.cost_tool import CostTool
from bioops.tools.eta_tool import ETATool
from bioops.tools.k8s_health import K8sHealthTool, PodStatus


@dataclass
class SubmitMasterMonitorRequest:
    batch_id: str | None = None
    argo_namespace: str = "argo"
    k8s_namespace: str = "bioops"


@dataclass
class SubmitMasterMonitorReport:
    status: str
    batch_id: str | None
    workflow_count: int
    running_workflows: int
    failed_workflows: int
    succeeded_workflows: int
    pod_count: int
    running_pods: int
    unhealthy_pods: int
    workflow_lines: list[str] = field(default_factory=list)
    pod_lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cost_line: str = ""
    eta_lines: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class SubmitMasterMonitor:
    """Read-only D3 monitor for Submit Master related workflows and pods."""

    def __init__(
        self,
        argo_tool: ArgoTool | None = None,
        k8s_tool_factory: Callable[[str], K8sHealthTool] | None = None,
        cost_tool: CostTool | None = None,
        eta_tool: ETATool | None = None,
    ):
        self.argo_tool = argo_tool or ArgoTool()
        self.k8s_tool_factory = k8s_tool_factory or (lambda namespace: K8sHealthTool(namespace=namespace))
        self.cost_tool = cost_tool or CostTool()
        self.eta_tool = eta_tool or ETATool()

    def monitor(self, request: SubmitMasterMonitorRequest) -> SubmitMasterMonitorReport:
        notes: list[str] = []
        errors: list[str] = []

        workflows = self._safe_get_workflows(
            namespace=request.argo_namespace,
            errors=errors,
        )
        workflows = self._filter_workflows_by_batch(workflows, request.batch_id)

        pods = self._safe_get_pods(
            namespace=request.k8s_namespace,
            errors=errors,
        )
        pods = self._filter_pods_by_batch(pods, request.batch_id)

        workflow_lines = [self._format_workflow(workflow) for workflow in workflows]
        pod_lines = [self._format_pod(pod) for pod in pods]

        failed_workflows = [workflow for workflow in workflows if workflow.phase in {"Failed", "Error"}]
        running_workflows = [workflow for workflow in workflows if workflow.phase in {"Running", "Pending"}]
        succeeded_workflows = [workflow for workflow in workflows if workflow.phase in {"Succeeded"}]

        unhealthy_pods = [pod for pod in pods if pod.phase not in {"Running", "Succeeded"}]
        running_pods = [pod for pod in pods if pod.phase == "Running"]

        for workflow in workflows:
            for failed_step in workflow.failed_steps:
                errors.append(
                    f"{workflow.name}/{failed_step.display_name}: "
                    f"{failed_step.phase} {failed_step.message}".strip()
                )

        for pod in unhealthy_pods:
            errors.append(f"{pod.name} is in phase {pod.phase}.")

        recent_errors = self._safe_get_recent_errors(
            namespace=request.k8s_namespace,
            errors=errors,
        )
        for error in recent_errors:
            if error != "No recent errors found.":
                errors.append(error)

        cost_line = self._estimate_cost_line(pods)
        eta_lines = self._estimate_eta_lines(running_pods)

        status = self._resolve_status(
            workflow_count=len(workflows),
            running_workflows=len(running_workflows),
            failed_workflows=len(failed_workflows),
            succeeded_workflows=len(succeeded_workflows),
            pod_count=len(pods),
            running_pods=len(running_pods),
            unhealthy_pods=len(unhealthy_pods),
            errors=errors,
        )

        if request.batch_id:
            notes.append("Workflow filtering uses workflow name and labels; pod filtering is best-effort by pod name.")
        else:
            notes.append("No batch_id provided; monitor summarizes all visible workflows/pods in configured namespaces.")

        return SubmitMasterMonitorReport(
            status=status,
            batch_id=request.batch_id,
            workflow_count=len(workflows),
            running_workflows=len(running_workflows),
            failed_workflows=len(failed_workflows),
            succeeded_workflows=len(succeeded_workflows),
            pod_count=len(pods),
            running_pods=len(running_pods),
            unhealthy_pods=len(unhealthy_pods),
            workflow_lines=workflow_lines,
            pod_lines=pod_lines,
            errors=errors or ["No monitor errors found."],
            cost_line=cost_line,
            eta_lines=eta_lines or ["ETA unavailable: no running pods with configured expected durations."],
            notes=notes,
        )

    def _safe_get_workflows(
        self,
        namespace: str,
        errors: list[str],
    ) -> list[ArgoWorkflowStatus]:
        try:
            return self.argo_tool.list_workflow_statuses(namespace=namespace)
        except Exception as exc:
            errors.append(f"Could not read Argo workflows from namespace {namespace}: {type(exc).__name__}: {exc}")
            return []

    def _safe_get_pods(
        self,
        namespace: str,
        errors: list[str],
    ) -> list[PodStatus]:
        try:
            return self.k8s_tool_factory(namespace).get_pods()
        except Exception as exc:
            errors.append(f"Could not read Kubernetes pods from namespace {namespace}: {type(exc).__name__}: {exc}")
            return []

    def _safe_get_recent_errors(
        self,
        namespace: str,
        errors: list[str],
    ) -> list[str]:
        try:
            return self.k8s_tool_factory(namespace).get_recent_errors()
        except Exception as exc:
            errors.append(f"Could not read Kubernetes logs/errors from namespace {namespace}: {type(exc).__name__}: {exc}")
            return []

    def _filter_workflows_by_batch(
        self,
        workflows: list[ArgoWorkflowStatus],
        batch_id: str | None,
    ) -> list[ArgoWorkflowStatus]:
        if not batch_id:
            return workflows

        return [
            workflow
            for workflow in workflows
            if self._workflow_matches_batch(workflow, batch_id)
        ]

    def _workflow_matches_batch(self, workflow: ArgoWorkflowStatus, batch_id: str) -> bool:
        haystack = [
            workflow.name,
            *[str(key) for key in workflow.labels.keys()],
            *[str(value) for value in workflow.labels.values()],
        ]
        return any(batch_id in item for item in haystack)

    def _filter_pods_by_batch(
        self,
        pods: list[PodStatus],
        batch_id: str | None,
    ) -> list[PodStatus]:
        if not batch_id:
            return pods

        return [
            pod
            for pod in pods
            if batch_id in pod.name
        ]

    def _format_workflow(self, workflow: ArgoWorkflowStatus) -> str:
        return (
            f"{workflow.name}: phase={workflow.phase}, "
            f"progress={workflow.progress or 'unknown'}, "
            f"running_steps={len(workflow.running_steps)}, "
            f"failed_steps={len(workflow.failed_steps)}"
        )

    def _format_pod(self, pod: PodStatus) -> str:
        return (
            f"{pod.name}: phase={pod.phase}, "
            f"step={pod.pipeline_step or 'unknown'}, "
            f"node={pod.node_name or 'unknown'}, "
            f"runtime_min={pod.runtime_minutes if pod.runtime_minutes is not None else 'unknown'}"
        )

    def _estimate_cost_line(self, pods: list[PodStatus]) -> str:
        max_runtime = max(
            [pod.runtime_minutes or 0.0 for pod in pods],
            default=0.0,
        )
        cost = self.cost_tool.estimate_cluster_cost(runtime_minutes=max_runtime)
        return (
            f"{cost.total_cost_usd:.4f} {cost.currency} "
            f"({cost.mode}; {cost.note})"
        )

    def _estimate_eta_lines(self, running_pods: list[PodStatus]) -> list[str]:
        eta_reports = self.eta_tool.estimate_for_running_pods(running_pods)

        lines: list[str] = []
        for eta in eta_reports:
            if eta.remaining_minutes is None:
                lines.append(f"{eta.pod_name}: ETA unavailable ({eta.source})")
            else:
                lines.append(
                    f"{eta.pod_name}: ~{eta.remaining_minutes} min remaining "
                    f"for {eta.pipeline_step}"
                )

        return lines

    def _resolve_status(
        self,
        workflow_count: int,
        running_workflows: int,
        failed_workflows: int,
        succeeded_workflows: int,
        pod_count: int,
        running_pods: int,
        unhealthy_pods: int,
        errors: list[str],
    ) -> str:
        real_errors = [error for error in errors if error != "No recent errors found."]

        if failed_workflows or unhealthy_pods or real_errors:
            return "failed_or_unhealthy"

        if running_workflows or running_pods:
            return "running"

        if workflow_count and succeeded_workflows == workflow_count:
            return "completed"

        if workflow_count == 0 and pod_count == 0:
            return "no_active_work"

        return "unknown"
