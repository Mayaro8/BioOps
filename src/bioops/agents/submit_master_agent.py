from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.argo_tool import ArgoTool
from bioops.tools.submit_master_failed_pods import (
    SubmitMasterFailedPodReporter,
    SubmitMasterFailedPodRequest,
)
from bioops.tools.submit_master_llm_planner import (
    SubmitMasterLLMPlanner,
    SubmitMasterPlannerDecision,
)
from bioops.tools.submit_master_monitor import (
    SubmitMasterMonitor,
    SubmitMasterMonitorRequest,
)
from bioops.tools.submit_master_tool import (
    SubmitMasterTool,
    SubmitRequest,
    SubmitPlan,
)


class SubmitMasterAgent(BaseAgent):
    """
    LLM-planned Submit Master agent.

    The agent does not use regex/key=value parsing as the primary interface.
    It asks an LLM planner to return strict JSON, compares provided vs required
    parameters, asks for missing information, and only then calls D1-D4 tools.
    """

    name = "submit_master"
    description = (
        "Plans original-compatible submit-master configs, safe launches, "
        "monitoring reports, and failed-pod reports."
    )

    def __init__(
        self,
        submit_tool: SubmitMasterTool | None = None,
        monitor: SubmitMasterMonitor | None = None,
        failed_pod_reporter: SubmitMasterFailedPodReporter | None = None,
        planner: SubmitMasterLLMPlanner | None = None,
        config_path: str = "configs/agents.yaml",
    ):
        self.config = self._load_config(config_path)
        self.submit_config = self.config.get("agents", {}).get("submit_master", {})

        argo_tool = ArgoTool(
            namespace=self.submit_config.get("argo_namespace"),
            workflow_file=self.submit_config.get("workflow_file"),
        )

        self.submit_tool = submit_tool or SubmitMasterTool(
            argo_tool=argo_tool,
            submit_master_entrypoint=self.submit_config.get("submit_master_entrypoint", ""),
            generated_config_dir=self.submit_config.get(
                "generated_config_dir",
                "logs/submit_master_configs",
            ),
            contour=self.submit_config.get("contour", "prod"),
            python_executable=self.submit_config.get("python_executable", "python3"),
            launch_timeout_seconds=int(self.submit_config.get("launch_timeout_seconds", 900)),
            allow_launch=bool(self.submit_config.get("allow_launch", False)),
        )

        self.monitor = monitor or SubmitMasterMonitor(argo_tool=argo_tool)
        self.failed_pod_reporter = failed_pod_reporter or SubmitMasterFailedPodReporter(
            argo_tool=argo_tool
        )
        self.planner = planner or SubmitMasterLLMPlanner()

    def run(self, message: str) -> str:
        try:
            decision = self.planner.plan(
                message=message,
                context=self._planner_context(),
            )
        except Exception as error:
            return self._format_planner_unavailable(error)

        if decision.intent == "restart_failed_pods":
            return self._format_d5_not_implemented(decision)

        if decision.intent == "refuse":
            return self._format_planner_refusal(decision)

        if not decision.ready:
            return self._format_missing_parameter_report(decision)

        if decision.intent == "monitor":
            report = self.monitor.monitor(self._build_monitor_request(decision))
            return self._format_generic_report(
                title="Submit Master Monitor Report",
                report=report,
            )

        if decision.intent == "failed_pods":
            report = self.failed_pod_reporter.report(
                self._build_failed_pod_request(decision)
            )
            return self._format_generic_report(
                title="Submit Master Failed Pod Report",
                report=report,
            )

        if decision.intent == "explain_config":
            return self._format_parameter_comparison(decision)

        if decision.intent == "build_or_launch":
            request = self._build_submit_request(decision)
            plan = self.submit_tool.build_plan(request)
            return self._format_report(request, plan, decision)

        return self._format_planner_refusal(
            SubmitMasterPlannerDecision(
                intent="refuse",
                ready=False,
                refusal_reason=f"Unsupported Submit Master intent: {decision.intent}",
            )
        )

    def _load_config(self, config_path: str) -> dict[str, Any]:
        path = Path(config_path)
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def _planner_context(self) -> dict[str, Any]:
        return {
            "submit_master_yaml": {
                "enabled": bool(self.submit_config.get("enabled", False)),
                "allow_launch": bool(self.submit_config.get("allow_launch", False)),
                "argo_namespace": self.submit_config.get("argo_namespace", "argo"),
                "workflow_file": self.submit_config.get("workflow_file", ""),
                "submit_master_entrypoint": self.submit_config.get(
                    "submit_master_entrypoint",
                    "",
                ),
                "generated_config_dir": self.submit_config.get(
                    "generated_config_dir",
                    "logs/submit_master_configs",
                ),
                "contour": self.submit_config.get("contour", "prod"),
                "python_executable": self.submit_config.get(
                    "python_executable",
                    "python3",
                ),
                "launch_timeout_seconds": int(
                    self.submit_config.get("launch_timeout_seconds", 900)
                ),
            },
            "intents": [
                "build_or_launch",
                "monitor",
                "failed_pods",
                "restart_failed_pods",
                "explain_config",
                "refuse",
            ],
            "required_by_intent": {
                "build_or_launch": [
                    "stage",
                    "step or steps_order",
                    "seq_type",
                    "cluster_name",
                    "namespace",
                    "sample_ids or batch_id",
                ],
                "monitor": ["batch_id or workflow_name"],
                "failed_pods": ["batch_id or workflow_name"],
                "restart_failed_pods": ["not implemented"],
            },
            "defaults": {
                "seq_type": "illumina",
                "namespace": self.submit_config.get("argo_namespace", "argo"),
                "contour": self.submit_config.get("contour", "prod"),
                "wait": True,
                "only_good": True,
                "delay": 0,
                "delay_step": 1,
                "chunk_size": 1,
                "confirm": False,
            },
            "safety": {
                "real_launch_requires_user_confirm": True,
                "real_launch_requires_yaml_allow_launch": True,
                "yaml_allow_launch": bool(self.submit_config.get("allow_launch", False)),
                "d5_restart_failed_pods_implemented": False,
            },
        }

    def _build_submit_request(self, decision: SubmitMasterPlannerDecision) -> SubmitRequest:
        params = decision.provided_parameters
        extra_params = params.get("extra_params") or {}
        if not isinstance(extra_params, dict):
            extra_params = {}

        return SubmitRequest(
            sample_id=self._string_or_none(
                params.get("sample_ids") or params.get("sample_id")
            ),
            batch_id=self._string_or_none(params.get("batch_id")),
            pipeline=self._string_or_none(params.get("pipeline")) or "pipeline-v3.0",
            step=self._string_or_none(params.get("step")),
            steps_order=self._string_or_none(params.get("steps_order")),
            stage=self._string_or_none(params.get("stage")),
            seq_type=self._string_or_none(params.get("seq_type")) or "illumina",
            cluster_name=self._string_or_none(params.get("cluster_name")),
            mongo_cluster_name=self._string_or_none(params.get("mongo_cluster_name")),
            contour=self._string_or_none(params.get("contour")),
            input_uri=self._string_or_none(params.get("input_uri")),
            output_uri=self._string_or_none(params.get("output_uri")),
            workflow_file=(
                self._string_or_none(params.get("workflow_file"))
                or self.submit_config.get("workflow_file")
            ),
            namespace=(
                self._string_or_none(params.get("namespace"))
                or self.submit_config.get("argo_namespace")
                or "default"
            ),
            wait=self._bool(params.get("wait"), default=True),
            only_good=self._bool(params.get("only_good"), default=True),
            delay=self._int(params.get("delay"), default=0),
            delay_step=self._int(params.get("delay_step"), default=1),
            chunk_size=self._int(params.get("chunk_size"), default=1),
            confirm=self._bool(params.get("confirm"), default=False),
            extra_params=extra_params,
        )

    def _build_monitor_request(
        self,
        decision: SubmitMasterPlannerDecision,
    ) -> SubmitMasterMonitorRequest:
        params = decision.provided_parameters
        return SubmitMasterMonitorRequest(
            batch_id=self._string_or_none(params.get("batch_id")),
            workflow_name=self._string_or_none(params.get("workflow_name")),
            argo_namespace=(
                self._string_or_none(params.get("argo_namespace"))
                or self.submit_config.get("argo_namespace")
                or "argo"
            ),
            k8s_namespace=(
                self._string_or_none(params.get("k8s_namespace"))
                or self._string_or_none(params.get("namespace"))
                or "bioops"
            ),
        )

    def _build_failed_pod_request(
        self,
        decision: SubmitMasterPlannerDecision,
    ) -> SubmitMasterFailedPodRequest:
        params = decision.provided_parameters
        return SubmitMasterFailedPodRequest(
            batch_id=self._string_or_none(params.get("batch_id")),
            workflow_name=self._string_or_none(params.get("workflow_name")),
            argo_namespace=(
                self._string_or_none(params.get("argo_namespace"))
                or self.submit_config.get("argo_namespace")
                or "argo"
            ),
            k8s_namespace=(
                self._string_or_none(params.get("k8s_namespace"))
                or self._string_or_none(params.get("namespace"))
                or "bioops"
            ),
        )

    def _format_report(
        self,
        request: SubmitRequest,
        plan: SubmitPlan,
        decision: SubmitMasterPlannerDecision,
    ) -> str:
        launch = plan.launch_result

        lines = [
            "Submit Master Report",
            "",
            f"Status: {plan.status}",
            "",
            "Planner decision:",
            f"- Intent: {decision.intent}",
            f"- Ready: {decision.ready}",
            f"- Explanation: {decision.explanation or 'not provided'}",
            "",
            "Parameter comparison:",
        ]

        lines.extend(self._comparison_lines(decision))

        lines.extend(
            [
                "",
                "Requested config:",
                f"- stage: {request.stage or 'not provided'}",
                f"- step/steps_order: {request.steps_order or request.step or 'not provided'}",
                f"- seq_type: {request.seq_type or 'not provided'}",
                f"- cluster_name: {request.cluster_name or 'not provided'}",
                f"- mongo_cluster_name: {request.mongo_cluster_name or 'not provided'}",
                f"- contour: {request.contour or 'config default'}",
                f"- namespace: {request.namespace or 'default'}",
                f"- sample_id/sample_ids: {request.sample_id or 'not provided'}",
                f"- batch_id: {request.batch_id or 'not provided'}",
                f"- wait: {request.wait}",
                f"- only_good: {request.only_good}",
                f"- confirm: {request.confirm}",
                "",
                "Validation:",
            ]
        )

        if plan.missing_fields:
            lines.append("- Missing or invalid fields:")
            lines.extend(f"  - {field}" for field in plan.missing_fields)
        else:
            lines.append("- Required fields are present.")

        lines.extend(
            [
                "",
                "Generated submit-master JSON config:",
                plan.config_preview,
                "",
                "D2 launch result:",
            ]
        )

        if launch is None:
            lines.append("- No launch result available.")
        else:
            lines.extend(
                [
                    f"- Launched: {launch.launched}",
                    f"- Saved config: {launch.saved_config_path or 'not saved'}",
                    f"- Command: {' '.join(launch.command) if launch.command else 'not configured'}",
                    f"- Return code: {launch.returncode if launch.returncode is not None else 'not run'}",
                    f"- Message: {launch.message}",
                ]
            )

            if launch.blocked_reason:
                lines.append(f"- Blocked reason: {launch.blocked_reason}")

            if launch.stdout:
                lines.extend(["", "Submit-master stdout:", launch.stdout.strip()])

            if launch.stderr:
                lines.extend(["", "Submit-master stderr:", launch.stderr.strip()])

        lines.extend(
            [
                "",
                "Argo preview kept for compatibility:",
                f"- Namespace: {plan.argo_preview.namespace}",
                f"- Workflow file: {plan.argo_preview.workflow_file or 'not configured'}",
                f"- Command: {plan.argo_preview.command}",
                "",
                "Submit result:",
                f"- Message: {plan.submit_result.message}",
            ]
        )

        if plan.submit_result.error:
            lines.append(f"- Error: {plan.submit_result.error}")

        if plan.argo_preview.missing_config:
            lines.extend(["", "Argo config issues:"])
            lines.extend(f"- {item}" for item in plan.argo_preview.missing_config)

        lines.extend(["", "Notes:"])
        lines.extend(f"- {item}" for item in plan.notes)

        return "\n".join(lines)

    def _format_missing_parameter_report(
        self,
        decision: SubmitMasterPlannerDecision,
    ) -> str:
        lines = [
            "Submit Master needs more information",
            "",
            f"Intent: {decision.intent}",
            f"Explanation: {decision.explanation or 'The request is incomplete.'}",
            "",
            "Parameter comparison:",
        ]

        lines.extend(self._comparison_lines(decision))

        if decision.questions:
            lines.extend(["", "Questions to complete the config:"])
            lines.extend(f"- {question}" for question in decision.questions)

        if decision.recommendations:
            lines.extend(["", "Recommendations:"])
            lines.extend(f"- {item}" for item in decision.recommendations)

        return "\n".join(lines)

    def _format_parameter_comparison(
        self,
        decision: SubmitMasterPlannerDecision,
    ) -> str:
        lines = [
            "Submit Master Config Guidance",
            "",
            f"Explanation: {decision.explanation or 'Here is what is needed.'}",
            "",
            "Parameter comparison:",
        ]

        lines.extend(self._comparison_lines(decision))

        if decision.recommendations:
            lines.extend(["", "Recommendations:"])
            lines.extend(f"- {item}" for item in decision.recommendations)

        if decision.questions:
            lines.extend(["", "Questions:"])
            lines.extend(f"- {item}" for item in decision.questions)

        return "\n".join(lines)

    def _format_planner_refusal(
        self,
        decision: SubmitMasterPlannerDecision,
    ) -> str:
        lines = [
            "Submit Master request was not executed",
            "",
            f"Intent: {decision.intent}",
            f"Reason: {decision.refusal_reason or decision.explanation or 'Request was refused by the planner.'}",
            "",
            "No config was generated.",
            "No launch was attempted.",
        ]

        if decision.questions:
            lines.extend(["", "Questions:"])
            lines.extend(f"- {question}" for question in decision.questions)

        if decision.recommendations:
            lines.extend(["", "Recommendations:"])
            lines.extend(f"- {item}" for item in decision.recommendations)

        return "\n".join(lines)

    def _format_planner_unavailable(self, error: Exception) -> str:
        return "\n".join(
            [
                "Submit Master planner unavailable",
                "",
                f"Error: {type(error).__name__}: {error}",
                "",
                "No config was generated.",
                "No launch was attempted.",
                "Configure Azure OpenAI environment variables before using the LLM-only Submit Master planner.",
            ]
        )

    def _format_d5_not_implemented(
        self,
        decision: SubmitMasterPlannerDecision,
    ) -> str:
        lines = [
            "Submit Master restart is not implemented yet",
            "",
            "D5 restart failed pods is intentionally not available in this branch.",
            "No pod or workflow was restarted.",
            "",
            "Parameter comparison:",
        ]

        lines.extend(self._comparison_lines(decision))
        return "\n".join(lines)

    def _format_generic_report(self, title: str, report: Any) -> str:
        payload = self._to_plain_data(report)

        lines = [title, ""]

        if isinstance(payload, dict):
            for key, value in payload.items():
                lines.append(f"{key}: {value}")
        else:
            lines.append(str(payload))

        return "\n".join(lines)

    def _comparison_lines(self, decision: SubmitMasterPlannerDecision) -> list[str]:
        provided = decision.provided_parameters or {}

        lines = ["- Required parameters:"]
        if decision.required_parameters:
            lines.extend(f"  - {item}" for item in decision.required_parameters)
        else:
            lines.append("  - none reported")

        lines.append("- Provided parameters:")
        meaningful_provided = {
            key: value
            for key, value in provided.items()
            if value not in {None, "", [], {}}
        }

        if meaningful_provided:
            lines.extend(f"  - {key}: {value}" for key, value in meaningful_provided.items())
        else:
            lines.append("  - none")

        lines.append("- Missing parameters:")
        if decision.missing_parameters:
            lines.extend(f"  - {item}" for item in decision.missing_parameters)
        else:
            lines.append("  - none")

        return lines

    def _to_plain_data(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)

        if isinstance(value, list):
            return [self._to_plain_data(item) for item in value]

        if isinstance(value, dict):
            return {
                key: self._to_plain_data(item)
                for key, item in value.items()
            }

        return value

    def _string_or_none(self, value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, list):
            return ",".join(str(item) for item in value if str(item).strip())

        text = str(value).strip()
        return text or None

    def _bool(self, value: Any, default: bool) -> bool:
        if value is None:
            return default

        if isinstance(value, bool):
            return value

        return str(value).strip().lower() in {"true", "yes", "1", "y"}

    def _int(self, value: Any, default: int) -> int:
        if value is None:
            return default

        try:
            return int(value)
        except (TypeError, ValueError):
            return default
