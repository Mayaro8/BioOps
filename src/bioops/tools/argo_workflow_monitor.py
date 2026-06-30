from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from kubernetes import client, config


DEFAULT_STEP_PATTERNS: dict[str, list[str]] = {
    "config-creator": ["config-creator", "config_creator"],
    "submit-master": ["submit-master", "submit_master", "submit-master-print"],
    "haplotypecaller": ["haplotypecaller", "haplotype-caller"],
    "transfer-vcf": ["transfer-vcf", "transfer_vcf", "vcf"],
    "transfer-bam": ["transfer-bam", "transfer_bam", "bam"],
}


class ArgoWorkflowMonitor:
    """Read-only Argo workflow progress monitor for SubmitMaster.

    This tool summarizes workflow/DAG/sample progress.
    It does not inspect generic cluster health and does not restart anything.
    """

    def __init__(
        self,
        namespace: str = "argo",
        workflow_name_prefix: str = "bioops-submit-master",
        workflow_template_name: str = "bioops-submit-master-local",
        recent_workflow_limit: int = 5,
        step_patterns: dict[str, list[str]] | None = None,
    ) -> None:
        self.namespace = namespace
        self.workflow_name_prefix = workflow_name_prefix
        self.workflow_template_name = workflow_template_name
        self.recent_workflow_limit = recent_workflow_limit
        self.step_patterns = step_patterns or DEFAULT_STEP_PATTERNS

    def render_latest_progress(self) -> str:
        try:
            workflow = self._latest_matching_workflow()
        except Exception as exc:
            return (
                "SubmitMaster workflow progress is unavailable.\n\n"
                f"Reason: {exc}\n\n"
                "This is a read-only Argo workflow monitor. It needs access to "
                "Argo Workflow CRDs in the configured namespace."
            )

        if workflow is None:
            return (
                "No recent SubmitMaster workflow was found.\n\n"
                f"Namespace: {self.namespace}\n"
                f"Workflow prefix: {self.workflow_name_prefix}\n"
                f"WorkflowTemplate: {self.workflow_template_name}"
            )

        summary = self._summarize_workflow(workflow)
        return self._format_summary(summary)

    def _latest_matching_workflow(self) -> dict[str, Any] | None:
        api = self._custom_objects_api()
        response = api.list_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=self.namespace,
            plural="workflows",
        )

        items = response.get("items", [])
        matches = [item for item in items if self._matches_submit_master(item)]

        matches.sort(
            key=lambda item: item.get("metadata", {}).get("creationTimestamp", ""),
            reverse=True,
        )

        if not matches:
            return None

        return matches[0]

    def _custom_objects_api(self) -> client.CustomObjectsApi:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        return client.CustomObjectsApi()

    def _matches_submit_master(self, workflow: dict[str, Any]) -> bool:
        metadata = workflow.get("metadata", {})
        spec = workflow.get("spec", {})

        name = metadata.get("name", "")
        labels = metadata.get("labels", {}) or {}
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

        return False

    def _summarize_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        metadata = workflow.get("metadata", {})
        status = workflow.get("status", {})
        spec = workflow.get("spec", {})

        nodes = status.get("nodes", {}) or {}

        step_counts: dict[str, Counter] = defaultdict(Counter)
        failed_items: list[str] = []
        active_items: list[str] = []

        for node in nodes.values():
            node_type = node.get("type", "")
            if node_type in {"DAG", "Steps", "Skipped"}:
                continue

            phase = node.get("phase", "Unknown")
            step = self._classify_step(node)
            label = self._node_label(node)

            step_counts[step][phase] += 1

            if phase in {"Failed", "Error"}:
                failed_items.append(label)
            elif phase in {"Running", "Pending"}:
                active_items.append(label)

        current_bottleneck = self._find_bottleneck(step_counts)

        return {
            "name": metadata.get("name", "unknown"),
            "namespace": metadata.get("namespace", self.namespace),
            "phase": status.get("phase", "Unknown"),
            "entrypoint": spec.get("entrypoint", "unknown"),
            "started_at": status.get("startedAt"),
            "finished_at": status.get("finishedAt"),
            "runtime": self._runtime(status.get("startedAt"), status.get("finishedAt")),
            "step_counts": step_counts,
            "current_bottleneck": current_bottleneck,
            "failed_items": failed_items[:20],
            "failed_count": len(failed_items),
            "active_items": active_items[:20],
            "active_count": len(active_items),
            "message": status.get("message", ""),
        }

    def _classify_step(self, node: dict[str, Any]) -> str:
        text = " ".join(
            str(value)
            for value in [
                node.get("displayName", ""),
                node.get("name", ""),
                node.get("templateName", ""),
                node.get("templateRef", {}).get("template", ""),
            ]
        ).lower()

        for step_name, patterns in self.step_patterns.items():
            if any(pattern.lower() in text for pattern in patterns):
                return step_name

        return "other"

    def _node_label(self, node: dict[str, Any]) -> str:
        display = node.get("displayName") or node.get("name") or "unknown-node"
        phase = node.get("phase", "Unknown")
        message = node.get("message", "")

        if message:
            return f"{display} [{phase}] - {message}"

        return f"{display} [{phase}]"

    def _find_bottleneck(self, step_counts: dict[str, Counter]) -> str:
        running_or_pending = []

        for step, counts in step_counts.items():
            active = counts.get("Running", 0) + counts.get("Pending", 0)
            failed = counts.get("Failed", 0) + counts.get("Error", 0)
            total = sum(counts.values())

            if active or failed:
                running_or_pending.append((active + failed, total, step))

        if not running_or_pending:
            return "None detected"

        running_or_pending.sort(reverse=True)
        return running_or_pending[0][2]

    def _runtime(self, started_at: str | None, finished_at: str | None) -> str:
        if not started_at:
            return "unknown"

        start = self._parse_time(started_at)
        end = self._parse_time(finished_at) if finished_at else datetime.now(timezone.utc)

        minutes = max((end - start).total_seconds() / 60, 0)
        return f"{minutes:.1f} min"

    def _parse_time(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _format_summary(self, summary: dict[str, Any]) -> str:
        lines = [
            "SubmitMaster Workflow Progress",
            "",
            f"Workflow: {summary['name']}",
            f"Namespace: {summary['namespace']}",
            f"Phase: {summary['phase']}",
            f"Entrypoint: {summary['entrypoint']}",
            f"Runtime: {summary['runtime']}",
            "",
            "Step progress:",
        ]

        step_counts = summary["step_counts"]
        if not step_counts:
            lines.append("- No workflow nodes found yet.")
        else:
            for step, counts in step_counts.items():
                total = sum(counts.values())
                phase_parts = [f"{phase}: {count}" for phase, count in sorted(counts.items())]
                lines.append(f"- {step}: {total} total ({', '.join(phase_parts)})")

        lines.extend(
            [
                "",
                "Current bottleneck:",
                f"- {summary['current_bottleneck']}",
                "",
                f"Failed nodes/samples: {summary['failed_count']}",
            ]
        )

        for item in summary["failed_items"]:
            lines.append(f"- {item}")

        if summary["failed_count"] > len(summary["failed_items"]):
            hidden = summary["failed_count"] - len(summary["failed_items"])
            lines.append(f"- ... {hidden} more")

        lines.extend(
            [
                "",
                f"Active nodes/samples: {summary['active_count']}",
            ]
        )

        for item in summary["active_items"]:
            lines.append(f"- {item}")

        if summary["active_count"] > len(summary["active_items"]):
            hidden = summary["active_count"] - len(summary["active_items"])
            lines.append(f"- ... {hidden} more")

        if summary["message"]:
            lines.extend(["", "Workflow message:", summary["message"]])

        return "\n".join(lines)
