from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from bioops.tools.argo_tool import ArgoTool, ArgoWorkflowStatus
from bioops.tools.k8s_health import K8sHealthTool, PodStatus


FAILED_POD_PHASES = {"Failed", "Error", "Unknown", "CrashLoopBackOff", "ImagePullBackOff"}


@dataclass
class SubmitMasterFailedPodRequest:
    batch_id: str | None = None
    argo_namespace: str = "argo"
    k8s_namespace: str = "bioops"
    log_tail_lines: int = 80


@dataclass
class FailedPodDetail:
    pod_name: str
    namespace: str
    phase: str
    pipeline_step: str | None
    node_name: str | None
    runtime_minutes: float | None
    workflow_name: str | None = None
    argo_failed_steps: list[str] = field(default_factory=list)
    log_excerpt: str = ""
    error_lines: list[str] = field(default_factory=list)
    suggested_action: str = ""


@dataclass
class SubmitMasterFailedPodReport:
    status: str
    batch_id: str | None
    failed_pod_count: int
    failed_pods: list[FailedPodDetail]
    workflow_error_lines: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class SubmitMasterFailedPodReporter:
    """Read-only failed pod reporter for Submit Master D4."""

    def __init__(
        self,
        argo_tool: ArgoTool | None = None,
        k8s_tool_factory: Callable[[str], K8sHealthTool] | None = None,
    ):
        self.argo_tool = argo_tool or ArgoTool()
        self.k8s_tool_factory = k8s_tool_factory or (lambda namespace: K8sHealthTool(namespace=namespace))

    def report(self, request: SubmitMasterFailedPodRequest) -> SubmitMasterFailedPodReport:
        notes: list[str] = []
        workflow_error_lines: list[str] = []

        workflows = self._safe_get_workflows(
            namespace=request.argo_namespace,
            workflow_error_lines=workflow_error_lines,
        )
        workflows = self._filter_workflows_by_batch(workflows, request.batch_id)

        k8s_tool = self.k8s_tool_factory(request.k8s_namespace)
        pods = self._safe_get_pods(k8s_tool, workflow_error_lines)
        pods = self._filter_pods_by_batch(pods, request.batch_id)

        failed_pods = [
            pod
            for pod in pods
            if self._is_failed_or_unhealthy(pod)
        ]

        details: list[FailedPodDetail] = []
        for pod in failed_pods:
            logs = self._safe_get_pod_logs(
                k8s_tool=k8s_tool,
                pod_name=pod.name,
                tail_lines=request.log_tail_lines,
            )
            error_lines = self._extract_error_lines(logs)
            workflow = self._match_workflow_for_pod(pod, workflows)
            argo_failed_steps = self._format_failed_steps(workflow)

            details.append(
                FailedPodDetail(
                    pod_name=pod.name,
                    namespace=pod.namespace,
                    phase=pod.phase,
                    pipeline_step=pod.pipeline_step,
                    node_name=pod.node_name,
                    runtime_minutes=pod.runtime_minutes,
                    workflow_name=workflow.name if workflow else None,
                    argo_failed_steps=argo_failed_steps,
                    log_excerpt=self._trim_logs(logs),
                    error_lines=error_lines,
                    suggested_action=self._suggest_action(pod, error_lines, argo_failed_steps),
                )
            )

        if request.batch_id:
            notes.append("Batch filtering is best-effort using pod names plus workflow names/labels.")
        else:
            notes.append("No batch_id provided; report includes all failed/unhealthy visible pods.")

        status = "failed_pods_found" if details else "no_failed_pods_found"

        return SubmitMasterFailedPodReport(
            status=status,
            batch_id=request.batch_id,
            failed_pod_count=len(details),
            failed_pods=details,
            workflow_error_lines=workflow_error_lines or ["No workflow read errors found."],
            notes=notes,
        )

    def _safe_get_workflows(
        self,
        namespace: str,
        workflow_error_lines: list[str],
    ) -> list[ArgoWorkflowStatus]:
        try:
            return self.argo_tool.list_workflow_statuses(namespace=namespace)
        except Exception as exc:
            workflow_error_lines.append(
                f"Could not read Argo workflows from namespace {namespace}: "
                f"{type(exc).__name__}: {exc}"
            )
            return []

    def _safe_get_pods(
        self,
        k8s_tool: K8sHealthTool,
        workflow_error_lines: list[str],
    ) -> list[PodStatus]:
        try:
            return k8s_tool.get_pods()
        except Exception as exc:
            workflow_error_lines.append(
                f"Could not read Kubernetes pods: {type(exc).__name__}: {exc}"
            )
            return []

    def _safe_get_pod_logs(
        self,
        k8s_tool: K8sHealthTool,
        pod_name: str,
        tail_lines: int,
    ) -> str:
        try:
            return k8s_tool.get_pod_logs(pod_name=pod_name, tail_lines=tail_lines)
        except Exception as exc:
            return f"Could not read logs for {pod_name}: {type(exc).__name__}: {exc}"

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

        return [pod for pod in pods if batch_id in pod.name]

    def _is_failed_or_unhealthy(self, pod: PodStatus) -> bool:
        if pod.phase in {"Running", "Succeeded"}:
            return False

        return True

    def _match_workflow_for_pod(
        self,
        pod: PodStatus,
        workflows: list[ArgoWorkflowStatus],
    ) -> ArgoWorkflowStatus | None:
        for workflow in workflows:
            if workflow.name and workflow.name in pod.name:
                return workflow

            if pod.pipeline_step:
                for failed_step in workflow.failed_steps:
                    if pod.pipeline_step in {
                        failed_step.display_name,
                        failed_step.template_name,
                        failed_step.name,
                    }:
                        return workflow

        return None

    def _format_failed_steps(self, workflow: ArgoWorkflowStatus | None) -> list[str]:
        if workflow is None:
            return []

        lines: list[str] = []
        for step in workflow.failed_steps:
            lines.append(
                f"{step.display_name}: phase={step.phase}, "
                f"template={step.template_name or 'unknown'}, "
                f"message={step.message or 'no message'}"
            )

        return lines

    def _extract_error_lines(self, logs: str) -> list[str]:
        keywords = [
            "error",
            "failed",
            "failure",
            "exception",
            "traceback",
            "oomkilled",
            "killed",
            "cannot",
            "denied",
            "exit code",
        ]

        suspicious: list[str] = []
        for line in logs.splitlines():
            lowered = line.lower()
            if any(keyword in lowered for keyword in keywords):
                suspicious.append(line.strip())

        return suspicious[:8]

    def _trim_logs(self, logs: str, max_chars: int = 1200) -> str:
        logs = logs.strip()
        if len(logs) <= max_chars:
            return logs

        return logs[-max_chars:]

    def _suggest_action(
        self,
        pod: PodStatus,
        error_lines: list[str],
        argo_failed_steps: list[str],
    ) -> str:
        combined = "\n".join(error_lines + argo_failed_steps).lower()

        if "oomkilled" in combined or "out of memory" in combined:
            return "Likely memory issue. Check RAM request/limit and consider rerun with higher memory."

        if "imagepullbackoff" in pod.phase.lower() or "image pull" in combined:
            return "Likely image pull issue. Check image tag, registry access, and image pull secrets."

        if "permission denied" in combined or "denied" in combined:
            return "Likely permission/access issue. Check service account, mounted secrets, and object storage permissions."

        if "no such file" in combined or "not found" in combined or "cannot" in combined:
            return "Likely missing input/path issue. Check generated submit-master config paths and sample IDs."

        return "Inspect the log excerpt and Argo failed steps, then rerun/restart only after confirming the root cause."
