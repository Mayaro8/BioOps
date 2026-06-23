from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any

from bioops.tools.submit_master_failed_pods import (
    SubmitMasterFailedPodReporter,
    SubmitMasterFailedPodRequest,
)


@dataclass
class SubmitMasterRestartRequest:
    batch_id: str | None = None
    workflow_name: str | None = None
    argo_namespace: str = "argo"
    k8s_namespace: str = "bioops"
    confirm: bool = False


@dataclass
class RestartAttempt:
    workflow_name: str
    command: list[str] = field(default_factory=list)
    executed: bool = False
    success: bool = False
    message: str = ""
    stdout: str = ""
    stderr: str = ""


@dataclass
class SubmitMasterRestartResult:
    status: str
    requested_batch_id: str | None = None
    requested_workflow_name: str | None = None
    failed_pod_count: int = 0
    target_workflows: list[str] = field(default_factory=list)
    attempts: list[RestartAttempt] = field(default_factory=list)
    blocked_reason: str = ""
    message: str = ""


class SubmitMasterRestartTool:
    """
    D5 safe restart tool.

    This does not delete Kubernetes pods directly. Argo owns workflow pods, so
    the safe restart operation is an Argo workflow retry, gated by confirmation
    and YAML allow_restart.
    """

    def __init__(
        self,
        failed_pod_reporter: SubmitMasterFailedPodReporter,
        allow_restart: bool = False,
        argo_command: str = "argo",
        command_runner: Any | None = None,
    ):
        self.failed_pod_reporter = failed_pod_reporter
        self.allow_restart = allow_restart
        self.argo_command = argo_command
        self.command_runner = command_runner or subprocess.run

    def restart(self, request: SubmitMasterRestartRequest) -> SubmitMasterRestartResult:
        failed_report = self.failed_pod_reporter.report(
            SubmitMasterFailedPodRequest(
                batch_id=request.batch_id,
                argo_namespace=request.argo_namespace,
                k8s_namespace=request.k8s_namespace,
            )
        )

        failed_pods = getattr(failed_report, "failed_pods", []) or []
        workflows = self._target_workflows(failed_pods, request.workflow_name)

        if not workflows:
            return SubmitMasterRestartResult(
                status="no_restart_targets",
                requested_batch_id=request.batch_id,
                requested_workflow_name=request.workflow_name,
                failed_pod_count=getattr(failed_report, "failed_pod_count", 0),
                target_workflows=[],
                message="No failed Argo workflow targets were found.",
            )

        attempts = [
            RestartAttempt(
                workflow_name=workflow,
                command=self._retry_command(workflow, request.argo_namespace),
                executed=False,
                success=False,
                message="Planned only. No restart was attempted.",
            )
            for workflow in workflows
        ]

        if not request.confirm:
            return SubmitMasterRestartResult(
                status="restart_confirmation_required",
                requested_batch_id=request.batch_id,
                requested_workflow_name=request.workflow_name,
                failed_pod_count=getattr(failed_report, "failed_pod_count", len(failed_pods)),
                target_workflows=workflows,
                attempts=attempts,
                blocked_reason="confirm=true is required before retrying failed Argo workflows.",
                message="Restart plan prepared. No workflow was retried.",
            )

        if not self.allow_restart:
            return SubmitMasterRestartResult(
                status="restart_blocked_by_config",
                requested_batch_id=request.batch_id,
                requested_workflow_name=request.workflow_name,
                failed_pod_count=getattr(failed_report, "failed_pod_count", len(failed_pods)),
                target_workflows=workflows,
                attempts=attempts,
                blocked_reason="agents.submit_master.allow_restart is false.",
                message="Restart was confirmed by the user but blocked by YAML safety config.",
            )

        executed_attempts = [
            self._execute_retry(workflow, request.argo_namespace)
            for workflow in workflows
        ]

        all_success = all(attempt.success for attempt in executed_attempts)
        return SubmitMasterRestartResult(
            status="restart_submitted" if all_success else "restart_partially_failed",
            requested_batch_id=request.batch_id,
            requested_workflow_name=request.workflow_name,
            failed_pod_count=getattr(failed_report, "failed_pod_count", len(failed_pods)),
            target_workflows=workflows,
            attempts=executed_attempts,
            message=(
                "Argo retry command submitted for all target workflows."
                if all_success
                else "At least one Argo retry command failed."
            ),
        )

    def _target_workflows(
        self,
        failed_pods: list[Any],
        requested_workflow_name: str | None,
    ) -> list[str]:
        workflows: list[str] = []

        if requested_workflow_name:
            workflows.append(requested_workflow_name)

        for pod in failed_pods:
            workflow_name = getattr(pod, "workflow_name", None)
            if workflow_name:
                workflows.append(str(workflow_name))

        unique: list[str] = []
        for workflow in workflows:
            if workflow and workflow not in unique:
                unique.append(workflow)

        return unique

    def _retry_command(self, workflow_name: str, namespace: str) -> list[str]:
        return [
            self.argo_command,
            "retry",
            workflow_name,
            "-n",
            namespace,
        ]

    def _execute_retry(self, workflow_name: str, namespace: str) -> RestartAttempt:
        command = self._retry_command(workflow_name, namespace)

        try:
            completed = self.command_runner(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            return RestartAttempt(
                workflow_name=workflow_name,
                command=command,
                executed=True,
                success=False,
                message=f"Argo command not found: {error}",
            )
        except Exception as error:
            return RestartAttempt(
                workflow_name=workflow_name,
                command=command,
                executed=True,
                success=False,
                message=f"Argo retry failed before completion: {type(error).__name__}: {error}",
            )

        return RestartAttempt(
            workflow_name=workflow_name,
            command=command,
            executed=True,
            success=completed.returncode == 0,
            message=(
                "Argo retry command succeeded."
                if completed.returncode == 0
                else f"Argo retry command failed with return code {completed.returncode}."
            ),
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
