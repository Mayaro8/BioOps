from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.jobs.submit_master_d4_failure_bitrix_report import (
    render_failure_report,
)
from bioops.jobs.submit_master_d5_retry_bitrix_report import (
    assess_workflow_retry,
    render_d5_report,
)
from bioops.tools.argo_ui_launcher import ArgoUiLauncher
from bioops.tools.llm_action_router import (
    LLMActionRouter,
    format_action_routing_error,
)
from bioops.tools.submit_master_scope import (
    SubmitMasterScopeMonitor,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "agents.yaml"
)


class SubmitMasterAgent(BaseAgent):
    """SubmitMaster operations agent for Epic D."""

    name = "submit_master"
    description = (
        "Reports explicit batch, sample, and workflow "
        "status and performs confirmed targeted retries."
    )

    def __init__(
        self,
        config_path: Path = AGENTS_CONFIG_PATH,
        action_router: LLMActionRouter | None = None,
    ) -> None:
        config = self._load_config(config_path)
        submit = (
            config.get("agents", {})
            .get("submit_master", {})
        )

        namespace = submit.get(
            "argo_namespace",
            "argo",
        )
        template = submit.get(
            "argo_workflow_template",
            "bioops-submit-master-local",
        )
        prefix = submit.get(
            "workflow_name_prefix",
            "bioops-submit-master",
        )

        self.launcher = ArgoUiLauncher(
            namespace=namespace,
            service_name=submit.get(
                "argo_service_name",
                "argo-server",
            ),
            local_port=int(
                submit.get("argo_local_port", 2746)
            ),
            remote_port=int(
                submit.get("argo_remote_port", 2746)
            ),
            url=submit.get(
                "argo_ui_url",
                "https://localhost:2746",
            ),
            workflow_template_name=template,
        )

        self.monitor = SubmitMasterScopeMonitor(
            namespace=namespace,
            workflow_name_prefix=prefix,
            workflow_template_name=template,
            step_patterns=submit.get("step_patterns"),
            batch_label=submit.get(
                "batch_label",
                "bioops.dev/batch-id",
            ),
            sample_label=submit.get(
                "sample_label",
                "bioops.dev/sample-id",
            ),
            workflow_page_size=int(
                submit.get("workflow_page_size", 100)
            ),
            pod_page_size=int(
                submit.get("pod_page_size", 200)
            ),
            max_listed_items=int(
                submit.get("max_listed_items", 10)
            ),
        )

        self.d4_namespace = namespace
        self.d4_workflow_prefix = submit.get(
            "d4_workflow_prefix",
            prefix,
        )
        self.d4_workflow_template = submit.get(
            "d4_workflow_template",
            template,
        )
        self.d4_log_tail_lines = int(
            submit.get("d4_log_tail_lines", 80)
        )
        self.d5_max_retries = int(
            submit.get("d5_max_retries", 2)
        )

        self.action_router = (
            action_router
            or self._build_action_router()
        )

    def run(self, message: str) -> str:
        try:
            decision = self.action_router.route(message)
        except Exception as error:
            return format_action_routing_error(
                "SubmitMaster Agent",
                error,
            )

        parameters = decision.parameters

        if decision.action == "launch_ui":
            result = self.launcher.launch(
                start_port_forward=True
            )
            return result.message

        if decision.action == "batch_status":
            batch_id = self._parameter(
                parameters,
                "batch_id",
            )

            if not batch_id:
                return (
                    "SubmitMaster batch status requires "
                    "an explicit batch_id."
                )

            return self.monitor.render_batch_status(
                batch_id
            )

        if decision.action == "sample_status":
            sample_id = self._parameter(
                parameters,
                "sample_id",
            )

            if not sample_id:
                return (
                    "SubmitMaster sample status requires "
                    "an explicit sample_id."
                )

            return self.monitor.render_sample_status(
                sample_id=sample_id,
                batch_id=self._parameter(
                    parameters,
                    "batch_id",
                ),
            )

        if decision.action == "workflow_status":
            workflow_name = self._parameter(
                parameters,
                "workflow_name",
            )

            if not workflow_name:
                return (
                    "SubmitMaster workflow status requires "
                    "an explicit workflow_name."
                )

            return self.monitor.render_workflow_status(
                workflow_name
            )

        if decision.action == "latest_progress":
            return self.monitor.render_latest_progress()

        if decision.action == "failure_report":
            workflow_name = self._selected_workflow(
                parameters
            )

            if workflow_name.startswith("ERROR: "):
                return workflow_name.removeprefix(
                    "ERROR: "
                )

            return render_failure_report(
                namespace=self.d4_namespace,
                workflow_prefix=(
                    self.d4_workflow_prefix
                ),
                workflow_template=(
                    self.d4_workflow_template
                ),
                log_tail_lines=(
                    self.d4_log_tail_lines
                ),
                workflow_name=workflow_name,
            )

        if decision.action == "retry_sample":
            return self._retry_sample(
                message,
                parameters,
            )

        return self._help()

    def _retry_sample(
        self,
        message: str,
        parameters: dict[str, Any],
    ) -> str:
        workflow_name = self._selected_workflow(
            parameters
        )

        if workflow_name.startswith("ERROR: "):
            return workflow_name.removeprefix(
                "ERROR: "
            )

        confirmation = (
            f"CONFIRM RETRY {workflow_name}"
        )

        if message.strip() == confirmation:
            return render_d5_report(
                namespace=self.d4_namespace,
                workflow_prefix=(
                    self.d4_workflow_prefix
                ),
                workflow_template=(
                    self.d4_workflow_template
                ),
                auto_retry=True,
                max_retries=self.d5_max_retries,
                force_retry=False,
                workflow_name=workflow_name,
            )

        try:
            retryable, reason = assess_workflow_retry(
                namespace=self.d4_namespace,
                workflow_name=workflow_name,
            )
        except Exception as error:
            return (
                "SubmitMaster D5 assessment failed."
                "\n\n"
                f"Workflow: {workflow_name}\n"
                f"Reason: {error}\n"
                "No retry was created."
            )

        report = [
            "SubmitMaster D5 Targeted Retry Assessment",
            "",
            f"Workflow: {workflow_name}",
            (
                "Retryable: yes"
                if retryable
                else "Retryable: no"
            ),
            f"Decision: {reason}",
            "No retry was created.",
        ]

        if retryable:
            report.extend([
                "",
                "Send exactly to retry:",
                confirmation,
            ])

        return "\n".join(report)

    def _selected_workflow(
        self,
        parameters: dict[str, Any],
    ) -> str:
        workflow_name = self._parameter(
            parameters,
            "workflow_name",
        )

        if workflow_name:
            return workflow_name

        sample_id = self._parameter(
            parameters,
            "sample_id",
        )

        if not sample_id:
            return (
                "ERROR: Select an explicit "
                "workflow_name or sample_id before "
                "D4/D5. No workflow was changed."
            )

        try:
            workflow = (
                self.monitor.resolve_sample_workflow(
                    sample_id=sample_id,
                    batch_id=self._parameter(
                        parameters,
                        "batch_id",
                    ),
                )
            )
        except Exception as error:
            return f"ERROR: {error}"

        result = str(
            workflow.get("metadata", {}).get(
                "name",
                "",
            )
        )

        if not result:
            return (
                "ERROR: Selected workflow has no "
                "metadata.name."
            )

        return result

    @staticmethod
    def _build_action_router() -> LLMActionRouter:
        return LLMActionRouter(
            agent_name="SubmitMaster Agent",
            actions={
                "launch_ui": (
                    "Open the SubmitMaster Argo UI."
                ),
                "batch_status": (
                    "Aggregate one explicit batch."
                ),
                "sample_status": (
                    "Report one sample and its pods."
                ),
                "workflow_status": (
                    "Report one explicit workflow."
                ),
                "latest_progress": (
                    "Read latest only when explicitly "
                    "requested."
                ),
                "failure_report": (
                    "Diagnose one selected workflow "
                    "or sample."
                ),
                "retry_sample": (
                    "Assess or confirm one targeted "
                    "sample retry."
                ),
                "help": "Explain supported actions.",
            },
            parameter_schema={
                "batch_id": (
                    "Exact batch ID from the request "
                    "or null."
                ),
                "sample_id": (
                    "Exact sample ID from the request "
                    "or null."
                ),
                "workflow_name": (
                    "Exact workflow name from the "
                    "request or null."
                ),
            },
            rules=[
                (
                    "Choose retry_sample for retry, "
                    "restart, or resubmit requests."
                ),
                (
                    "Choose batch_status when batch_id "
                    "is supplied for status or D3."
                ),
                (
                    "Choose sample_status when "
                    "sample_id is supplied for status."
                ),
                (
                    "Choose workflow_status when "
                    "workflow_name is supplied."
                ),
                (
                    "Choose failure_report for D4 only "
                    "when a sample or workflow is "
                    "selected."
                ),
                (
                    "Choose latest_progress only when "
                    "the user explicitly says latest."
                ),
                "Never invent identifiers.",
            ],
            examples=[
                {
                    "request": (
                        "Show batch B104 progress"
                    ),
                    "action": "batch_status",
                    "parameters": {
                        "batch_id": "B104",
                        "sample_id": None,
                        "workflow_name": None,
                    },
                    "reason": (
                        "An explicit batch was selected."
                    ),
                },
                {
                    "request": (
                        "Show sample S927 in batch B104"
                    ),
                    "action": "sample_status",
                    "parameters": {
                        "batch_id": "B104",
                        "sample_id": "S927",
                        "workflow_name": None,
                    },
                    "reason": (
                        "An explicit sample was selected."
                    ),
                },
                {
                    "request": (
                        "Retry sample S927 in batch B104"
                    ),
                    "action": "retry_sample",
                    "parameters": {
                        "batch_id": "B104",
                        "sample_id": "S927",
                        "workflow_name": None,
                    },
                    "reason": (
                        "Assess one sample before retry."
                    ),
                },
            ],
        )

    @staticmethod
    def _parameter(
        parameters: dict[str, Any],
        name: str,
    ) -> str | None:
        value = parameters.get(name)

        if not isinstance(value, str):
            return None

        return value.strip() or None

    @staticmethod
    def _help() -> str:
        return (
            "SubmitMaster Agent\n\n"
            "- Check an explicit batch, sample, "
            "or workflow\n"
            "- Aggregate counts, percentages, "
            "and runtime statistics\n"
            "- Diagnose selected failures\n"
            "- Assess and explicitly confirm "
            "a targeted retry"
        )

    @staticmethod
    def _load_config(
        path: Path,
    ) -> dict[str, Any]:
        if not path.exists():
            return {}

        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return yaml.safe_load(handle) or {}
