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
    Simple SubmitMaster UI-launch agent.

    This agent does not build SubmitMaster JSON.
    This agent does not collect pipeline parameters.
    It opens the Argo UI so the user can submit the real SubmitMaster workflow.
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

        if (
            "launch submit master" not in lowered
            and "open submit master" not in lowered
            and "submit master ui" not in lowered
        ):
            return (
                "Use: launch submit master\n\n"
                "This opens the Argo UI. From there, submit the "
                "`bioops-submit-master-local` WorkflowTemplate."
            )

        start_port_forward = (
            "port-forward" in lowered
            or "port forward" in lowered
            or "--port-forward" in lowered
        )

        result = self.launcher.launch(start_port_forward=start_port_forward)
        return result.message

    def _load_config(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}