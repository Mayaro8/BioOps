from __future__ import annotations

from typing import Any

from kubernetes import client, config


class BatchStatusArgoScanner:
    """List Argo workflows for Batch Status Agent using Kubernetes Workflow CRDs."""

    def __init__(
        self,
        *,
        namespace: str,
        workflow_name_prefix: str = "bioops-submit-master",
        workflow_template_name: str = "bioops-submit-master-local",
        label_selector: str = "",
    ) -> None:
        self.namespace = namespace
        self.workflow_name_prefix = workflow_name_prefix
        self.workflow_template_name = workflow_template_name
        self.label_selector = label_selector

    def list_matching_workflows(self) -> list[dict[str, Any]]:
        api = self._custom_objects_api()

        kwargs: dict[str, Any] = {
            "group": "argoproj.io",
            "version": "v1alpha1",
            "namespace": self.namespace,
            "plural": "workflows",
        }

        if self.label_selector:
            kwargs["label_selector"] = self.label_selector

        response = api.list_namespaced_custom_object(**kwargs)
        items = response.get("items", []) or []

        matches = [workflow for workflow in items if self.matches(workflow)]
        matches.sort(
            key=lambda workflow: workflow.get("metadata", {}).get(
                "creationTimestamp", ""
            ),
            reverse=True,
        )
        return matches

    def get_workflow(self, workflow_name: str) -> dict[str, Any]:
        api = self._custom_objects_api()
        return api.get_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=self.namespace,
            plural="workflows",
            name=workflow_name,
        )

    def matches(self, workflow: dict[str, Any]) -> bool:
        metadata = workflow.get("metadata", {}) or {}
        spec = workflow.get("spec", {}) or {}
        labels = metadata.get("labels", {}) or {}
        name = str(metadata.get("name", ""))
        workflow_template_ref = spec.get("workflowTemplateRef", {}) or {}

        if self.workflow_name_prefix and name.startswith(self.workflow_name_prefix):
            return True

        if workflow_template_ref.get("name") == self.workflow_template_name:
            return True

        template_label = (
            labels.get("workflows.argoproj.io/workflow-template")
            or labels.get("workflow-template")
        )
        if template_label == self.workflow_template_name:
            return True

        parameters = spec.get("arguments", {}).get("parameters", []) or []
        parameter_names = {
            str(item.get("name"))
            for item in parameters
            if isinstance(item, dict) and item.get("name")
        }

        return "batch_id" in parameter_names or "BATCH_ID" in parameter_names

    def _custom_objects_api(self) -> client.CustomObjectsApi:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        return client.CustomObjectsApi()
