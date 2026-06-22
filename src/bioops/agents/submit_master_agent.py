from __future__ import annotations

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
    """Prepares original-compatible submit-master configs.

    Real submit-master launch is a later D2 step and must require confirmation.
    """

    name = "submit_master"
    description = "Prepares submit-master configs for launching pipeline jobs."

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

        reserved_keys = {
            "sample_id", "sample", "samples", "sample_ids", "tube", "tube_id",
            "batch_id", "batch",
            "pipeline", "pipeline_id",
            "step", "pipeline_step", "steps_order",
            "stage",
            "seq_type", "sequencer",
            "cluster", "cluster_name", "k8s_cluster_name",
            "mongo_cluster", "mongo_cluster_name",
            "namespace", "argo_namespace",
            "input_uri", "input",
            "output_uri", "output",
            "workflow_file", "workflow",
            "confirm",
            "wait",
            "only_good",
            "delay",
            "delay_step",
            "step_delay",
            "chunk_size",
        }

        extra_params = {
            key: value
            for key, value in values.items()
            if key not in reserved_keys
        }

        return SubmitRequest(
            sample_id=(
                values.get("sample_id")
                or values.get("sample")
                or values.get("samples")
                or values.get("sample_ids")
                or values.get("tube")
                or values.get("tube_id")
            ),
            batch_id=values.get("batch_id") or values.get("batch"),
            pipeline=values.get("pipeline") or values.get("pipeline_id") or "pipeline-v3.0",
            step=values.get("step") or values.get("pipeline_step"),
            steps_order=values.get("steps_order"),
            stage=values.get("stage"),
            seq_type=values.get("seq_type") or values.get("sequencer") or "illumina",
            cluster_name=(
                values.get("cluster_name")
                or values.get("cluster")
                or values.get("k8s_cluster_name")
            ),
            mongo_cluster_name=values.get("mongo_cluster_name") or values.get("mongo_cluster"),
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
                or "default"
            ),
            wait=self._parse_bool(values.get("wait"), default=True),
            only_good=self._parse_bool(values.get("only_good"), default=True),
            delay=self._parse_int(values.get("delay"), default=0),
            delay_step=self._parse_int(
                values.get("delay_step") or values.get("step_delay"),
                default=1,
            ),
            chunk_size=self._parse_int(values.get("chunk_size"), default=1),
            confirm=self._parse_bool(values.get("confirm"), default=False),
            extra_params=extra_params,
        )

    def _parse_key_value_pairs(self, message: str) -> dict[str, str]:
        pattern = r"(\w+)=([^\s]+)"
        matches = re.findall(pattern, message)
        return {key.lower(): value for key, value in matches}

    def _parse_bool(self, value: str | None, default: bool) -> bool:
        if value is None:
            return default

        return value.lower() in {"true", "yes", "1", "y"}

    def _parse_int(self, value: str | None, default: int) -> int:
        if value is None:
            return default

        try:
            return int(value)
        except ValueError:
            return default

    def _format_report(self, request: SubmitRequest, plan: SubmitPlan) -> str:
        lines = [
            "Submit Master Report",
            "",
            f"Status: {plan.status}",
            f"Workflow submitted: {plan.submit_result.submitted}",
            f"Workflow name: {plan.submit_result.workflow_name or 'not submitted'}",
            f"Workflow phase: {plan.submit_result.phase}",
            "",
            "Requested config:",
            f"- stage: {request.stage or 'not provided'}",
            f"- step/steps_order: {request.steps_order or request.step or 'not provided'}",
            f"- seq_type: {request.seq_type or 'not provided'}",
            f"- cluster_name: {request.cluster_name or 'not provided'}",
            f"- mongo_cluster_name: {request.mongo_cluster_name or 'not provided'}",
            f"- namespace: {request.namespace or 'default'}",
            f"- sample_id/sample_ids: {request.sample_id or 'not provided'}",
            f"- batch_id: {request.batch_id or 'not provided'}",
            f"- wait: {request.wait}",
            f"- only_good: {request.only_good}",
            f"- confirm: {request.confirm}",
            "",
            "Validation:",
        ]

        if plan.missing_fields:
            lines.append("- Missing or invalid fields:")
            lines.extend(f"  - {field}" for field in plan.missing_fields)
        else:
            lines.append("- Required fields are present.")

        lines.extend(
            [
                "",
                "Generated submit-master JSON config:",
                plan.config_preview,
                "",
                "Argo preview kept for later D2 compatibility:",
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

        lines.extend(
            [
                "",
                "No submit master was launched in this D1 slice.",
                "D2 launch will be added separately and must require confirm=true.",
            ]
        )

        return "\n".join(lines)
