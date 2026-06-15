import re
from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.argo_tool import ArgoTool
from bioops.tools.submit_master_tool import (
    SubmitMasterTool,
    SubmitRequest,
    SubmitPlan,
)


class SubmitMasterAgent(BaseAgent):
    """
    Prepares and optionally submits Argo workflow plans.

    Real workflow submission only happens with confirm=true.
    """

    name = "submit_master"
    description = "Prepares and optionally submits Argo workflows for pipeline jobs."

    def __init__(
        self,
        submit_tool: SubmitMasterTool | None = None,
        config_path: str = "configs/agents.yaml",
    ):
        self.config = self._load_config(config_path)
        self.submit_config = self.config.get("agents", {}).get("submit_master", {})

        argo_tool = ArgoTool(
            namespace=self.submit_config.get("argo_namespace"),
            workflow_file=self.submit_config.get("workflow_file"),
        )

        self.submit_tool = submit_tool or SubmitMasterTool(argo_tool=argo_tool)

    def run(self, message: str) -> str:
        request = self._parse_message(message)
        plan = self.submit_tool.build_plan(request)
        return self._format_report(request, plan)

    def _load_config(self, config_path: str) -> dict[str, Any]:
        path = Path(config_path)

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def _parse_message(self, message: str) -> SubmitRequest:
        values = self._parse_key_value_pairs(message)

        confirm_value = values.get("confirm", "").lower()
        confirm = confirm_value in {"true", "yes", "1", "y"}

        return SubmitRequest(
            sample_id=(
                values.get("sample_id")
                or values.get("sample")
                or values.get("tube")
                or values.get("tube_id")
                or values.get("sample_ids")
            ),
            batch_id=values.get("batch_id") or values.get("batch"),
            pipeline=values.get("pipeline") or values.get("pipeline_id"),
            step=values.get("step") or values.get("pipeline_step"),
            input_uri=values.get("input_uri") or values.get("input"),
            output_uri=values.get("output_uri") or values.get("output"),
            workflow_file=(
                values.get("workflow_file")
                or values.get("workflow")
                or self.submit_config.get("workflow_file")
            ),
            namespace=(
                values.get("namespace")
                or values.get("argo_namespace")
                or self.submit_config.get("argo_namespace")
            ),
            confirm=confirm,
        )

    def _parse_key_value_pairs(self, message: str) -> dict[str, str]:
        pattern = r"(\w+)=([^\s]+)"
        matches = re.findall(pattern, message)
        return {key.lower(): value for key, value in matches}

    def _format_report(self, request: SubmitRequest, plan: SubmitPlan) -> str:
        lines = [
            "Submit Master Report",
            "",
            f"Status: {plan.status}",
            f"Workflow submitted: {plan.submit_result.submitted}",
            f"Workflow name: {plan.submit_result.workflow_name or 'not submitted'}",
            f"Workflow phase: {plan.submit_result.phase}",
            "",
            "Requested submission:",
            f"- sample_id: {request.sample_id or 'not provided'}",
            f"- batch_id: {request.batch_id or 'not provided'}",
            f"- pipeline: {request.pipeline or 'not provided'}",
            f"- step: {request.step or 'not provided'}",
            f"- input_uri: {request.input_uri or 'not provided'}",
            f"- output_uri: {request.output_uri or 'not provided'}",
            f"- confirm: {request.confirm}",
            "",
            "Validation:",
        ]

        if plan.missing_fields:
            lines.append("- Missing required fields:")
            lines.extend(f"  - {field}" for field in plan.missing_fields)
        else:
            lines.append("- Required fields are present.")

        lines.extend(
            [
                "",
                "Generated config preview:",
                plan.config_preview,
                "",
                "Argo submit command preview:",
                f"- Namespace: {plan.argo_preview.namespace}",
                f"- Workflow file: {plan.argo_preview.workflow_file or 'not configured'}",
                f"- Command: {plan.argo_preview.command}",
                "",
                "Submit result:",
                f"- Message: {plan.submit_result.message}",
            ]
        )

        if plan.submit_result.error:
            lines.append(f"- Error: {plan.submit_result.error}")

        if plan.argo_preview.missing_config:
            lines.extend(["", "Argo config issues:"])
            lines.extend(f"- {item}" for item in plan.argo_preview.missing_config)

        lines.extend(["", "Notes:"])
        lines.extend(f"- {item}" for item in plan.notes)

        if not request.confirm:
            lines.extend(
                [
                    "",
                    "No workflow was submitted.",
                    "To submit for real, rerun with confirm=true.",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "Submission was attempted because confirm=true was provided.",
                    "No GitHub actions were modified.",
                ]
            )

        return "\n".join(lines)
