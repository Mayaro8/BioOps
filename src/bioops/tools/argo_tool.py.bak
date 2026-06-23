import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from kubernetes import client, config


@dataclass
class ArgoWorkflowSummary:
    name: str
    namespace: str
    phase: str
    started_at: str
    finished_at: str
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class ArgoSubmitPreview:
    namespace: str
    workflow_file: str
    parameters: dict[str, str]
    command: str
    can_submit: bool
    missing_config: list[str]


@dataclass
class ArgoSubmitResult:
    submitted: bool
    workflow_name: str | None
    namespace: str
    phase: str
    message: str
    error: str | None = None


@dataclass
class ArgoNodeStatus:
    name: str
    display_name: str
    phase: str
    node_type: str
    template_name: str
    started_at: str
    finished_at: str
    message: str


@dataclass
class ArgoWorkflowStatus:
    name: str
    namespace: str
    phase: str
    progress: str
    started_at: str
    finished_at: str
    message: str
    labels: dict[str, str]
    running_steps: list[ArgoNodeStatus]
    failed_steps: list[ArgoNodeStatus]
    all_steps: list[ArgoNodeStatus]


class ArgoTool:
    """
    Argo Workflows helper.

    Supports:
    - list/get workflows
    - workflow status summaries
    - submit command preview
    - confirmed workflow submission
    """

    group = "argoproj.io"
    version = "v1alpha1"
    plural = "workflows"

    def __init__(
        self,
        namespace: str | None = None,
        workflow_file: str | None = None,
    ):
        self.namespace = namespace or os.getenv("BIOOPS_ARGO_NAMESPACE", "argo")
        self.workflow_file = workflow_file or os.getenv("BIOOPS_ARGO_WORKFLOW_FILE")

    def list_workflows(self, namespace: str | None = None) -> list[ArgoWorkflowSummary]:
        namespace = namespace or self.namespace
        api = self._custom_objects_api()

        response = api.list_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=namespace,
            plural=self.plural,
        )

        workflows: list[ArgoWorkflowSummary] = []

        for item in response.get("items", []):
            metadata = item.get("metadata", {})
            status = item.get("status", {})

            workflows.append(
                ArgoWorkflowSummary(
                    name=metadata.get("name", ""),
                    namespace=metadata.get("namespace", namespace),
                    phase=status.get("phase", "Unknown"),
                    started_at=status.get("startedAt", ""),
                    finished_at=status.get("finishedAt", ""),
                    labels=metadata.get("labels", {}) or {},
                )
            )

        return workflows

    def list_workflow_statuses(
        self,
        namespace: str | None = None,
    ) -> list[ArgoWorkflowStatus]:
        namespace = namespace or self.namespace
        api = self._custom_objects_api()

        response = api.list_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=namespace,
            plural=self.plural,
        )

        return [
            self._workflow_to_status(item, namespace=namespace)
            for item in response.get("items", [])
        ]

    def get_workflow(
        self,
        name: str,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        namespace = namespace or self.namespace
        api = self._custom_objects_api()

        return api.get_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=namespace,
            plural=self.plural,
            name=name,
        )

    def get_workflow_status(
        self,
        name: str,
        namespace: str | None = None,
    ) -> ArgoWorkflowStatus:
        namespace = namespace or self.namespace
        workflow = self.get_workflow(name=name, namespace=namespace)
        return self._workflow_to_status(workflow, namespace=namespace)

    def get_workflow_phase(
        self,
        name: str,
        namespace: str | None = None,
    ) -> str:
        workflow = self.get_workflow(name=name, namespace=namespace)
        return workflow.get("status", {}).get("phase", "Unknown")

    def prepare_submit_command(
        self,
        workflow_file: str | None = None,
        namespace: str | None = None,
        parameters: dict[str, str] | None = None,
    ) -> ArgoSubmitPreview:
        namespace = namespace or self.namespace
        workflow_file = workflow_file or self.workflow_file
        parameters = parameters or {}

        missing_config: list[str] = []

        if not workflow_file:
            missing_config.append("workflow_file or BIOOPS_ARGO_WORKFLOW_FILE")
        elif not Path(workflow_file).exists():
            missing_config.append(f"workflow file not found: {workflow_file}")

        command_parts = ["argo", "submit", "-n", namespace]

        if workflow_file:
            command_parts.append(workflow_file)
        else:
            command_parts.append("<workflow-file>")

        for key, value in parameters.items():
            if value:
                command_parts.extend(["-p", f"{key}={value}"])

        return ArgoSubmitPreview(
            namespace=namespace,
            workflow_file=workflow_file or "",
            parameters=parameters,
            command=" ".join(command_parts),
            can_submit=not missing_config,
            missing_config=missing_config,
        )

    def submit_workflow(
        self,
        workflow_file: str,
        namespace: str | None = None,
        parameters: dict[str, str] | None = None,
    ) -> ArgoSubmitResult:
        namespace = namespace or self.namespace
        parameters = parameters or {}

        workflow_path = Path(workflow_file)

        if not workflow_path.exists():
            return ArgoSubmitResult(
                submitted=False,
                workflow_name=None,
                namespace=namespace,
                phase="Unknown",
                message="Workflow file not found.",
                error=f"workflow file not found: {workflow_file}",
            )

        try:
            with workflow_path.open("r", encoding="utf-8") as file:
                workflow = yaml.safe_load(file)

            workflow = self._inject_parameters(workflow, parameters)

            api = self._custom_objects_api()
            created = api.create_namespaced_custom_object(
                group=self.group,
                version=self.version,
                namespace=namespace,
                plural=self.plural,
                body=workflow,
            )

            metadata = created.get("metadata", {})
            status = created.get("status", {})

            workflow_name = metadata.get("name")

            return ArgoSubmitResult(
                submitted=True,
                workflow_name=workflow_name,
                namespace=namespace,
                phase=status.get("phase", "Pending"),
                message="Workflow submitted successfully.",
                error=None,
            )

        except Exception as error:
            return ArgoSubmitResult(
                submitted=False,
                workflow_name=None,
                namespace=namespace,
                phase="Unknown",
                message="Workflow submission failed.",
                error=f"{type(error).__name__}: {error}",
            )

    def _workflow_to_status(
        self,
        workflow: dict[str, Any],
        namespace: str,
    ) -> ArgoWorkflowStatus:
        metadata = workflow.get("metadata", {})
        status = workflow.get("status", {})
        labels = metadata.get("labels", {}) or {}
        nodes = status.get("nodes", {}) or {}

        all_steps: list[ArgoNodeStatus] = []

        for node_name, node in nodes.items():
            node_status = ArgoNodeStatus(
                name=node_name,
                display_name=node.get("displayName", node_name),
                phase=node.get("phase", "Unknown"),
                node_type=node.get("type", ""),
                template_name=node.get("templateName", ""),
                started_at=node.get("startedAt", ""),
                finished_at=node.get("finishedAt", ""),
                message=node.get("message", ""),
            )

            if node_status.node_type in {"Pod", "Steps", "StepGroup", "DAG", ""}:
                all_steps.append(node_status)

        running_steps = [
            node for node in all_steps
            if node.phase in {"Running", "Pending"}
        ]

        failed_steps = [
            node for node in all_steps
            if node.phase in {"Failed", "Error"}
        ]

        return ArgoWorkflowStatus(
            name=metadata.get("name", ""),
            namespace=metadata.get("namespace", namespace),
            phase=status.get("phase", "Unknown"),
            progress=status.get("progress", ""),
            started_at=status.get("startedAt", ""),
            finished_at=status.get("finishedAt", ""),
            message=status.get("message", ""),
            labels=labels,
            running_steps=running_steps,
            failed_steps=failed_steps,
            all_steps=all_steps,
        )

    def _inject_parameters(
        self,
        workflow: dict[str, Any],
        parameters: dict[str, str],
    ) -> dict[str, Any]:
        if not parameters:
            return workflow

        spec = workflow.setdefault("spec", {})
        arguments = spec.setdefault("arguments", {})
        existing_parameters = arguments.setdefault("parameters", [])

        by_name = {
            item.get("name"): item
            for item in existing_parameters
            if isinstance(item, dict)
        }

        for key, value in parameters.items():
            if not value:
                continue

            if key in by_name:
                by_name[key]["value"] = value
            else:
                existing_parameters.append(
                    {
                        "name": key,
                        "value": value,
                    }
                )

        return workflow

    def _custom_objects_api(self) -> client.CustomObjectsApi:
        try:
            config.load_kube_config()
        except Exception:
            config.load_incluster_config()

        return client.CustomObjectsApi()
