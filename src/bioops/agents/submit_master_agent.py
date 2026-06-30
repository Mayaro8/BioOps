from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.argo_ui_launcher import ArgoUiLauncher
from bioops.tools.argo_workflow_monitor import ArgoWorkflowMonitor

PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = PROJECT_ROOT / "configs" / "agents.yaml"


class SubmitMasterAgent(BaseAgent):
    """SubmitMaster agent.

    D1: open Argo UI for SubmitMaster.
    D3: summarize SubmitMaster workflow progress without duplicating pod health.
    """

    name = "submit_master"
    description = (
        "Opens the Argo UI for launching SubmitMaster and reports "
        "workflow-level SubmitMaster progress."
    )

    def __init__(self, config_path: Path = AGENTS_CONFIG_PATH) -> None:
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

    def run(self, message: str) -> str:
        lowered = message.lower()

        if self._is_launch_request(lowered):
            result = self.launcher.launch(start_port_forward=True)
            return result.message

        if self._is_progress_request(lowered):
            return self.monitor.render_latest_progress()

        return (
            "SubmitMaster supports two actions:\n\n"
            "1. Launch UI:\n"
            "- launch submit master\n"
            "- open argo ui\n\n"
            "2. Check workflow progress:\n"
            "- submit master status\n"
            "- where is submit master\n"
            "- submit master progress\n"
            "- show failed submit master samples\n\n"
            "For raw pod health, use ClusterHealthAgent."
        )

    def _is_launch_request(self, lowered: str) -> bool:
        return (
            "launch submit master" in lowered
            or "open submit master" in lowered
            or "submit master ui" in lowered
            or "open argo" in lowered
            or "argo ui" in lowered
        )

    def _is_progress_request(self, lowered: str) -> bool:
        progress_terms = (
            "status",
            "progress",
            "where",
            "failed",
            "failure",
            "bottleneck",
            "workflow",
            "dag",
            "current step",
        )

        return "submit master" in lowered and any(term in lowered for term in progress_terms)

    def _load_config(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
