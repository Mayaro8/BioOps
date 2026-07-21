from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.jobs.submit_master_d5_retry_bitrix_report import (
    assess_workflow_retry,
    render_d5_report,
)
from bioops.tools.llm_action_router import (
    LLMActionRouter,
    format_action_routing_error,
)
from bioops.tools.submit_master_scope import (
    SubmitMasterScopeMonitor,
)
from bioops.tools.submit_master_launcher import (
    MockLaunchTarget,
    SubmitMasterWorkflowLauncher,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "agents.yaml"
)


class SubmitMasterAgent(BaseAgent):
    """SubmitMaster operations agent for Epic D."""

    name = "submit_master"
    description = (
        "Launches processing and performs confirmed targeted retries."
    )
    MULTI_LAUNCH_CONFIRMATION_PREFIX = "CONFIRM MOCK MULTI-LAUNCH "

    def __init__(
        self,
        config_path: Path = AGENTS_CONFIG_PATH,
        action_router: LLMActionRouter | None = None,
    ) -> None:
        config = self._load_config(config_path)
        submit = (
            config.get("agents", {})
            .get("submit_master", {})
        )

        namespace = submit.get(
            "argo_namespace",
            "argo",
        )
        template = submit.get(
            "argo_workflow_template",
            "bioops-submit-master-local",
        )
        prefix = submit.get(
            "workflow_name_prefix",
            "bioops-submit-master",
        )

        self.launcher = SubmitMasterWorkflowLauncher(
            namespace=submit.get("launch_namespace", namespace),
            template_name=submit.get(
                "launch_workflow_template",
                "argo-submit-workflow",
            ),
        )

        self.monitor = SubmitMasterScopeMonitor(
            namespace=namespace,
            workflow_name_prefix=prefix,
            workflow_template_name=template,
            step_patterns=submit.get("step_patterns"),
            batch_label=submit.get(
                "batch_label",
                "bioops.dev/batch-id",
            ),
            sample_label=submit.get(
                "sample_label",
                "bioops.dev/sample-id",
            ),
            workflow_page_size=int(
                submit.get("workflow_page_size", 100)
            ),
            pod_page_size=int(
                submit.get("pod_page_size", 200)
            ),
            max_listed_items=int(
                submit.get("max_listed_items", 10)
            ),
        )

        self.d4_namespace = namespace
        self.d4_workflow_prefix = submit.get(
            "d4_workflow_prefix",
            prefix,
        )
        self.d4_workflow_template = submit.get(
            "d4_workflow_template",
            template,
        )
        self.d5_max_retries = int(
            submit.get("d5_max_retries", 2)
        )
        self.max_launch_targets = max(
            1,
            int(submit.get("max_launch_targets", 20)),
        )

        self.action_router = (
            action_router
            or self._build_action_router()
        )

    def run(self, message: str) -> str:
        if message.strip().startswith(
            self.MULTI_LAUNCH_CONFIRMATION_PREFIX
        ):
            serialized = message.strip().removeprefix(
                self.MULTI_LAUNCH_CONFIRMATION_PREFIX
            )
            try:
                raw_targets = json.loads(serialized)
            except json.JSONDecodeError as error:
                return (
                    "SubmitMaster multi-cluster confirmation is invalid.\n\n"
                    f"Reason: invalid JSON: {error.msg}\n"
                    "No workflow was created."
                )
            return self._launch_multiple_mock_pipelines(
                message,
                raw_targets,
            )

        try:
            decision = self.action_router.route(message)
        except Exception as error:
            return format_action_routing_error(
                "SubmitMaster Agent",
                error,
            )

        parameters = decision.parameters

        if decision.action == "launch_submit_master":
            return self._launch_mock_pipeline(message, parameters)

        if decision.action == "retry_sample":
            return self._retry_sample(
                message,
                parameters,
            )

        return self._help()

    def _launch_mock_pipeline(
        self,
        message: str,
        parameters: dict[str, Any],
    ) -> str:
        raw_targets = parameters.get("launch_targets")
        if raw_targets is not None:
            return self._launch_multiple_mock_pipelines(
                message,
                raw_targets,
            )

        batch_id = self._parameter(parameters, "batch_id")
        input_prefix = self._parameter(parameters, "input_prefix")
        cluster_context = self._parameter(parameters, "cluster_context")
        namespace = self._parameter(parameters, "namespace")
        raw_stage = parameters.get("stage")
        stage = str(raw_stage).strip() if raw_stage is not None else "all"
        if not batch_id or not input_prefix:
            return (
                "Mock launch requires batch_id and input_prefix.\n"
                "No workflow was created."
            )
        confirmation = f"CONFIRM MOCK LAUNCH {batch_id} {input_prefix} {stage}"
        if cluster_context or namespace:
            confirmation = (
                f"{confirmation} {cluster_context or 'current'} "
                f"{namespace or self.launcher.namespace}"
            )
        if message.strip() != confirmation:
            return "\n".join([
                "SubmitMaster Mock Launch Assessment",
                "",
                f"Batch: {batch_id}",
                f"Input prefix: {input_prefix}",
                f"Stage: {stage}",
                f"Cluster: {cluster_context or 'current'}",
                f"Namespace: {namespace or self.launcher.namespace}",
                "Plan: discover batch files -> Config Creator -> Submit Master -> sample workflows",
                "No workflow was created.",
                "Send exactly to launch:",
                confirmation,
            ])

        try:
            return self.launcher.launch_mock(
                batch_id=batch_id,
                input_prefix=input_prefix,
                stage=stage,
                cluster_context=cluster_context,
                namespace=namespace,
            )
        except Exception as error:
            return (
                "SubmitMaster launch failed.\n\n"
                f"Reason: {type(error).__name__}: {error}\n"
                "The API did not confirm workflow creation."
            )

    def _launch_multiple_mock_pipelines(
        self,
        message: str,
        raw_targets: Any,
    ) -> str:
        try:
            targets = self._parse_launch_targets(raw_targets)
        except ValueError as error:
            return (
                "SubmitMaster multi-cluster launch is invalid.\n\n"
                f"Reason: {error}\n"
                "No workflow was created."
            )

        serialized = json.dumps(
            [
                {
                    "batch_id": target.batch_id,
                    "cluster_context": target.cluster_context,
                    "input_prefix": target.input_prefix,
                    "namespace": target.namespace,
                    "stage": target.stage,
                }
                for target in targets
            ],
            separators=(",", ":"),
            sort_keys=True,
        )
        confirmation = (
            f"{self.MULTI_LAUNCH_CONFIRMATION_PREFIX}{serialized}"
        )
        if message.strip() != confirmation:
            lines = [
                "SubmitMaster Multi-Cluster Launch Assessment",
                "",
                f"Targets: {len(targets)}",
            ]
            for target in targets:
                lines.append(
                    "- "
                    f"{target.cluster_context or 'current'}/"
                    f"{target.namespace or self.launcher.namespace}: "
                    f"{target.batch_id}, {target.input_prefix}, "
                    f"stage {target.stage}"
                )
            lines.extend(
                [
                    "No workflow was created.",
                    "Send exactly to launch all targets:",
                    confirmation,
                ]
            )
            return "\n".join(lines)

        return self.launcher.launch_mock_many(targets)

    def _parse_launch_targets(
        self,
        raw_targets: Any,
    ) -> list[MockLaunchTarget]:
        if not isinstance(raw_targets, list) or not raw_targets:
            raise ValueError("launch_targets must be a non-empty JSON array")

        limit = getattr(self, "max_launch_targets", 20)
        if len(raw_targets) > limit:
            raise ValueError(
                f"launch_targets exceeds the configured limit of {limit}"
            )

        targets: list[MockLaunchTarget] = []
        seen: set[tuple[str | None, str | None, str]] = set()
        for index, raw_target in enumerate(raw_targets, start=1):
            if not isinstance(raw_target, dict):
                raise ValueError(f"target {index} must be an object")

            def value(name: str) -> str | None:
                raw_value = raw_target.get(name)
                if raw_value is None:
                    return None
                if not isinstance(raw_value, str) or not raw_value.strip():
                    raise ValueError(
                        f"target {index} field {name} must be a non-empty string"
                    )
                return raw_value.strip()

            batch_id = value("batch_id")
            input_prefix = value("input_prefix")
            if not batch_id or not input_prefix:
                raise ValueError(
                    f"target {index} requires batch_id and input_prefix"
                )

            stage = value("stage") or "all"
            cluster_context = value("cluster_context")
            namespace = value("namespace")
            identity = (cluster_context, namespace, batch_id)
            if identity in seen:
                raise ValueError(
                    f"target {index} duplicates batch {batch_id} in the same cluster"
                )
            seen.add(identity)
            targets.append(
                MockLaunchTarget(
                    batch_id=batch_id,
                    input_prefix=input_prefix,
                    stage=stage,
                    cluster_context=cluster_context,
                    namespace=namespace,
                )
            )

        return targets

    def _retry_sample(
        self,
        message: str,
        parameters: dict[str, Any],
    ) -> str:
        workflow_name = self._selected_workflow(
            parameters
        )

        if workflow_name.startswith("ERROR: "):
            return workflow_name.removeprefix(
                "ERROR: "
            )

        confirmation = (
            f"CONFIRM RETRY {workflow_name}"
        )

        if message.strip() == confirmation:
            return render_d5_report(
                namespace=self.d4_namespace,
                workflow_prefix=(
                    self.d4_workflow_prefix
                ),
                workflow_template=(
                    self.d4_workflow_template
                ),
                auto_retry=True,
                max_retries=self.d5_max_retries,
                force_retry=False,
                workflow_name=workflow_name,
            )

        try:
            retryable, reason = assess_workflow_retry(
                namespace=self.d4_namespace,
                workflow_name=workflow_name,
            )
        except Exception as error:
            return (
                "SubmitMaster D5 assessment failed."
                "\n\n"
                f"Workflow: {workflow_name}\n"
                f"Reason: {error}\n"
                "No retry was created."
            )

        report = [
            "SubmitMaster D5 Targeted Retry Assessment",
            "",
            f"Workflow: {workflow_name}",
            (
                "Retryable: yes"
                if retryable
                else "Retryable: no"
            ),
            f"Decision: {reason}",
            "No retry was created.",
        ]

        if retryable:
            report.extend([
                "",
                "Send exactly to retry:",
                confirmation,
            ])

        return "\n".join(report)

    def _selected_workflow(
        self,
        parameters: dict[str, Any],
    ) -> str:
        workflow_name = self._parameter(
            parameters,
            "workflow_name",
        )

        if workflow_name:
            return workflow_name

        sample_id = self._parameter(
            parameters,
            "sample_id",
        )

        if not sample_id:
            return (
                "ERROR: Select an explicit "
                "workflow_name or sample_id before "
                "D4/D5. No workflow was changed."
            )

        try:
            workflow = (
                self.monitor.resolve_sample_workflow(
                    sample_id=sample_id,
                    batch_id=self._parameter(
                        parameters,
                        "batch_id",
                    ),
                )
            )
        except Exception as error:
            return f"ERROR: {error}"

        result = str(
            workflow.get("metadata", {}).get(
                "name",
                "",
            )
        )

        if not result:
            return (
                "ERROR: Selected workflow has no "
                "metadata.name."
            )

        return result

    @staticmethod
    def _build_action_router() -> LLMActionRouter:
        return LLMActionRouter(
            agent_name="SubmitMaster Agent",
            actions={
                "launch_submit_master": (
                    "Assess or confirm one or many SubmitMaster launches using "
                    "Config Creator inputs, including launches across kube contexts."
                ),
                "retry_sample": (
                    "Assess or confirm one targeted "
                    "sample retry."
                ),
                "help": "Explain supported actions.",
            },
            parameter_schema={
                "batch_id": (
                    "Exact batch ID from the request "
                    "or null."
                ),
                "sample_id": (
                    "Exact sample ID from the request "
                    "or null."
                ),
                "workflow_name": (
                    "Exact workflow name from the "
                    "request or null."
                ),
                "input_prefix": "Exact mock batch directory under /mock-data/ or null.",
                "stage": "all, 1, 2, or 3; use all when omitted.",
                "cluster_context": (
                    "Exact kube context for a single launch or null for the "
                    "current cluster."
                ),
                "namespace": (
                    "Exact Kubernetes namespace for a single launch or null "
                    "for the configured namespace."
                ),
                "launch_targets": (
                    "For a multi-batch or multi-cluster launch, an exact JSON "
                    "array of objects with batch_id, input_prefix, stage, "
                    "cluster_context, and optional namespace; otherwise null."
                ),
            },
            rules=[
                (
                    "Choose launch_submit_master for launch, start, or submit requests; "
                    "batch_id and input_prefix are required and must never be invented."
                ),
                (
                    "For multiple batches or clusters, return launch_targets "
                    "with one object per batch/cluster pair. Preserve every "
                    "exact kube-context, namespace, path, and stage."
                ),
                (
                    "Choose retry_sample for retry, "
                    "restart, or resubmit requests."
                ),
                "Status and progress queries belong to Batch Status, not this agent.",
                "Never invent identifiers.",
            ],
            examples=[
                {
                    "request": (
                        "Launch batch B1 from /mock-data/B1 in cluster-a and "
                        "batch B2 from /mock-data/B2 in cluster-b"
                    ),
                    "action": "launch_submit_master",
                    "parameters": {
                        "launch_targets": [
                            {
                                "batch_id": "B1",
                                "input_prefix": "/mock-data/B1",
                                "stage": "all",
                                "cluster_context": "cluster-a",
                                "namespace": None,
                            },
                            {
                                "batch_id": "B2",
                                "input_prefix": "/mock-data/B2",
                                "stage": "all",
                                "cluster_context": "cluster-b",
                                "namespace": None,
                            },
                        ]
                    },
                    "reason": "Assess two launches across two kube contexts.",
                },
                {
                    "request": (
                        "Retry sample S927 in batch B104"
                    ),
                    "action": "retry_sample",
                    "parameters": {
                        "batch_id": "B104",
                        "sample_id": "S927",
                        "workflow_name": None,
                    },
                    "reason": (
                        "Assess one sample before retry."
                    ),
                },
            ],
        )

    @staticmethod
    def _parameter(
        parameters: dict[str, Any],
        name: str,
    ) -> str | None:
        value = parameters.get(name)

        if not isinstance(value, str):
            return None

        return value.strip() or None

    @staticmethod
    def _help() -> str:
        return (
            "SubmitMaster Agent\n\n"
            "- Discover a batch and launch per-sample FASTQ workflows after confirmation\n"
            "- Launch multiple batches across configured kube contexts with one confirmation\n"
            "- Assess and explicitly confirm "
            "a targeted retry\n"
            "- Use Batch Status for all status and progress queries"
        )

    @staticmethod
    def _load_config(
        path: Path,
    ) -> dict[str, Any]:
        if not path.exists():
            return {}

        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return yaml.safe_load(handle) or {}
