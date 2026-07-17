"""SubmitMaster D5 automatic safe retry/resubmit job with Bitrix report."""

from __future__ import annotations

import argparse
import copy
import re
from datetime import datetime, timezone
from typing import Any

import requests
from kubernetes import client, config


ACTIVE_PHASES = {"Pending", "Running"}
FAILED_PHASES = {"Failed", "Error"}


NON_RETRYABLE_PATTERNS: list[tuple[str, str]] = [
    (
        r"No such file or directory: 'argo'|argo: command not found",
        "Not retryable: SubmitMaster needs the external `argo` CLI, but the image does not contain it.",
    ),
    (
        r"ModuleNotFoundError: No module named",
        "Not retryable: a required Python dependency is missing from the image.",
    ),
    (
        r"aws: command not found",
        "Not retryable: Config Creator tried to use AWS CLI, but `aws` is missing from the image.",
    ),
    (
        r"forbidden|Forbidden|cannot create resource|cannot list resource",
        "Not retryable: Kubernetes RBAC/service-account permissions are insufficient.",
    ),
    (
        r"InvalidImageName|ImagePullBackOff|ErrImagePull",
        "Not retryable without changes: Kubernetes could not pull or parse the image.",
    ),
    (
        r"Invalid URL|MissingSchema|YOUR_BITRIX_WEBHOOK_URL",
        "Not retryable: Bitrix webhook URL is invalid or still a placeholder.",
    ),
    (
        r"invalid json|JSONDecodeError|config file.*not found|No such file or directory",
        "Not retryable: workflow/config/input file appears invalid or missing.",
    ),
    (
        r"Permission denied|AccessDenied|Unauthorized|authentication failed",
        "Not retryable: credentials or permissions are missing.",
    ),
]


RETRYABLE_PATTERNS: list[tuple[str, str]] = [
    (
        r"Evicted|The node was low on resource|node was low on resource",
        "Retryable: pod was evicted because of temporary node/resource pressure.",
    ),
    (
        r"NodeLost|node lost|pod deleted|pod was deleted",
        "Retryable: pod/node disappeared during execution.",
    ),
    (
        r"DeadlineExceeded|deadline exceeded|context deadline exceeded",
        "Retryable: operation hit a timeout/deadline.",
    ),
    (
        r"temporarily unavailable|ServiceUnavailable|503|502|504",
        "Retryable: remote service looked temporarily unavailable.",
    ),
    (
        r"connection reset|connection refused|i/o timeout|TLS handshake timeout",
        "Retryable: transient network failure.",
    ),
    (
        r"Too Many Requests|429|rate limit",
        "Retryable: temporary API rate limiting.",
    ),
]


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


def _list_workflows(api: client.CustomObjectsApi, namespace: str) -> list[dict[str, Any]]:
    response = api.list_namespaced_custom_object(
        group="argoproj.io",
        version="v1alpha1",
        namespace=namespace,
        plural="workflows",
    )
    return response.get("items", [])


def _get_workflow(api, namespace, workflow_name):
    return api.get_namespaced_custom_object(
        group="argoproj.io",
        version="v1alpha1",
        namespace=namespace,
        plural="workflows",
        name=workflow_name,
    )


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

        if workflow_template in {str(v) for v in labels.values()}:
            return True

    return False


def _latest_matching_workflow(
    api: client.CustomObjectsApi,
    namespace: str,
    workflow_prefix: str,
    workflow_template: str | None,
    workflow_name: str | None = None,
) -> dict[str, Any] | None:
    if workflow_name:
        return _get_workflow(api, namespace, workflow_name)
    workflows = _list_workflows(api, namespace)

    matches = [
        workflow
        for workflow in workflows
        if _workflow_matches(workflow, workflow_prefix, workflow_template)
    ]

    if not matches:
        return None

    return sorted(
        matches,
        key=lambda workflow: workflow.get("metadata", {}).get("creationTimestamp", ""),
        reverse=True,
    )[0]


