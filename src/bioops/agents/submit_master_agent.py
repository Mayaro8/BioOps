from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.jobs.submit_master_d4_failure_bitrix_report import render_failure_report
from bioops.tools.argo_ui_launcher import ArgoUiLauncher
from bioops.tools.argo_workflow_monitor import ArgoWorkflowMonitor
from bioops.tools.llm_action_router import (
    LLMActionRouter,
    format_action_routing_error,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = PROJECT_ROOT / "configs" / "agents.yaml"


class SubmitMasterAgent(BaseAgent):
    """SubmitMaster operations agent for Epic D."""

    name = "submit_master"
    description = (
        "Launches, monitors, reports, and provides safe retry instructions for "
        "Submit Master Argo workflows."
    )

    def __init__(
        self,
        config_path: Path = AGENTS_CONFIG_PATH,
        action_router: LLMActionRouter | None = None,
    ) -> None:
        config = self._load_config(config_path)
        agents_config = config.get("agents", {})
        submit_config = agents_config.get("submit_master", {})
        argo_namespace = submit_config.get("argo_namespace", "argo")
        workflow_template_name = submit_config.get(
            "argo_workflow_template",
            "bioops-submit-master-local",
        )

        self.launcher = ArgoUiLauncher(
            namespace=argo_namespace,
            service_name=submit_config.get("argo_service_name", "argo-server"),
            local_port=int(submit_config.get("argo_local_port", 2746)),
            remote_port=int(submit_config.get("argo_remote_port", 2746)),
            url=submit_config.get("argo_ui_url", "https://localhost:2746"),
            workflow_template_name=workflow_template_name,
        )
        self.monitor = ArgoWorkflowMonitor(
            namespace=argo_namespace,
            workflow_name_prefix=submit_config.get(
                "workflow_name_prefix",
                "bioops-submit-master",
            ),
            workflow_template_name=workflow_template_name,
            recent_workflow_limit=int(submit_config.get("recent_workflow_limit", 5)),
            step_patterns=submit_config.get("step_patterns"),
        )
        self.d4_namespace = argo_namespace
        self.d4_workflow_prefix = submit_config.get(
            "d4_workflow_prefix",
            submit_config.get("workflow_name_prefix", "bioops-submit-master"),
        )
        self.d4_workflow_template = submit_config.get(
            "d4_workflow_template",
            workflow_template_name,
        )
        self.d4_log_tail_lines = int(submit_config.get("d4_log_tail_lines", 80))
        self.action_router = action_router or self._build_action_router()

    def run(self, message: str) -> str:
        try:
            decision = self.action_router.route(message)
        except Exception as error:
            return format_action_routing_error("SubmitMaster Agent", error)

        if decision.action == "launch_ui":
            result = self.launcher.launch(start_port_forward=True)
            return result.message
        if decision.action == "failure_report":
            return render_failure_report(
                namespace=self.d4_namespace,
                workflow_prefix=self.d4_workflow_prefix,
                workflow_template=self.d4_workflow_template,
                log_tail_lines=self.d4_log_tail_lines,
            )
        if decision.action == "progress":
            return self.monitor.render_latest_progress()
        if decision.action == "retry_instructions":
            return self._d5_help()
        return self._help()

    @staticmethod
    def _build_action_router() -> LLMActionRouter:
        return LLMActionRouter(
            agent_name="SubmitMaster Agent",
            actions={
                "launch_ui": "Open or prepare access to the SubmitMaster Argo UI.",
                "progress": "Read the latest matching SubmitMaster workflow progress.",
                "failure_report": (
                    "Inspect the latest failed SubmitMaster workflow nodes and pod logs."
                ),
                "retry_instructions": (
                    "Explain the safe D5 retry command without creating a workflow."
                ),
                "help": "Explain the supported SubmitMaster actions.",
            },
            rules=[
                "Choose retry_instructions for every request to retry, restart, or resubmit.",
                "Never execute D5 retry from chat.",
                "Choose failure_report for failed-pod diagnosis or D4 requests.",
                "Choose progress for status, current step, bottleneck, DAG, or D3 requests.",
                "Choose launch_ui only when the user explicitly asks to open or launch the UI.",
            ],
            examples=[
                {
                    "request": "Where is SubmitMaster now?",
                    "action": "progress",
                    "parameters": {},
                    "reason": "The user asks for live workflow progress.",
                },
                {
                    "request": "Retry the failed SubmitMaster workflow",
                    "action": "retry_instructions",
                    "parameters": {},
                    "reason": "Chat must remain read-only for D5 retry.",
                },
            ],
        )

    def _help(self) -> str:
        return (
            "SubmitMaster Agent\n\n"
            "Supported actions:\n"
            "- Open the SubmitMaster Argo UI\n"
            "- Check latest workflow progress and bottlenecks\n"
            "- Diagnose failed workflow nodes and pod logs\n"
            "- Show safe D5 retry instructions\n\n"
            "Chat does not execute D5 retry."
        )

    def _d5_help(self) -> str:
        return (
            "SubmitMaster D5 safe retry is intentionally not executed from chat.\n\n"
            "Run:\n"
            "python -m bioops.jobs.submit_master_d5_retry_bitrix_report "
            "--auto-retry\n\n"
            "The standalone job classifies the failure, caps retry attempts, "
            "blocks duplicate active retries, and annotates the new workflow."
        )

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
