from __future__ import annotations

import logging
import re
from pathlib import PurePosixPath
from typing import Any

from kubernetes import client, config


logger = logging.getLogger(__name__)
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


def normalize_config_path(value: str, mount_root: str = "/mnt/pipeline-v3.0") -> str:
    """Return a safe config path relative to the Submit Master PVC mount."""
    cleaned = value.strip().replace("\\", "/")
    root = PurePosixPath(mount_root)
    path = PurePosixPath(cleaned)

    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError as error:
            raise ValueError(f"config_path must be under {root}") from error

    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("config_path must be a non-empty path without traversal")
    if path.suffix.lower() != ".json":
        raise ValueError("config_path must point to a JSON file")

    return path.as_posix()


class SubmitMasterWorkflowLauncher:
    """Submit the real Submit Master WorkflowTemplate through the Argo CRD."""

    def __init__(self, namespace: str, template_name: str) -> None:
        self.namespace = namespace
        self.template_name = template_name

    def launch(self, *, config_path: str, batch_id: str | None = None) -> str:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        labels = {"bioops.dev/workload": "submit-master"}
        if batch_id:
            labels["bioops.dev/batch-id"] = batch_id

        body: dict[str, Any] = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Workflow",
            "metadata": {
                "generateName": "bioops-submit-master-",
                "namespace": self.namespace,
                "labels": labels,
            },
            "spec": {
                "workflowTemplateRef": {"name": self.template_name},
                "arguments": {
                    "parameters": [{"name": "config_path", "value": config_path}]
                },
            },
        }

        logger.info(
            "Submitting SubmitMaster namespace=%s template=%s config_path=%s batch_id=%s",
            self.namespace,
            self.template_name,
            config_path,
            batch_id or "unknown",
        )
        created = client.CustomObjectsApi().create_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=self.namespace,
            plural="workflows",
            body=body,
        )
        workflow_name = created.get("metadata", {}).get("name", "unknown")
        logger.info(
            "Submitted SubmitMaster namespace=%s workflow=%s",
            self.namespace,
            workflow_name,
        )
        return "\n".join([
            "SubmitMaster Launch",
            "",
            f"Workflow: {workflow_name}",
            f"Template: {self.template_name}",
            f"Config: {config_path}",
            "Status: submitted",
        ])

    def launch_mock(
        self,
        *,
        batch_id: str,
        input_prefix: str,
        stage: str,
    ) -> str:
        for name, value in {"batch_id": batch_id}.items():
            if not IDENTIFIER.fullmatch(value):
                raise ValueError(f"{name} is invalid")
        if stage not in {"all", "1", "2", "3"}:
            raise ValueError("stage must be all, 1, 2, or 3")
        if not input_prefix.startswith("/mock-data/"):
            raise ValueError("input_prefix must be under /mock-data/")
        if "\n" in input_prefix or "\r" in input_prefix or ".." in input_prefix.split("/"):
            raise ValueError("input_prefix is invalid")

        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        parameters = {
            "batch_id": batch_id,
            "input_prefix": input_prefix,
            "stage": stage,
        }
        body = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Workflow",
            "metadata": {
                "generateName": "bioops-fastq-mock-",
                "namespace": self.namespace,
                "labels": {
                    "bioops.dev/workload": "submit-master",
                    "bioops.dev/batch-id": batch_id,
                },
            },
            "spec": {
                "workflowTemplateRef": {"name": self.template_name},
                "arguments": {"parameters": [
                    {"name": name, "value": value}
                    for name, value in parameters.items()
                ]},
            },
        }
        created = client.CustomObjectsApi().create_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=self.namespace,
            plural="workflows",
            body=body,
        )
        workflow = created.get("metadata", {}).get("name", "unknown")
        logger.info("Submitted mock FASTQ pipeline workflow=%s batch_id=%s", workflow, batch_id)
        return "\n".join([
            "SubmitMaster Mock Launch",
            "",
            f"Workflow: {workflow}",
            f"Batch: {batch_id}",
            f"Input prefix: {input_prefix}",
            f"Stage: {stage}",
            "Status: submitted",
        ])