def _failure_text(workflow: dict[str, Any]) -> str:
    status = workflow.get("status", {})
    nodes = status.get("nodes", {}) or {}

    chunks: list[str] = [
        str(status.get("phase", "")),
        str(status.get("message", "")),
        str(workflow.get("metadata", {}).get("name", "")),
    ]

    for node in nodes.values():
        if node.get("phase") in FAILED_PHASES:
            chunks.extend(
                [
                    str(node.get("displayName", "")),
                    str(node.get("name", "")),
                    str(node.get("templateName", "")),
                    str(node.get("message", "")),
                    str(node.get("phase", "")),
                ]
            )

    return "\n".join(chunks)


def _retry_decision(workflow: dict[str, Any]) -> tuple[bool, str]:
    phase = workflow.get("status", {}).get("phase", "unknown")

    if phase not in FAILED_PHASES:
        return False, f"Workflow phase is {phase}, not Failed/Error. Retry is not needed."

    text = _failure_text(workflow)

    for pattern, reason in NON_RETRYABLE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return False, reason

    for pattern, reason in RETRYABLE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True, reason

    return False, (
        "Not safely retryable: failure reason is unknown. "
        "Run D4 and inspect logs before automatic restart."
    )


def assess_workflow_retry(*, namespace, workflow_name):
    _load_kube_config()
    workflow = _get_workflow(
        client.CustomObjectsApi(),
        namespace,
        workflow_name,
    )
    retryable, reason = _retry_decision(workflow)
    if retryable:
        try:
            _, samples = _target_retry_spec(workflow)
        except ValueError as error:
            return False, f"Not safely retryable: {error}."
        reason = f"{reason} Target samples: {', '.join(samples)}."
    return retryable, reason


def _safe_label_value(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9.-]+", "-", value.lower()).strip("-.")
    return cleaned[:63].strip("-.") or "unknown"


def _safe_retry_name(root: str, attempt: int) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", root.lower()).strip("-")
    suffix = f"-d5-retry-{attempt}"
    cleaned = cleaned[: 63 - len(suffix)].strip("-") or "submit-master"
    return f"{cleaned}{suffix}"


def _retry_metadata(workflow: dict[str, Any]) -> tuple[str, int]:
    metadata = workflow.get("metadata", {})
    annotations = metadata.get("annotations", {}) or {}

    current_name = metadata.get("name", "unknown")
    root = annotations.get("bioops.dev/d5-root-workflow") or current_name

    raw_count = annotations.get("bioops.dev/d5-retry-count", "0")
    try:
        retry_count = int(raw_count)
    except ValueError:
        retry_count = 0

    return root, retry_count


def _has_active_retry(
    api: client.CustomObjectsApi,
    namespace: str,
    root_workflow: str,
    current_workflow_name: str,
) -> bool:
    response = api.list_namespaced_custom_object(
        group="argoproj.io",
        version="v1alpha1",
        namespace=namespace,
        plural="workflows",
        label_selector=(
            f"bioops.dev/d5-root={_safe_label_value(root_workflow)}"
        ),
    )
    workflows = response.get("items", []) or []

    for workflow in workflows:
        metadata = workflow.get("metadata", {})
        annotations = metadata.get("annotations", {}) or {}
        status = workflow.get("status", {})

        name = metadata.get("name")
        phase = status.get("phase")

        if name == current_workflow_name:
            continue

        if annotations.get("bioops.dev/d5-root-workflow") != root_workflow:
            continue

        if phase in ACTIVE_PHASES:
            return True

    return False


