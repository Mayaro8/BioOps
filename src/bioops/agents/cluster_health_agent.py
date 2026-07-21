from pathlib import Path
from statistics import fmean, quantiles
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.cost_tool import CostTool
from bioops.tools.eta_tool import ETATool
from bioops.tools.k8s_health import (
    K8sHealthTool,
    NodePressureReport,
    PodStatus,
)
from bioops.tools.llm_action_router import (
    LLMActionRouter,
    format_action_routing_error,
)
from bioops.tools.pod_error_analysis import analyze_pod_errors


class ClusterHealthAgent(BaseAgent):
    """Report Argo workflow health from its Kubernetes pods."""

    name = "cluster_health"
    description = (
        "Reports workflow pod phases, active steps, errors, runtime, cost, "
        "and ETA."
    )

    def __init__(
        self,
        health_tool: K8sHealthTool | None = None,
        config_path: str = "configs/agents.yaml",
        action_router: LLMActionRouter | None = None,
    ) -> None:
        self.config = self._load_config(config_path)
        cluster_config = self.config.get("agents", {}).get(
            "cluster_health",
            {},
        )

        self.health_tool = health_tool or K8sHealthTool(
            namespace=cluster_config.get("namespace", "bioops"),
            request_timeout_seconds=cluster_config.get(
                "request_timeout_seconds",
                5,
            ),
            log_tail_lines=cluster_config.get("log_tail_lines", 50),
            recent_error_minutes=cluster_config.get(
                "recent_error_minutes",
                60,
            ),
        )

        self.cost_tool = CostTool(cluster_config.get("cost", {}))
        self.eta_tool = ETATool(
            cluster_config.get("step_eta_minutes", {})
        )
        self.error_report_limit = max(
            1,
            int(cluster_config.get("error_report_limit", 20)),
        )
        self.max_batches = max(
            1,
            int(cluster_config.get("max_batches", 10)),
        )
        self.action_router = action_router or self._build_action_router()

    def run(self, message: str) -> str:
        try:
            decision = self.action_router.route(message)
        except Exception as error:
            return format_action_routing_error(
                "Cluster Health Agent",
                error,
            )

        if decision.action == "help":
            return self._help()

        try:
            if decision.action == "recent_errors":
                errors = self.health_tool.get_recent_errors(
                    limit=self.error_report_limit,
                )
                return self.format_analyzed_errors(errors)

            if decision.action == "node_pressure":
                return self._format_node_pressure_report(
                    self.health_tool.get_node_pressure_report()
                )

            pods = self.health_tool.get_pods()

            if decision.action == "pod_statuses":
                return self._format_pod_status_report(pods)

            if decision.action == "running_steps":
                return self._format_running_steps_report(pods)

            if decision.action == "cost_eta":
                return self._format_cost_eta_report(pods)

            errors = self.health_tool.get_recent_errors(
                limit=self.error_report_limit,
            )
            return self.format_overall_health(pods, errors)
        except Exception as error:
            if decision.action == "node_pressure":
                return (
                    "Kubernetes Node Pressure Report\n\n"
                    "Overall status: Unavailable\n"
                    f"Reason: failed to query Kubernetes nodes: {error}"
                )

            cost_report = self.cost_tool.estimate_cluster_cost(
                runtime_minutes=0.0
            )
            currency = str(cost_report.currency).upper()

            return (
                "Workflow Health Report\n\n"
                "Overall status: Unavailable\n"
                f"Reason: failed to query workflow pods: {error}\n\n"
                "Cost:\n"
                f"- Estimated cost: "
                f"{cost_report.total_cost_usd:.2f} {currency}\n"
                f"- Mode: {cost_report.mode}"
            )

    @staticmethod
    def _build_action_router() -> LLMActionRouter:
        return LLMActionRouter(
            agent_name="Cluster Health Agent",
            actions={
                "overall_health": (
                    "Return workflow health aggregated by batch, including "
                    "workflow states, pod phases, running steps, errors, cost, "
                    "and ETA."
                ),
                "pod_statuses": (
                    "Return batch-level workflow and pod-phase counts and "
                    "percentages."
                ),
                "running_steps": (
                    "Return running pipeline steps grouped by batch, with "
                    "pod counts and percentages."
                ),
                "recent_errors": (
                    "Return analyzed recent workflow pod and container errors."
                ),
                "cost_eta": (
                    "Return cost and ETA grouped by active batch."
                ),
                "node_pressure": (
                    "Return Kubernetes worker-node readiness, resource "
                    "pressure, capacity, usage, and workflow scheduling "
                    "blockers."
                ),
                "help": "Explain the read-only workflow health capabilities.",
            },
            rules=[
                "This agent is read-only and must never restart or delete pods.",
                (
                    "Choose overall_health for broad workflow execution health "
                    "requests."
                ),
                (
                    "Choose pod_statuses for requests about a workflow's pods "
                    "or pod phases."
                ),
                (
                    "Choose running_steps for requests specifically about "
                    "current pipeline steps."
                ),
                (
                    "Choose recent_errors for failed pods, logs, errors, or "
                    "diagnosis."
                ),
                (
                    "Choose cost_eta when cost or completion ETA is the main "
                    "request."
                ),
                (
                    "Choose node_pressure for node readiness, MemoryPressure, "
                    "DiskPressure, PIDPressure, resource capacity, or "
                    "unschedulable pods."
                ),
                (
                    "Treat master node report, control-plane report, node "
                    "health report, and cluster capacity report as "
                    "node_pressure requests."
                ),
            ],
            examples=[
                {
                    "request": "How healthy are the running workflows?",
                    "action": "overall_health",
                    "parameters": {},
                    "reason": "The user requested workflow execution health.",
                },
                {
                    "request": "What pipeline steps are running now?",
                    "action": "running_steps",
                    "parameters": {},
                    "reason": "The request is specifically about active steps.",
                },
                {
                    "request": "Why did a pod fail?",
                    "action": "recent_errors",
                    "parameters": {},
                    "reason": "The request asks for failed-pod diagnosis.",
                },
                {
                    "request": "Are the Kubernetes nodes under pressure?",
                    "action": "node_pressure",
                    "parameters": {},
                    "reason": "The request asks about worker-node pressure.",
                },
                {
                    "request": "Show master node report",
                    "action": "node_pressure",
                    "parameters": {},
                    "reason": (
                        "The request asks for the available Kubernetes API "
                        "and visible node health report."
                    ),
                },
            ],
        )

    @staticmethod
    def _format_node_pressure_report(report: NodePressureReport) -> str:
        total_nodes = len(report.nodes)

        def count(attribute: str) -> int:
            return sum(
                1 for node in report.nodes if getattr(node, attribute)
            )

        def percentage(value: int, total: int) -> float:
            return value / total * 100 if total else 0.0

        ready = count("ready")
        not_ready = total_nodes - ready
        memory_pressure = count("memory_pressure")
        disk_pressure = count("disk_pressure")
        pid_pressure = count("pid_pressure")
        network_unavailable = count("network_unavailable")
        degraded = any(
            (
                not_ready,
                memory_pressure,
                disk_pressure,
                pid_pressure,
                network_unavailable,
                report.unschedulable_workflow_pods,
            )
        )

        def metric(value: float | None) -> str:
            return f"{value:.1f}%" if value is not None else "Unavailable"

        lines = [
            "Kubernetes Node Pressure Report",
            "",
            f"Overall status: {'Degraded' if degraded else 'Healthy'}",
            "Kubernetes API: Available",
            (
                "Scope: Kubernetes API and visible worker nodes; managed "
                "control-plane internals are provider-managed."
            ),
            f"Nodes observed: {total_nodes}",
            f"Ready nodes: {ready} ({percentage(ready, total_nodes):.1f}%)",
            (
                f"NotReady nodes: {not_ready} "
                f"({percentage(not_ready, total_nodes):.1f}%)"
            ),
            "",
            "Resource pressure:",
            (
                f"- MemoryPressure: {memory_pressure} nodes "
                f"({percentage(memory_pressure, total_nodes):.1f}%)"
            ),
            (
                f"- DiskPressure: {disk_pressure} nodes "
                f"({percentage(disk_pressure, total_nodes):.1f}%)"
            ),
            (
                f"- PIDPressure: {pid_pressure} nodes "
                f"({percentage(pid_pressure, total_nodes):.1f}%)"
            ),
            (
                f"- NetworkUnavailable: {network_unavailable} nodes "
                f"({percentage(network_unavailable, total_nodes):.1f}%)"
            ),
            "",
            "Capacity:",
            f"- CPU usage: {metric(report.cpu_usage_percent)}",
            f"- Memory usage: {metric(report.memory_usage_percent)}",
            (
                f"- Metrics coverage: {report.metrics_nodes}/{total_nodes} "
                "nodes"
            ),
            (
                f"- Pod capacity: {report.active_pods}/"
                f"{report.pod_capacity} active pods "
                f"({percentage(report.active_pods, report.pod_capacity):.1f}%)"
            ),
            "",
            "Scheduling impact:",
            (
                "- Unschedulable workflow pods: "
                f"{report.unschedulable_workflow_pods}"
            ),
        ]

        for reason, reason_count in sorted(
            report.scheduling_reasons.items()
        ):
            lines.append(
                f"- {reason}: {reason_count} pods "
                f"({percentage(reason_count, report.unschedulable_workflow_pods):.1f}%)"
            )

        lines.extend(
            [
                "",
                "Recommended action:",
                (
                    "Review node conditions and scheduling capacity before "
                    "submitting more workflows."
                    if degraded
                    else "No node-pressure intervention is currently needed."
                ),
            ]
        )
        return "\n".join(lines)

    def _load_config(self, config_path: str) -> dict[str, Any]:
        path = Path(config_path)

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    @staticmethod
    def _is_workflow_pod(pod: PodStatus) -> bool:
        return bool(pod.workflow_name or pod.pipeline_step)

    def _workflow_pods(
        self,
        pods: list[PodStatus],
    ) -> list[PodStatus]:
        return [pod for pod in pods if self._is_workflow_pod(pod)]

    @staticmethod
    def _workflow_name(pod: PodStatus) -> str:
        return pod.workflow_name or "unassigned-workflow"

    def _workflow_groups(
        self,
        pods: list[PodStatus],
    ) -> list[tuple[str, list[PodStatus]]]:
        grouped: dict[str, list[PodStatus]] = {}

        for pod in self._workflow_pods(pods):
            grouped.setdefault(
                self._workflow_name(pod),
                [],
            ).append(pod)

        phase_priority = {
            "Failed": 0,
            "Unknown": 1,
            "Pending": 2,
            "Running": 3,
            "Succeeded": 4,
        }

        for workflow_pods in grouped.values():
            workflow_pods.sort(
                key=lambda pod: (
                    phase_priority.get(pod.phase, 5),
                    pod.name,
                )
            )

        return sorted(
            grouped.items(),
            key=lambda item: (
                min(
                    phase_priority.get(pod.phase, 5)
                    for pod in item[1]
                ),
                item[0],
            ),
        )

    def _batch_groups(
        self,
        pods: list[PodStatus],
    ) -> list[tuple[str, list[PodStatus]]]:
        grouped: dict[str, list[PodStatus]] = {}

        for _, workflow_pods in self._workflow_groups(pods):
            batch_ids = sorted(
                {pod.batch_id for pod in workflow_pods if pod.batch_id}
            )
            batch_id = batch_ids[0] if batch_ids else "unlabeled"
            grouped.setdefault(batch_id, []).extend(workflow_pods)

        return sorted(grouped.items())

    @staticmethod
    def _workflow_state(pods: list[PodStatus]) -> str:
        phases = {pod.phase or "Unknown" for pod in pods}

        if phases & {"Failed", "Unknown"}:
            return "Failed"
        if "Running" in phases:
            return "Running"
        if "Pending" in phases:
            return "Pending"
        if phases == {"Succeeded"}:
            return "Succeeded"
        return "Unknown"

    def _format_workflow_state_section(
        self,
        pods: list[PodStatus],
    ) -> list[str]:
        states: dict[str, int] = {}
        groups = self._workflow_groups(pods)

        for _, workflow_pods in groups:
            state = self._workflow_state(workflow_pods)
            states[state] = states.get(state, 0) + 1

        total = len(groups)
        if not total:
            return ["- No workflows found."]

        return [
            (
                f"- {state}: {count} "
                f"{'workflow' if count == 1 else 'workflows'} "
                f"({count / total * 100:.1f}% of workflows)"
            )
            for state, count in sorted(states.items())
        ]

    def _format_pipeline_section(
        self,
        pipeline_pods: list[PodStatus],
    ) -> list[str]:
        total_pods = len(pipeline_pods)
        pods_by_step: dict[str, int] = {}

        for pod in pipeline_pods:
            step = pod.pipeline_step or "unknown"
            pods_by_step[step] = pods_by_step.get(step, 0) + 1

        return [
            (
                f"- {step}: {count} {'pod' if count == 1 else 'pods'} "
                f"({count / total_pods * 100:.1f}% of active workflow pods)"
            )
            for step, count in sorted(pods_by_step.items())
        ]

    @staticmethod
    def _format_pod_phase_section(
        pods: list[PodStatus],
    ) -> list[str]:
        if not pods:
            return ["- No pods found."]

        pods_by_phase: dict[str, int] = {}
        for pod in pods:
            phase = pod.phase or "Unknown"
            pods_by_phase[phase] = pods_by_phase.get(phase, 0) + 1

        total_pods = len(pods)
        return [
            (
                f"- {phase}: {count} {'pod' if count == 1 else 'pods'} "
                f"({count / total_pods * 100:.1f}% of workflow pods)"
            )
            for phase, count in sorted(pods_by_phase.items())
        ]

    def _running_pipeline_pods(
        self,
        pods: list[PodStatus],
    ) -> list[PodStatus]:
        return [
            pod
            for pod in self._workflow_pods(pods)
            if pod.phase == "Running"
            and pod.pipeline_step
        ]

    def _format_batch_sections(
        self,
        pods: list[PodStatus],
    ) -> list[str]:
        groups = self._batch_groups(pods)

        if not groups:
            return ["", "- No Argo workflow pods found."]

        lines: list[str] = []

        for batch_id, batch_pods in groups[: self.max_batches]:
            workflow_count = len(self._workflow_groups(batch_pods))
            sample_count = len(
                {pod.sample_id for pod in batch_pods if pod.sample_id}
            )
            lines.extend(
                [
                    "",
                    f"Batch: {batch_id}",
                    f"Workflows: {workflow_count}",
                    f"Samples represented: {sample_count}",
                    f"Workflow pods: {len(batch_pods)}",
                    "Workflow states:",
                    *self._format_workflow_state_section(batch_pods),
                ]
            )

            lines.extend(
                [
                    "Pod phases:",
                    *self._format_pod_phase_section(batch_pods),
                    "Current steps:",
                ]
            )

            running_pods = self._running_pipeline_pods(batch_pods)

            if running_pods:
                lines.extend(self._format_pipeline_section(running_pods))
                lines.extend(
                    self._format_runtime_statistics_section(running_pods)
                )
            else:
                lines.append("- No running pipeline steps.")

        hidden_batches = len(groups) - self.max_batches
        if hidden_batches > 0:
            lines.extend(
                ["", f"... {hidden_batches} more batches not listed"]
            )

        return lines

    def _format_pod_status_report(
        self,
        pods: list[PodStatus],
    ) -> str:
        workflow_pods = self._workflow_pods(pods)
        groups = self._workflow_groups(workflow_pods)
        batches = self._batch_groups(workflow_pods)
        samples = {pod.sample_id for pod in workflow_pods if pod.sample_id}

        return "\n".join(
            [
                "Workflow Pod Status Report",
                "",
                f"Batches represented: {len(batches)}",
                f"Workflows observed: {len(groups)}",
                f"Samples represented: {len(samples)}",
                f"Total workflow pods: {len(workflow_pods)}",
                *self._format_batch_sections(workflow_pods),
                "",
                (
                    "Possible Kubernetes phases: Pending, Running, Succeeded, "
                    "Failed, Unknown."
                ),
            ]
        )

    def _format_running_steps_report(
        self,
        pods: list[PodStatus],
    ) -> str:
        pipeline_pods = self._running_pipeline_pods(pods)
        groups = self._workflow_groups(pipeline_pods)
        batches = self._batch_groups(pipeline_pods)
        lines = [
            "Current Workflow Pipeline Steps",
            "",
            f"Active batches: {len(batches)}",
            f"Active workflows: {len(groups)}",
            f"Running labeled pipeline pods: {len(pipeline_pods)}",
        ]

        if not pipeline_pods:
            lines.append("- No active pipeline workflows.")
            return "\n".join(lines)

        for batch_id, batch_pods in batches[: self.max_batches]:
            lines.extend(
                [
                    "",
                    f"Batch: {batch_id}",
                    (
                        "Active workflows: "
                        f"{len(self._workflow_groups(batch_pods))}"
                    ),
                    "Step distribution:",
                    *self._format_pipeline_section(batch_pods),
                    *self._format_runtime_statistics_section(batch_pods),
                ]
            )

        return "\n".join(lines)

    def _format_cost_eta_report(
        self,
        pods: list[PodStatus],
    ) -> str:
        running_pods = [
            pod
            for pod in self._workflow_pods(pods)
            if pod.phase == "Running"
        ]
        groups = self._batch_groups(running_pods)
        lines = ["Workflow Cost and ETA"]

        if not groups:
            lines.extend(["", "- No active workflow pods."])
            return "\n".join(lines)

        for batch_id, batch_pods in groups[: self.max_batches]:
            pipeline_pods = self._running_pipeline_pods(batch_pods)
            lines.extend(
                [
                    "",
                    f"Batch: {batch_id}",
                    (
                        "Active workflows: "
                        f"{len(self._workflow_groups(batch_pods))}"
                    ),
                    *self._format_cost_section(batch_pods),
                    *self._format_eta_section(pipeline_pods),
                ]
            )

        return "\n".join(lines)

    def _format_runtime_statistics_section(
        self,
        pipeline_pods: list[PodStatus],
    ) -> list[str]:
        runtime_pods = [
            pod
            for pod in pipeline_pods
            if pod.runtime_minutes is not None
        ]

        lines = ["", "Active pipeline runtime statistics:"]

        if not runtime_pods:
            lines.append("- No active pipeline runtime data.")
            return lines

        runtimes = sorted(
            float(pod.runtime_minutes)
            for pod in runtime_pods
            if pod.runtime_minutes is not None
        )

        if len(runtimes) == 1:
            q1 = q2 = q3 = runtimes[0]
        else:
            q1, q2, q3 = quantiles(
                runtimes,
                n=4,
                method="inclusive",
            )

        lines.extend(
            [
                f"- Pods measured: {len(runtime_pods)}",
                f"- Average runtime: {fmean(runtimes):.1f} min",
                f"- Q1 (25th percentile): {q1:.1f} min",
                f"- Median (Q2): {q2:.1f} min",
                f"- Q3 (75th percentile): {q3:.1f} min",
                f"- Minimum runtime: {runtimes[0]:.1f} min",
                f"- Maximum runtime: {runtimes[-1]:.1f} min",
            ]
        )

        return lines

    def _estimate_report_cost(
        self,
        running_pods: list[PodStatus],
    ) -> Any:
        max_runtime_minutes = max(
            [pod.runtime_minutes or 0.0 for pod in running_pods],
            default=0.0,
        )

        return self.cost_tool.estimate_cluster_cost(
            runtime_minutes=max_runtime_minutes,
        )

    def _format_cost_section(
        self,
        running_pods: list[PodStatus],
    ) -> list[str]:
        report = self._estimate_report_cost(running_pods)
        currency = str(report.currency).upper()

        return [
            "",
            "Cost:",
            f"- Estimated cost: "
            f"{report.total_cost_usd:.2f} {currency}",
            f"- Mode: {report.mode}",
            f"- Note: {report.note}",
        ]

    def _format_eta_section(
        self,
        pipeline_pods: list[PodStatus],
    ) -> list[str]:
        configured_steps = set(self.eta_tool.step_eta_minutes)

        eta_pods = [
            pod
            for pod in pipeline_pods
            if pod.pipeline_step in configured_steps
        ]

        lines = ["", "ETA:"]

        if not eta_pods:
            lines.append(
                "- No active pipeline steps with a configured ETA."
            )
            return lines

        reports = self.eta_tool.estimate_for_running_pods(eta_pods)

        remaining_by_step: dict[str, list[float]] = {}

        for report in reports:
            if report.remaining_minutes is None:
                continue

            remaining_by_step.setdefault(
                report.pipeline_step,
                [],
            ).append(float(report.remaining_minutes))

        for step in sorted(remaining_by_step):
            remaining_times = remaining_by_step[step]
            pod_count = len(remaining_times)
            pod_word = "pod" if pod_count == 1 else "pods"

            lines.append(
                f"- {step}: average "
                f"~{fmean(remaining_times):.1f} min remaining "
                f"across {pod_count} {pod_word}"
            )

        if len(lines) == 2:
            lines.append("- No ETA currently available.")

        return lines

    def format_overall_health(
        self,
        pods: list[PodStatus],
        errors: list[str],
    ) -> str:
        workflow_pods = self._workflow_pods(pods)
        workflow_groups = self._workflow_groups(workflow_pods)
        batch_groups = self._batch_groups(workflow_pods)
        samples = {pod.sample_id for pod in workflow_pods if pod.sample_id}
        running_pods = [
            pod
            for pod in workflow_pods
            if pod.phase == "Running"
        ]
        overall_status = (
            "Healthy"
            if (
                not errors
                and not any(
                    pod.phase in {"Failed", "Unknown"}
                    for pod in workflow_pods
                )
            )
            else "Degraded"
        )

        lines = [
            "Workflow Health Report",
            "",
            f"Overall status: {overall_status}",
            f"Batches represented: {len(batch_groups)}",
            f"Workflows observed: {len(workflow_groups)}",
            f"Samples represented: {len(samples)}",
            f"Total workflow pods: {len(workflow_pods)}",
            *self._format_batch_sections(workflow_pods),
        ]

        lines.extend(
            [
                "",
                (
                    f"Recent workflow pod issues "
                    f"(last {self.health_tool.recent_error_minutes} min):"
                ),
            ]
        )

        if errors:
            lines.extend(f"- {error}" for error in errors[:3])
        else:
            lines.append("- None.")

        if running_pods:
            lines.extend(
                [
                    "",
                    *self._format_cost_eta_report(
                        workflow_pods
                    ).splitlines(),
                ]
            )

        return "\n".join(lines)

    def _format_report(
        self,
        pods: list[PodStatus],
        errors: list[str],
    ) -> str:
        """Compatibility alias for callers using the former private API."""

        return self.format_overall_health(pods, errors)

    @staticmethod
    def format_analyzed_errors(errors: list[str]) -> str:
        if not errors:
            return (
                "Analyzed Workflow Pod Errors\n\n"
                "No recent workflow pod errors found."
            )

        lines = [
            "Analyzed Workflow Pod Errors",
            "",
            f"Findings: {len(errors)}",
        ]
        for index, analysis in enumerate(
            analyze_pod_errors(errors),
            start=1,
        ):
            lines.extend(
                [
                    "",
                    f"{index}. Category: {analysis.category}",
                    f"   Severity: {analysis.severity}",
                    f"   Likely cause: {analysis.likely_cause}",
                    f"   Evidence: {analysis.evidence}",
                    f"   Recommended action: {analysis.recommended_action}",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _help() -> str:
        return (
            "Cluster Health Agent\n\n"
            "Supported read-only requests:\n"
            "- workflow health aggregated by batch\n"
            "- workflow and pod status counts and percentages\n"
            "- running pipeline steps per batch\n"
            "- analyzed workflow pod errors\n"
            "- configured workflow pod cost and ETA"
            "\n- Kubernetes worker-node pressure and scheduling capacity"
        )
