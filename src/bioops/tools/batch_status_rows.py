from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SHEET_COLUMNS = [
    "batch_id",
    "workflow_name",
    "workflow_template",
    "stage",
    "mode",
    "sample_ids",
    "status",
    "progress",
    "current_step",
    "created_at",
    "started_at",
    "finished_at",
    "last_checked_at",
    "error_message",
    "argo_url",
]


def workflow_to_batch_status_row(
    workflow: dict[str, Any],
    *,
    argo_ui_url: str = "",
) -> dict[str, str]:
    """Convert one Argo Workflow object into one Google Sheet status row."""

    metadata = workflow.get("metadata", {}) or {}
    spec = workflow.get("spec", {}) or {}
    status = workflow.get("status", {}) or {}
    labels = metadata.get("labels", {}) or {}

    parameters = _parameters_to_dict(spec.get("arguments", {}).get("parameters", []))
    workflow_name = str(metadata.get("name", ""))

    batch_id = (
        parameters.get("batch_id")
        or parameters.get("BATCH_ID")
        or labels.get("bioops.dev/batch-id")
        or labels.get("bioops/batch-id")
        or labels.get("batch_id")
        or ""
    )

    workflow_template = (
        (spec.get("workflowTemplateRef", {}) or {}).get("name")
        or labels.get("workflows.argoproj.io/workflow-template")
        or labels.get("workflow-template")
        or ""
    )

    row = {
        "batch_id": str(batch_id),
        "workflow_name": workflow_name,
        "workflow_template": str(workflow_template),
        "stage": str(parameters.get("stage") or parameters.get("STAGE") or ""),
        "mode": str(parameters.get("mode") or parameters.get("MODE") or ""),
        "sample_ids": str(
            parameters.get("sample_id")
            or parameters.get("SAMPLE_ID")
            or parameters.get("sample_ids")
            or parameters.get("SAMPLE_IDS")
            or parameters.get("samples")
            or labels.get("bioops.dev/sample-id")
            or ""
        ),
        "status": str(status.get("phase") or "Unknown"),
        "progress": str(status.get("progress") or ""),
        "current_step": _current_step(status),
        "created_at": str(metadata.get("creationTimestamp") or ""),
        "started_at": str(status.get("startedAt") or ""),
        "finished_at": str(status.get("finishedAt") or ""),
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
        "error_message": _error_message(status),
        "argo_url": _argo_url(argo_ui_url, workflow_name),
    }

    return {column: row.get(column, "") for column in SHEET_COLUMNS}


def workflows_to_batch_status_rows(
    workflows: list[dict[str, Any]],
    *,
    argo_ui_url: str = "",
) -> list[dict[str, str]]:
    return [
        workflow_to_batch_status_row(workflow, argo_ui_url=argo_ui_url)
        for workflow in workflows
    ]


def _parameters_to_dict(parameters: Any) -> dict[str, str]:
    if not isinstance(parameters, list):
        return {}

    result: dict[str, str] = {}
    for item in parameters:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        result[str(name)] = str(item.get("value", ""))
    return result


def _current_step(status: dict[str, Any]) -> str:
    nodes = status.get("nodes", {}) or {}
    active = []

    for node in nodes.values():
        if not isinstance(node, dict):
            continue

        phase = node.get("phase")
        if phase not in {"Running", "Pending"}:
            continue

        display = (
            node.get("displayName")
            or node.get("templateName")
            or node.get("name")
            or ""
        )
        if display:
            active.append(str(display))

    if not active:
        return ""

    return "; ".join(active[:5])


def _error_message(status: dict[str, Any]) -> str:
    if status.get("message"):
        return str(status["message"])

    nodes = status.get("nodes", {}) or {}
    errors = []

    for node in nodes.values():
        if not isinstance(node, dict):
            continue

        if node.get("phase") in {"Failed", "Error"}:
            display = node.get("displayName") or node.get("name") or "unknown-node"
            message = node.get("message") or ""
            errors.append(f"{display}: {message}".strip())

    return "; ".join(errors[:5])


def _argo_url(argo_ui_url: str, workflow_name: str) -> str:
    if not argo_ui_url or not workflow_name:
        return ""

    return f"{argo_ui_url.rstrip('/')}/workflows/{workflow_name}"