def _target_retry_spec(workflow: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return a spec scoped to failed samples, or fail closed."""
    metadata = workflow.get("metadata", {}) or {}
    workflow_sample = (metadata.get("labels", {}) or {}).get("bioops.dev/sample-id")
    original_spec = copy.deepcopy(workflow.get("spec", {}))
    if workflow_sample:
        return original_spec, [workflow_sample]

    templates = original_spec.get("templates", []) or []
    template_samples = {
        template.get("name"): (template.get("metadata", {}).get("labels", {}) or {}).get(
            "bioops.dev/sample-id"
        )
        for template in templates
        if isinstance(template, dict) and template.get("name")
    }
    failed_template_names = {
        node.get("templateName")
        for node in (workflow.get("status", {}).get("nodes", {}) or {}).values()
        if node.get("phase") in FAILED_PHASES and node.get("templateName")
    }
    failed_samples = sorted({
        template_samples[name]
        for name in failed_template_names
        if template_samples.get(name)
    })
    if not failed_samples:
        raise ValueError(
            "retry scope is unknown: failed nodes are not mapped to sample-labeled templates"
        )

    selected_templates = {
        name for name, sample in template_samples.items() if sample in failed_samples
    }
    entrypoint = original_spec.get("entrypoint")
    root = next(
        (template for template in templates if template.get("name") == entrypoint),
        None,
    )
    if not root or not isinstance(root.get("dag", {}).get("tasks"), list):
        raise ValueError("retry scope is unsupported: workflow entrypoint is not a DAG")

    selected_tasks = [
        copy.deepcopy(task)
        for task in root["dag"]["tasks"]
        if task.get("template") in selected_templates
    ]
    selected_task_names = {task.get("name") for task in selected_tasks}
    for task in selected_tasks:
        if "dependencies" in task:
            task["dependencies"] = [
                name for name in task["dependencies"] if name in selected_task_names
            ]
            if not task["dependencies"]:
                task.pop("dependencies")

    if not selected_tasks:
        raise ValueError("retry scope is empty after filtering failed samples")
    root["dag"]["tasks"] = selected_tasks
    original_spec["templates"] = [
        root,
        *[
            template for template in templates
            if template.get("name") in selected_templates
        ],
    ]
    return original_spec, failed_samples


def _resubmit_workflow(
    api: client.CustomObjectsApi,
    workflow: dict[str, Any],
    namespace: str,
    root_workflow: str,
    next_retry_count: int,
) -> str:
    metadata = workflow.get("metadata", {})
    old_name = metadata.get("name", "unknown")

    new_spec, targeted_samples = _target_retry_spec(workflow)

    # If the old workflow was manually stopped, do not copy the stop instruction.
    new_spec.pop("shutdown", None)

    parameters = new_spec.setdefault(
        "arguments", {}
    ).setdefault("parameters", [])
    attempt = next(
        (
            item for item in parameters
            if isinstance(item, dict)
            and item.get("name") == "attempt"
        ),
        None,
    )
    if attempt is None:
        parameters.append({
            "name": "attempt",
            "value": str(next_retry_count),
        })
    else:
        attempt["value"] = str(next_retry_count)

    old_labels = metadata.get("labels", {}) or {}
    labels = {
        key: value
        for key, value in old_labels.items()
        if key.startswith("bioops.dev/")
    }
    labels.update({
        "bioops.dev/d5-resubmit": "true",
        "bioops.dev/d5-root": _safe_label_value(root_workflow),
        "bioops.dev/attempt": str(next_retry_count),
    })
    if len(targeted_samples) == 1:
        labels["bioops.dev/sample-id"] = targeted_samples[0]

    body = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Workflow",
        "metadata": {
            "name": _safe_retry_name(root_workflow, next_retry_count),
            "namespace": namespace,
            "labels": labels,
            "annotations": {
                "bioops.dev/d5-root-workflow": root_workflow,
                "bioops.dev/d5-parent-workflow": old_name,
                "bioops.dev/d5-retry-count": str(next_retry_count),
                "bioops.dev/d5-target-samples": ",".join(targeted_samples),
            },
        },
        "spec": new_spec,
    }

    created = api.create_namespaced_custom_object(
        group="argoproj.io",
        version="v1alpha1",
        namespace=namespace,
        plural="workflows",
        body=body,
    )

    return created.get("metadata", {}).get("name", "unknown")


def render_d5_report(
    namespace: str,
    workflow_prefix: str,
    workflow_template: str | None,
    auto_retry: bool,
    max_retries: int,
    force_retry: bool,
    workflow_name: str | None = None,
) -> str:
    _load_kube_config()
    api = client.CustomObjectsApi()

    workflow = _latest_matching_workflow(
        api=api,
        namespace=namespace,
        workflow_prefix=workflow_prefix,
        workflow_template=workflow_template,
        workflow_name=workflow_name,
    )

    if workflow is None:
        return (
            "BioOps D5 SubmitMaster Auto-Retry Report\n\n"
            "No matching SubmitMaster workflow was found.\n"
            f"Namespace: {namespace}\n"
            f"Workflow prefix: {workflow_prefix}\n"
            f"Workflow template: {workflow_template or 'not set'}"
        )

    metadata = workflow.get("metadata", {})
    status = workflow.get("status", {})

    name = metadata.get("name", "unknown")
    phase = status.get("phase", "unknown")
    runtime = _runtime_minutes(workflow)

    root_workflow, current_retry_count = _retry_metadata(workflow)
    next_retry_count = current_retry_count + 1

    retryable, decision = _retry_decision(workflow)

    active_retry_exists = _has_active_retry(
        api=api,
        namespace=namespace,
        root_workflow=root_workflow,
        current_workflow_name=name,
    )

    action = "No retry performed."
    new_workflow_name: str | None = None

    if not auto_retry:
        action = "Auto-retry disabled. D5 only reported the decision."

    elif active_retry_exists:
        action = "Retry blocked: another D5 retry workflow for the same root workflow is already active."

    elif current_retry_count >= max_retries:
        action = f"Retry blocked: max retries reached ({current_retry_count}/{max_retries})."

    elif retryable or force_retry:
        try:
            new_workflow_name = _resubmit_workflow(
                api=api,
                workflow=workflow,
                namespace=namespace,
                root_workflow=root_workflow,
                next_retry_count=next_retry_count,
            )
            action = f"Automatically resubmitted workflow as: {new_workflow_name}"
        except Exception as exc:
            action = f"Auto-retry attempted but failed to create new Workflow: {exc}"

    else:
        action = "Retry blocked: failure is not safely retryable."

    lines = [
        "BioOps D5 SubmitMaster Auto-Retry Report",
        "",
        f"Workflow: {name}",
        f"Root workflow: {root_workflow}",
        f"Namespace: {namespace}",
        f"Phase: {phase}",
        f"Runtime: {runtime if runtime is not None else 'unknown'} min",
        "",
        f"Current retry count: {current_retry_count}",
        f"Max retries: {max_retries}",
        f"Retryable: {'yes' if retryable else 'no'}",
        f"Decision: {decision}",
        f"Auto-retry enabled: {'yes' if auto_retry else 'no'}",
        f"Action: {action}",
    ]

    if force_retry:
        lines.extend(
            [
                "",
                "Warning:",
                "--force-retry was enabled. This bypasses the safe retry decision.",
            ]
        )

    if new_workflow_name:
        lines.extend(
            [
                "",
                "New workflow:",
                new_workflow_name,
            ]
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook-url", required=True)
    parser.add_argument("--dialog-id", required=True)
    parser.add_argument("--namespace", default="argo")
    parser.add_argument("--workflow-prefix", default="bioops-submit-master-target")
    parser.add_argument("--workflow-template", default="bioops-submit-master-local")
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--auto-retry", action="store_true")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--force-retry", action="store_true")
    args = parser.parse_args()

    report = render_d5_report(
        namespace=args.namespace,
        workflow_prefix=args.workflow_prefix,
        workflow_template=args.workflow_template,
        auto_retry=args.auto_retry,
        max_retries=args.max_retries,
        force_retry=args.force_retry,
        workflow_name=args.workflow_name,
    )

    print("=== D5 auto-retry report ===")
    print(report)

    bitrix_url = args.webhook_url.rstrip("/") + "/im.message.add.json"
    message = "[B]BioOps D5 SubmitMaster Auto-Retry Report[/B]\n\n" + report

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
