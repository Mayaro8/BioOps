from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from statistics import fmean, quantiles
from typing import Any

from kubernetes import client, config

from bioops.tools.argo_workflow_monitor import ArgoWorkflowMonitor


LABEL_VALUE = re.compile(
    r"^[A-Za-z0-9](?:[-A-Za-z0-9_.]{0,61}[A-Za-z0-9])?$"
)

STEP_PATTERNS = {
    "config-creator": ["config-creator", "config_creator"],
    "submit-master": ["submit-master", "submit_master"],
    "haplotypecaller": ["haplotypecaller", "haplotype-caller"],
    "gvcf-to-vcf": ["gvcf-to-vcf", "gvcf_to_vcf"],
    "beagle": ["beagle"],
    "transfer-vcf": ["transfer-vcf", "transfer_vcf"],
    "transfer-bam": ["transfer-bam", "transfer_bam"],
}


class SubmitMasterScopeMonitor(ArgoWorkflowMonitor):
    """Read workflows and pods by explicit batch/sample labels."""

    def __init__(
        self,
        namespace: str,
        workflow_name_prefix: str,
        workflow_template_name: str,
        step_patterns: dict[str, list[str]] | None = None,
        *,
        batch_label: str = "bioops.dev/batch-id",
        sample_label: str = "bioops.dev/sample-id",
        workflow_page_size: int = 100,
        pod_page_size: int = 200,
        max_listed_items: int = 10,
        custom_api: Any | None = None,
        core_api: Any | None = None,
    ) -> None:
        super().__init__(
            namespace=namespace,
            workflow_name_prefix=workflow_name_prefix,
            workflow_template_name=workflow_template_name,
            step_patterns=step_patterns or STEP_PATTERNS,
        )
        self.batch_label = batch_label
        self.sample_label = sample_label
        self.workflow_page_size = max(1, workflow_page_size)
        self.pod_page_size = max(1, pod_page_size)
        self.max_listed_items = max(1, max_listed_items)
        self._custom_api_override = custom_api
        self._core_api_override = core_api

    def render_batch_status(self, batch_id: str) -> str:
        try:
            attempts = self._find_workflows(batch_id=batch_id)
        except Exception as error:
            return self._error("batch", batch_id, error)

        if not attempts:
            return f"No SubmitMaster workflows found for batch {batch_id}."

        latest: dict[str, dict[str, Any]] = {}

        for workflow in attempts:
            sample = (
                self._label(workflow, self.sample_label)
                or workflow["metadata"]["name"]
            )
            latest.setdefault(sample, workflow)

        snapshots = [
            self._snapshot(workflow)
            for workflow in latest.values()
        ]
        total = len(snapshots)

        phase_counts = Counter(
            item["phase"]
            for item in snapshots
        )
        step_counts = Counter(
            item["step"]
            for item in snapshots
        )
        runtimes = [
            item["runtime"]
            for item in snapshots
            if item["runtime"] is not None
        ]

        lines = [
            "SubmitMaster Batch Status",
            "",
            f"Batch: {batch_id}",
            f"Samples: {total}",
            f"Workflow attempts: {len(attempts)}",
            "",
            "Workflow status:",
            *self._percentages(phase_counts, total),
            "",
            "Current sample step:",
            *self._percentages(step_counts, total),
            "",
            "Runtime statistics:",
            *self._runtime_statistics(snapshots, runtimes),
        ]

        failed = [
            item
            for item in snapshots
            if item["phase"] in {"Failed", "Error"}
        ]

        lines.extend([
            "",
            f"Failed samples: {len(failed)}",
        ])

        for item in failed[: self.max_listed_items]:
            lines.append(
                f"- {item['sample']}: "
                f"{item['step']} ({item['name']})"
            )

        if len(failed) > self.max_listed_items:
            hidden = len(failed) - self.max_listed_items
            lines.append(f"- ... {hidden} more")

        return "\n".join(lines)

    def render_sample_status(
        self,
        sample_id: str,
        batch_id: str | None = None,
    ) -> str:
        try:
            workflow = self.resolve_sample_workflow(
                sample_id=sample_id,
                batch_id=batch_id,
            )
            workflow_name = workflow["metadata"]["name"]
            pods = self._list_pods(workflow_name)
        except Exception as error:
            return self._error("sample", sample_id, error)

        snapshot = self._snapshot(workflow)
        groups: Counter[tuple[str, str]] = Counter()

        for pod in pods:
            labels = (
                getattr(pod.metadata, "labels", None)
                or {}
            )
            step = labels.get("pipeline_step") or "unknown"
            phase = (
                getattr(pod.status, "phase", None)
                or "Unknown"
            )
            groups[(step, phase)] += 1

        lines = [
            "SubmitMaster Sample Status",
            "",
            f"Batch: {snapshot['batch'] or 'unknown'}",
            f"Sample: {snapshot['sample'] or sample_id}",
            f"Workflow: {snapshot['name']}",
            f"Attempt: {snapshot['attempt']}",
            f"Status: {snapshot['phase']}",
            f"Current step: {snapshot['step']}",
            f"Runtime: {self._minutes(snapshot['runtime'])}",
            "",
            f"Pods: {len(pods)}",
        ]

        if not groups:
            lines.append("- No pods found.")
        else:
            for (step, phase), count in sorted(
                groups.items()
            ):
                percentage = count / len(pods) * 100
                lines.append(
                    f"- {step} [{phase}]: "
                    f"{count} ({percentage:.1f}%)"
                )

        return "\n".join(lines)

    def render_workflow_status(
        self,
        workflow_name: str,
    ) -> str:
        try:
            workflow = self.get_workflow(workflow_name)
        except Exception as error:
            return self._error(
                "workflow",
                workflow_name,
                error,
            )

        summary = self._summarize_workflow(workflow)
        return self._format_summary(summary)

    def get_workflow(
        self,
        workflow_name: str,
    ) -> dict[str, Any]:
        if not workflow_name.strip():
            raise ValueError("workflow_name is required")

        return self._custom_api().get_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=self.namespace,
            plural="workflows",
            name=workflow_name,
        )

    def resolve_sample_workflow(
        self,
        *,
        sample_id: str,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        workflows = self._find_workflows(
            batch_id=batch_id,
            sample_id=sample_id,
        )

        if not workflows:
            raise ValueError(
                f"No workflow found for sample {sample_id}"
            )

        if batch_id is None:
            batches = {
                self._label(item, self.batch_label)
                or "unknown"
                for item in workflows
            }

            if len(batches) > 1:
                batch_names = ", ".join(sorted(batches))
                raise ValueError(
                    f"Sample {sample_id} exists in "
                    f"multiple batches: {batch_names}. "
                    "Specify batch_id."
                )

        return workflows[0]

    def _find_workflows(
        self,
        *,
        batch_id: str | None = None,
        sample_id: str | None = None,
    ) -> list[dict[str, Any]]:
        selectors = [
            "bioops.dev/workload=submit-master"
        ]

        if batch_id:
            value = self._label_value(batch_id)
            selectors.append(
                f"{self.batch_label}={value}"
            )

        if sample_id:
            value = self._label_value(sample_id)
            selectors.append(
                f"{self.sample_label}={value}"
            )

        if not batch_id and not sample_id:
            raise ValueError(
                "batch_id or sample_id is required"
            )

        workflows: list[dict[str, Any]] = []
        token: str | None = None

        while True:
            arguments: dict[str, Any] = {
                "group": "argoproj.io",
                "version": "v1alpha1",
                "namespace": self.namespace,
                "plural": "workflows",
                "label_selector": ",".join(selectors),
                "limit": self.workflow_page_size,
            }

            if token:
                arguments["_continue"] = token

            response = (
                self._custom_api()
                .list_namespaced_custom_object(
                    **arguments
                )
            )

            workflows.extend(
                response.get("items", [])
                or []
            )

            token = (
                response.get("metadata", {})
                .get("continue")
                or None
            )

            if not token:
                break

        workflows.sort(
            key=lambda workflow: (
                workflow.get("metadata", {}).get(
                    "creationTimestamp",
                    "",
                )
            ),
            reverse=True,
        )

        return workflows

    def _list_pods(
        self,
        workflow_name: str,
    ) -> list[Any]:
        pods: list[Any] = []
        token: str | None = None

        while True:
            arguments: dict[str, Any] = {
                "namespace": self.namespace,
                "label_selector": (
                    "workflows.argoproj.io/workflow="
                    f"{workflow_name}"
                ),
                "limit": self.pod_page_size,
            }

            if token:
                arguments["_continue"] = token

            response = (
                self._core_api()
                .list_namespaced_pod(**arguments)
            )

            pods.extend(response.items)

            token = getattr(
                response.metadata,
                "_continue",
                None,
            )

            if not token:
                return pods

    def _snapshot(
        self,
        workflow: dict[str, Any],
    ) -> dict[str, Any]:
        status = workflow.get("status", {}) or {}
        phase = status.get("phase") or "Unknown"
        active_steps: Counter[str] = Counter()

        nodes = status.get("nodes", {}) or {}

        for node in nodes.values():
            if node.get("type") in {
                "DAG",
                "Steps",
                "Skipped",
            }:
                continue

            if node.get("phase") in {
                "Running",
                "Pending",
                "Failed",
                "Error",
            }:
                step = self._classify_step(node)
                active_steps[step] += 1

        if active_steps:
            current_step = (
                active_steps.most_common(1)[0][0]
            )
        elif phase == "Succeeded":
            current_step = "completed"
        else:
            current_step = "unknown"

        metadata = workflow.get("metadata", {})

        return {
            "name": metadata.get("name", "unknown"),
            "batch": self._label(
                workflow,
                self.batch_label,
            ),
            "sample": self._label(
                workflow,
                self.sample_label,
            ),
            "attempt": (
                self._label(
                    workflow,
                    "bioops.dev/attempt",
                )
                or "0"
            ),
            "phase": phase,
            "step": current_step,
            "runtime": self._runtime_minutes(workflow),
        }

    @staticmethod
    def _runtime_minutes(
        workflow: dict[str, Any],
    ) -> float | None:
        status = workflow.get("status", {}) or {}
        started_at = status.get("startedAt")

        if not started_at:
            return None

        start = datetime.fromisoformat(
            started_at.replace("Z", "+00:00")
        )

        finished_at = status.get("finishedAt")

        if finished_at:
            end = datetime.fromisoformat(
                finished_at.replace(
                    "Z",
                    "+00:00",
                )
            )
        else:
            end = datetime.now(timezone.utc)

        return max(
            (end - start).total_seconds() / 60,
            0.0,
        )

    def _runtime_statistics(
        self,
        snapshots: list[dict[str, Any]],
        runtimes: list[float],
    ) -> list[str]:
        if not runtimes:
            return ["- No runtime data available."]

        ordered = sorted(runtimes)

        if len(ordered) == 1:
            q1 = median = q3 = ordered[0]
        else:
            q1, median, q3 = quantiles(
                ordered,
                n=4,
                method="inclusive",
            )

        timed = [
            item
            for item in snapshots
            if item["runtime"] is not None
        ]

        shortest = min(
            timed,
            key=lambda item: item["runtime"],
        )
        longest = max(
            timed,
            key=lambda item: item["runtime"],
        )

        return [
            f"- Average: {fmean(ordered):.1f} min",
            f"- Q1: {q1:.1f} min",
            f"- Median: {median:.1f} min",
            f"- Q3: {q3:.1f} min",
            (
                f"- Shortest: {shortest['sample']} "
                f"({shortest['runtime']:.1f} min)"
            ),
            (
                f"- Longest: {longest['sample']} "
                f"({longest['runtime']:.1f} min)"
            ),
        ]

    @staticmethod
    def _percentages(
        counts: Counter,
        total: int,
    ) -> list[str]:
        ordered = sorted(
            counts.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )

        return [
            (
                f"- {name}: {count} "
                f"({count / total * 100:.1f}%)"
            )
            for name, count in ordered
        ]

    def _custom_api(self) -> Any:
        if self._custom_api_override is not None:
            return self._custom_api_override

        return super()._custom_objects_api()

    def _core_api(self) -> Any:
        if self._core_api_override is not None:
            return self._core_api_override

        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        self._core_api_override = client.CoreV1Api()
        return self._core_api_override

    @staticmethod
    def _label(
        workflow: dict[str, Any],
        name: str,
    ) -> str:
        labels = (
            workflow.get("metadata", {})
            .get("labels", {})
            or {}
        )
        return str(labels.get(name) or "")

    @staticmethod
    def _label_value(value: str) -> str:
        cleaned = value.strip()

        if not LABEL_VALUE.fullmatch(cleaned):
            raise ValueError(
                "Invalid Kubernetes label value: "
                f"{value!r}"
            )

        return cleaned

    @staticmethod
    def _minutes(
        value: float | None,
    ) -> str:
        if value is None:
            return "unknown"

        return f"{value:.1f} min"

    @staticmethod
    def _error(
        scope: str,
        value: str,
        error: Exception,
    ) -> str:
        return (
            f"SubmitMaster {scope} status "
            "is unavailable.\n\n"
            f"Requested {scope}: {value}\n"
            f"Reason: {error}"
        )
