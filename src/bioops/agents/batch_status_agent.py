from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.argo_workflow_monitor import ArgoWorkflowMonitor


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = PROJECT_ROOT / "configs" / "agents.yaml"


class BatchStatusAgent(BaseAgent):
    """Batch Status Agent for tracking Argo-submitted batch workflows."""

    name = "batch_status"
    description = (
        "Tracks Argo batch workflow statuses, updates Google Sheet, "
        "and answers questions about batch processing status."
    )

    def __init__(self, config_path: Path = AGENTS_CONFIG_PATH) -> None:
        config = self._load_config(config_path)
        agents_config = config.get("agents", {})
        batch_config = agents_config.get("batch_status", {})
        submit_config = agents_config.get("submit_master", {})

        argo_namespace = batch_config.get(
            "argo_namespace",
            submit_config.get("argo_namespace", "argo"),
        )

        workflow_template_name = batch_config.get(
            "argo_workflow_template",
            submit_config.get("argo_workflow_template", "bioops-submit-master-local"),
        )

        self.monitor = ArgoWorkflowMonitor(
            namespace=argo_namespace,
            workflow_name_prefix=batch_config.get(
                "workflow_name_prefix",
                submit_config.get("workflow_name_prefix", "bioops-submit-master"),
            ),
            workflow_template_name=workflow_template_name,
            recent_workflow_limit=int(batch_config.get("recent_workflow_limit", 20)),
            step_patterns=submit_config.get("step_patterns"),
        )

    def run(self, message: str) -> str:
        lowered = message.lower()

        if self._is_sync_request(lowered):
            return self._sync_help()

        if self._is_batch_question(lowered):
            return self.monitor.render_latest_progress()

        return self._help()

    def _is_batch_question(self, lowered: str) -> bool:
        return any(
            term in lowered
            for term in (
                "batch",
                "batch status",
                "status of batch",
                "failed batch",
                "running batch",
            )
        )

    def _is_sync_request(self, lowered: str) -> bool:
        return "sync batch" in lowered or "update batch sheet" in lowered

    def _help(self) -> str:
        return (
            "Batch Status Agent\n\n"
            "Current MVP actions:\n"
            "- check latest batch status\n"
            "- show failed batch status\n"
            "- update batch sheet\n\n"
            "Next implementation step: connect Argo workflow rows to Google Sheet."
        )

    def _sync_help(self) -> str:
        return (
            "Batch status sync will scan Argo workflows and update Google Sheet.\n\n"
            "Planned command:\n"
            "python -m bioops.jobs.batch_status_sync"
        )

    def _load_config(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
