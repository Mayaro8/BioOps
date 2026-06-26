from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.argo_ui_launcher import ArgoUiLauncher

PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = PROJECT_ROOT / "configs" / "agents.yaml"


class SubmitMasterAgent(BaseAgent):
    """
    SubmitMaster launcher agent.

    This agent opens the Argo UI for the local SubmitMaster WorkflowTemplate.
    By default, it also starts the Argo port-forward so the UI is reachable.
    """

    name = "submit_master"
    description = "Opens the Argo UI for launching the SubmitMaster workflow."

    def __init__(self, config_path: Path = AGENTS_CONFIG_PATH) -> None:
        config = self._load_config(config_path)
        agents_config = config.get("agents", {})
        submit_config = agents_config.get("submit_master", {})

        self.launcher = ArgoUiLauncher(
            namespace=submit_config.get("argo_namespace", "argo"),
            service_name=submit_config.get("argo_service_name", "argo-server"),
            local_port=int(submit_config.get("argo_local_port", 2746)),
            remote_port=int(submit_config.get("argo_remote_port", 2746)),
            url=submit_config.get("argo_ui_url", "https://localhost:2746"),
            workflow_template_name=submit_config.get(
                "argo_workflow_template",
                "bioops-submit-master-local",
            ),
        )

    def run(self, message: str) -> str:
        lowered = message.lower()

        valid_request = (
            "launch submit master" in lowered
            or "open submit master" in lowered
            or "submit master ui" in lowered
            or "open argo" in lowered
            or "argo ui" in lowered
        )

        if not valid_request:
            return (
                "Use: launch submit master\n\n"
                "This starts the Argo UI port-forward and opens the "
                "`bioops-submit-master-local` WorkflowTemplate page."
            )

        # New behavior:
        # Always start/check the Argo UI port-forward when launching SubmitMaster.
        result = self.launcher.launch(start_port_forward=True)
        return result.message

    def _load_config(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}