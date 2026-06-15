import re
from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.argo_tool import ArgoTool, ArgoWorkflowStatus
from bioops.tools.batch_status_tool import (
    BatchStatusRequest,
    BatchStatusResult,
    BatchStatusTool,
)


class BatchStatusAgent(BaseAgent):
    """
    Reports batch/workflow status from Argo Workflows.
    """

    name = "batch_status"
    description = "Reports Argo workflow and batch status."

    def __init__(
        self,
        status_tool: BatchStatusTool | None = None,
        config_path: str = "configs/agents.yaml",
    ):
        self.config = self._load_config(config_path)
        self.batch_config = self.config.get("agents", {}).get("batch_status", {})

        argo_tool = ArgoTool(
            namespace=self.batch_config.get("argo_namespace"),
        )

        self.status_tool = status_tool or BatchStatusTool(argo_tool=argo_tool)

    def run(self, message: str) -> str:
        request = self._parse_message(message)
        result = self.status_tool.get_status(request)
        return self._format_report(request, result)

    def _load_config(self, config_path: str) -> dict[str, Any]:
        path = Path(config_path)

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def _parse_message(self, message: str) -> BatchStatusRequest:
        values = self._parse_key_value_pairs(message)

        return BatchStatusRequest(
            batch_id=values.get("batch_id") or values.get("batch"),
            sample_id=(
                values.get("sample_id")
                or values.get("sample")
                or values.get("tube")
                or values.get("tube_id")
            ),
            step=values.get("step") or values.get("pipeline_step"),
            workflow_name=(
                values.get("workflow")
                or values.get("workflow_name")
                or values.get("workflow_id")
            ),
            namespace=(
                values.get("namespace")
                or values.get("argo_namespace")
                or self.batch_config.get("argo_namespace")
            ),
        )

    def _parse_key_value_pairs(self, message: str) -> dict[str, str]:
        pattern = r"(\w+)=([^\s]+)"
        matches = re.findall(pattern, message)
        return {key.lower(): value for key, value in matches}

    def _format_report(
        self,
        request: BatchStatusRequest,
        result: BatchStatusResult,
    ) -> str:
        lines = [
            "Batch Status Report",
            "",
            f"Namespace: {result.namespace}",
            f"Message: {result.message}",
            "",
            "Filters:",
            f"- batch_id: {request.batch_id or 'not provided'}",
            f"- sample_id: {request.sample_id or 'not provided'}",
            f"- step: {request.step or 'not provided'}",
            f"- workflow: {request.workflow_name or 'not provided'}",
        ]

        if result.error:
            lines.extend(
                [
                    "",
                    "Error:",
                    f"- {result.error}",
                ]
            )
            return "\n".join(lines)

        if not result.workflows:
            lines.extend(
                [
                    "",
                    "No workflows matched the request.",
                ]
            )
            return "\n".join(lines)

        lines.extend(["", "Matching workflows:"])

        for workflow in result.workflows:
            lines.extend(self._format_workflow(workflow))

        return "\n".join(lines)

    def _format_workflow(self, workflow: ArgoWorkflowStatus) -> list[str]:
        lines = [
            "",
            f"- Workflow: {workflow.name}",
            f"  Phase: {workflow.phase}",
            f"  Progress: {workflow.progress or 'unavailable'}",
            f"  Started: {workflow.started_at or 'unknown'}",
            f"  Finished: {workflow.finished_at or 'not finished'}",
        ]

        if workflow.labels:
            label_text = ", ".join(
                f"{key}={value}" for key, value in workflow.labels.items()
            )
            lines.append(f"  Labels: {label_text}")

        if workflow.message:
            lines.append(f"  Message: {workflow.message}")

        if workflow.running_steps:
            lines.append("  Running/current steps:")
            for step in workflow.running_steps:
                lines.append(
                    f"    - {step.display_name} [{step.phase}]"
                )

        if workflow.failed_steps:
            lines.append("  Failed steps:")
            for step in workflow.failed_steps:
                message = f": {step.message}" if step.message else ""
                lines.append(
                    f"    - {step.display_name} [{step.phase}]{message}"
                )

        if not workflow.running_steps and not workflow.failed_steps:
            lines.append("  Running/current steps: none")
            lines.append("  Failed steps: none")

        return lines
