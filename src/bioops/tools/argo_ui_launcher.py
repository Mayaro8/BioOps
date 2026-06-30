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

    This tool starts a kubectl port-forward to the Argo server and then tries
    to open the UI URL. It does not submit workflows directly.
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

    def launch(self, start_port_forward: bool = True) -> ArgoUiLaunchResult:
        port_forward_started = False

        if start_port_forward:
            if self._is_port_open("127.0.0.1", self.local_port):
                port_status = (
                    f"Port {self.local_port} is already open, so I reused the "
                    "existing Argo UI tunnel."
                )
            else:
                self._start_port_forward()
                port_forward_started = True
                time.sleep(2)

                if self._is_port_open("127.0.0.1", self.local_port):
                    port_status = (
                        f"Started Argo UI port-forward on port {self.local_port}."
                    )
                else:
                    port_status = (
                        "Tried to start Argo UI port-forward, but the port did "
                        "not become reachable yet. Check Kubernetes/Argo status."
                    )
        else:
            port_status = "Port-forward was not requested."

        opened = webbrowser.open(self.url)

        message = (
            "Opening Argo UI for SubmitMaster.\n\n"
            f"{port_status}\n\n"
            f"URL: {self.url}\n\n"
            "In Argo UI, open:\n"
            f"Workflow Templates → {self.workflow_template_name} → Submit\n\n"
            "The workflow template now runs the local SubmitMaster MVP:\n"
            "Config Creator → generated JSON → SubmitMaster → downstream workflows.\n"
        )

        if not opened:
            message += (
                "\nI could not automatically open a browser from this environment.\n"
                f"Open this URL manually: {self.url}\n"
            )

        message += (
            "\nIf you are using VS Code Remote/SSH, make sure port "
            f"{self.local_port} is forwarded to your laptop."
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