from __future__ import annotations

import socket
import subprocess
import time
import webbrowser
from dataclasses import dataclass


@dataclass
class ArgoUiLaunchResult:
    opened: bool
    url: str
    message: str
    port_forward_started: bool = False


class ArgoUiLauncher:
    """
    Opens the local Argo Workflows UI.

    This does not submit workflows.
    It only takes the user to the Argo UI where they can submit
    the SubmitMaster WorkflowTemplate and fill parameters manually.
    """

    def __init__(
        self,
        namespace: str = "argo",
        service_name: str = "argo-server",
        local_port: int = 2746,
        remote_port: int = 2746,
        url: str | None = None,
        workflow_template_name: str = "bioops-submit-master-local",
    ) -> None:
        self.namespace = namespace
        self.service_name = service_name
        self.local_port = local_port
        self.remote_port = remote_port
        self.url = url or f"https://localhost:{local_port}"
        self.workflow_template_name = workflow_template_name

    def launch(self, start_port_forward: bool = False) -> ArgoUiLaunchResult:
        port_forward_started = False

        if start_port_forward and not self._is_port_open("127.0.0.1", self.local_port):
            self._start_port_forward()
            port_forward_started = True
            time.sleep(2)

        opened = webbrowser.open(self.url)

        message = (
            "Opening Argo UI for SubmitMaster.\n\n"
            f"URL: {self.url}\n\n"
            "In Argo UI, open:\n"
            f"Workflow Templates → {self.workflow_template_name} → Submit\n\n"
            "Fill the parameters and click Submit.\n"
        )

        if not start_port_forward:
            message += (
                "\nIf the UI is not reachable, run:\n"
                f"kubectl -n {self.namespace} port-forward "
                f"service/{self.service_name} {self.local_port}:{self.remote_port}\n"
            )

        return ArgoUiLaunchResult(
            opened=opened,
            url=self.url,
            message=message,
            port_forward_started=port_forward_started,
        )

    def _start_port_forward(self) -> subprocess.Popen:
        return subprocess.Popen(
            [
                "kubectl",
                "-n",
                self.namespace,
                "port-forward",
                f"service/{self.service_name}",
                f"{self.local_port}:{self.remote_port}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _is_port_open(self, host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((host, port)) == 0
