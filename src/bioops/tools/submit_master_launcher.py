from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from kubernetes import client, config


logger = logging.getLogger(__name__)
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
KUBE_CONTEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,252}$")
NAMESPACE = re.compile(
    r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$"
)


@dataclass(frozen=True)
class MockLaunchTarget:
    batch_id: str
    input_prefix: str
    stage: str = "all"
    cluster_context: str | None = None
    namespace: str | None = None


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

    @staticmethod
    def _custom_objects_api(
        cluster_context: str | None = None,
    ) -> Any:
        if cluster_context:
            api_client = config.new_client_from_config(
                context=cluster_context
            )
            return client.CustomObjectsApi(api_client)

        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        return client.CustomObjectsApi()

    def launch(self, *, config_path: str, batch_id: str | None = None) -> str:
        custom_api = self._custom_objects_api()

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
        created = custom_api.create_namespaced_custom_object(
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
        cluster_context: str | None = None,
        namespace: str | None = None,
    ) -> str:
        effective_namespace = namespace or self.namespace
        for name, value in {"batch_id": batch_id}.items():
            if not IDENTIFIER.fullmatch(value):
                raise ValueError(f"{name} is invalid")
        if cluster_context and not KUBE_CONTEXT.fullmatch(cluster_context):
            raise ValueError("cluster_context is invalid")
        if not NAMESPACE.fullmatch(effective_namespace):
            raise ValueError("namespace is invalid")
        if stage not in {"all", "1", "2", "3"}:
            raise ValueError("stage must be all, 1, 2, or 3")
        if not input_prefix.startswith("/mock-data/"):
            raise ValueError("input_prefix must be under /mock-data/")
        if "\n" in input_prefix or "\r" in input_prefix or ".." in input_prefix.split("/"):
            raise ValueError("input_prefix is invalid")

        custom_api = self._custom_objects_api(cluster_context)

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
                "namespace": effective_namespace,
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
        created = custom_api.create_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=effective_namespace,
            plural="workflows",
            body=body,
        )
        workflow = created.get("metadata", {}).get("name", "unknown")
        logger.info("Submitted mock FASTQ pipeline workflow=%s batch_id=%s", workflow, batch_id)
        return "\n".join([
            "SubmitMaster Mock Launch",
            "",
            f"Workflow: {workflow}",
            f"Cluster: {cluster_context or 'current'}",
            f"Namespace: {effective_namespace}",
            f"Batch: {batch_id}",
            f"Input prefix: {input_prefix}",
            f"Stage: {stage}",
            "Status: submitted",
        ])

    def launch_mock_many(
        self,
        targets: list[MockLaunchTarget],
    ) -> str:
        results: list[tuple[MockLaunchTarget, bool, str]] = []

        for target in targets:
            try:
                report = self.launch_mock(
                    batch_id=target.batch_id,
                    input_prefix=target.input_prefix,
                    stage=target.stage,
                    cluster_context=target.cluster_context,
                    namespace=target.namespace,
                )
                workflow = next(
                    (
                        line.removeprefix("Workflow: ")
                        for line in report.splitlines()
                        if line.startswith("Workflow: ")
                    ),
                    "unknown",
                )
                results.append((target, True, workflow))
            except Exception as error:
                results.append(
                    (
                        target,
                        False,
                        f"{type(error).__name__}: {error}",
                    )
                )

        submitted = sum(1 for _, success, _ in results if success)
        lines = [
            "SubmitMaster Multi-Cluster Launch",
            "",
            f"Targets requested: {len(results)}",
            f"Submitted: {submitted}",
            f"Failed: {len(results) - submitted}",
            "",
            "Results:",
        ]
        for target, success, detail in results:
            location = (
                f"{target.cluster_context or 'current'}/"
                f"{target.namespace or self.namespace}"
            )
            if success:
                lines.append(
                    f"- {location} | {target.batch_id}: submitted "
                    f"as {detail}"
                )
            else:
                lines.append(
                    f"- {location} | {target.batch_id}: failed ({detail})"
                )

        return "\n".join(lines)
