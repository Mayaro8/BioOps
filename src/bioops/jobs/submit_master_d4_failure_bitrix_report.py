"""SubmitMaster D4 failure diagnosis report sender."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from typing import Any

import requests
from kubernetes import client, config


def _load_kube_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _runtime_minutes(workflow: dict[str, Any]) -> float | None:
    status = workflow.get("status", {})
    started = _parse_time(status.get("startedAt"))
    finished = _parse_time(status.get("finishedAt")) or datetime.now(timezone.utc)
    if not started:
        return None
    return round((finished - started).total_seconds() / 60, 1)


def _workflow_matches(
    workflow: dict[str, Any],
    workflow_prefix: str,
    workflow_template: str | None,
) -> bool:
    metadata = workflow.get("metadata", {})
    spec = workflow.get("spec", {})
    labels = metadata.get("labels", {}) or {}
    name = metadata.get("name", "")

    if workflow_prefix and name.startswith(workflow_prefix):
        return True

    if workflow_template:
        template_ref = spec.get("workflowTemplateRef", {}) or {}
        if template_ref.get("name") == workflow_template:
            return True

        label_values = set(str(v) for v in labels.values())
        if workflow_template in label_values:
            return True

    return False


def _latest_workflow(
    namespace: str,
    workflow_prefix: str,
    workflow_template: str | None,
    workflow_name: str | None = None,
) -> dict[str, Any] | None:
    api = client.CustomObjectsApi()
    if workflow_name:
        return api.get_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=namespace,
            plural="workflows",
            name=workflow_name,
        )
    workflows = api.list_namespaced_custom_object(
        group="argoproj.io",
        version="v1alpha1",
        namespace=namespace,
        plural="workflows",
    )

    items = workflows.get("items", [])
    matches = [
        wf
        for wf in items
        if _workflow_matches(wf, workflow_prefix, workflow_template)
    ]

    if not matches:
        return None

    return sorted(
        matches,
        key=lambda wf: wf.get("metadata", {}).get("creationTimestamp", ""),
        reverse=True,
    )[0]


def _candidate_pod_names(node_id: str, node: dict[str, Any]) -> list[str]:
    candidates = [
        node_id,
        node.get("id"),
        node.get("name"),
        node.get("displayName"),
    ]
    result = []
    for item in candidates:
        if item and item not in result:
            result.append(item)
    return result


def _read_logs(
    core: client.CoreV1Api,
    namespace: str,
    node_id: str,
    node: dict[str, Any],
    tail_lines: int,
) -> tuple[str | None, str]:
    for pod_name in _candidate_pod_names(node_id, node):
        try:
            logs = core.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                tail_lines=tail_lines,
            )
            return pod_name, logs.strip() or "(pod logs empty)"
        except Exception:
            continue

    return None, "(no pod logs found for this failed node)"


def _diagnose(text: str) -> str:
    checks = [
        (
            r"No such file or directory: 'argo'|argo: command not found",
            "Legacy SubmitMaster tried to call the external `argo` CLI, but the BioOps image does not contain it. Add Argo CLI to the image or refactor SubmitMaster to submit Workflow CRDs through the Kubernetes API.",
        ),
        (
            r"ModuleNotFoundError: No module named 'pandas'",
            "Config Creator requires pandas, but pandas is missing from the image. Add pandas to requirements and rebuild the image.",
        ),
        (
            r"aws: command not found",
            "Config Creator tried to call AWS CLI, but awscli is missing from the image. Add awscli or skip S3 upload for the demo path.",
        ),
        (
            r"forbidden|Forbidden|cannot create resource|cannot list resource",
            "This looks like Kubernetes RBAC/service-account permissions. Check serviceAccountName and Role/RoleBinding permissions.",
        ),
        (
            r"ImagePullBackOff|ErrImagePull",
            "Kubernetes could not pull the image. Check image tag, registry path, and imagePullSecret/registry access.",
        ),
    ]

    for pattern, diagnosis in checks:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return diagnosis

    return "No known failure pattern matched. Inspect the failed node message and pod logs manually."


def render_failure_report(
    namespace: str,
    workflow_prefix: str,
    workflow_template: str | None,
    log_tail_lines: int,
    workflow_name: str | None = None,
) -> str:
    _load_kube_config()

    workflow = _latest_workflow(
        namespace=namespace,
        workflow_prefix=workflow_prefix,
        workflow_template=workflow_template,
        workflow_name=workflow_name,
    )

    if workflow is None:
        return (
            "BioOps D4 SubmitMaster Failure Report\n\n"
            "No matching SubmitMaster workflow was found.\n"
            f"Namespace: {namespace}\n"
            f"Workflow prefix: {workflow_prefix}\n"
            f"Workflow template: {workflow_template or 'not set'}"
        )

    metadata = workflow.get("metadata", {})
    status = workflow.get("status", {})
    nodes = status.get("nodes", {}) or {}

    failed_nodes = [
        (node_id, node)
        for node_id, node in nodes.items()
        if node.get("phase") in {"Failed", "Error"}
    ]

    core = client.CoreV1Api()

    name = metadata.get("name", "unknown")
    phase = status.get("phase", "unknown")
    runtime = _runtime_minutes(workflow)

    chunks = [
        "BioOps D4 SubmitMaster Failure Report",
        "",
        f"Workflow: {name}",
        f"Namespace: {namespace}",
        f"Phase: {phase}",
        f"Runtime: {runtime if runtime is not None else 'unknown'} min",
        "",
        f"Failed/Error nodes: {len(failed_nodes)}",
    ]

    if not failed_nodes:
        chunks.extend(
            [
                "",
                "No failed/error nodes found in this workflow.",
                "D4 diagnosis is only meaningful for Failed/Error workflows.",
            ]
        )
        return "\n".join(chunks)

    combined_failure_text = []

    for i, (node_id, node) in enumerate(failed_nodes[:5], start=1):
        display_name = node.get("displayName") or node.get("name") or node_id
        template_name = node.get("templateName", "unknown")
        node_phase = node.get("phase", "unknown")
        message = node.get("message", "") or "(no node message)"

        pod_name, logs = _read_logs(
            core=core,
            namespace=namespace,
            node_id=node_id,
            node=node,
            tail_lines=log_tail_lines,
        )

        failure_text = "\n".join([message, logs])
        combined_failure_text.append(failure_text)

        chunks.extend(
            [
                "",
                f"Failure #{i}",
                f"- Node: {display_name}",
                f"- Template/step: {template_name}",
                f"- Phase: {node_phase}",
                f"- Pod: {pod_name or 'unknown'}",
                f"- Node message: {message}",
                "",
                f"Last {log_tail_lines} log lines:",
                logs,
            ]
        )

    diagnosis = _diagnose("\n".join(combined_failure_text))

    chunks.extend(
        [
            "",
            "Likely diagnosis:",
            diagnosis,
        ]
    )

    if len(failed_nodes) > 5:
        chunks.append(f"\nNote: showing first 5 failed nodes out of {len(failed_nodes)}.")

    return "\n".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook-url", required=True)
    parser.add_argument("--dialog-id", required=True)
    parser.add_argument("--namespace", default="argo")
    parser.add_argument("--workflow-prefix", default="bioops-submit-master-target")
    parser.add_argument("--workflow-template", default="bioops-submit-master-local")
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--log-tail-lines", type=int, default=80)
    args = parser.parse_args()

    report = render_failure_report(
        namespace=args.namespace,
        workflow_prefix=args.workflow_prefix,
        workflow_template=args.workflow_template,
        log_tail_lines=args.log_tail_lines,
        workflow_name=args.workflow_name,
    )

    print("=== D4 failure report ===")
    print(report)

    bitrix_url = args.webhook_url.rstrip("/") + "/im.message.add.json"
    message = "[B]BioOps D4 SubmitMaster Failure Report[/B]\n\n" + report

    response = requests.post(
        bitrix_url,
        data={
            "DIALOG_ID": args.dialog_id,
            "MESSAGE": message,
        },
        timeout=15,
    )

    print("=== Bitrix response ===")
    print("status_code:", response.status_code)
    print(response.text)
    response.raise_for_status()


if __name__ == "__main__":
    main()
