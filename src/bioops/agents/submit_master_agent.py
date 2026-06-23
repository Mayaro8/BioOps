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
from bioops.tools.submit_master_restart import (
    SubmitMasterRestartRequest,
    SubmitMasterRestartTool,
)
from bioops.tools.submit_master_parameter_matcher import (
    StepMatchResult,
    SubmitMasterParameterMatcher,
)
from bioops.tools.submit_master_tool import SubmitMasterTool, SubmitRequest, SubmitPlan


class SubmitMasterAgent(BaseAgent):
    """
    Submit Master agent with LLM-only request interpretation and deterministic
    parameter matching.

    Flow:
    user message -> LLM planner -> deterministic required/provided comparison
    -> confirmation or missing-info feedback -> D1/D2/D3/D4 tools.
    """

    name = "submit_master"
    description = (
        "Plans original-compatible Submit Master configs, safe launches, "
        "monitoring reports, and failed-pod reports."
    )

    def __init__(
        self,
        submit_tool: SubmitMasterTool | None = None,
        monitor: SubmitMasterMonitor | None = None,
        failed_pod_reporter: SubmitMasterFailedPodReporter | None = None,
        restart_tool: SubmitMasterRestartTool | None = None,
        planner: SubmitMasterLLMPlanner | None = None,
        matcher: SubmitMasterParameterMatcher | None = None,
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
        self.restart_tool = restart_tool or SubmitMasterRestartTool(
            failed_pod_reporter=self.failed_pod_reporter,
            allow_restart=bool(self.submit_config.get("allow_restart", False)),
            argo_command=self.submit_config.get("argo_command", "argo"),
        )
        self.planner = planner or SubmitMasterLLMPlanner()
        self.matcher = matcher or SubmitMasterParameterMatcher()

    def run(self, message: str) -> str:
        try:
            decision = self.planner.plan(
                message=message,
                context=self._planner_context(),
            )
        except Exception as error:
            return self._format_planner_error(error)

        if decision.intent == "refuse":
            return self._format_refusal(decision)

        if decision.intent == "restart_failed_pods":
            return self._run_restart_failed_pods(decision)

        if decision.intent == "monitor":
            return self._run_monitor(decision)

        if decision.intent == "failed_pods":
            return self._run_failed_pods(decision)

        if decision.intent in {"build_or_launch", "explain_config"}:
            merged_parameters = self._merge_defaults(decision.provided_parameters)
            match = self.matcher.match(
                provided_parameters=merged_parameters,
                candidate_stage=decision.candidate_stage or self._string_or_none(merged_parameters.get("stage")),
                candidate_step=decision.candidate_step or self._string_or_none(
                    merged_parameters.get("step") or merged_parameters.get("steps_order")
                ),
                candidate_platform=decision.candidate_platform or self._string_or_none(
                    merged_parameters.get("seq_type")
                ),
            )

            if decision.intent == "explain_config":
                return self._format_config_guidance(decision, match)

            if not match.ready:
                return self._format_missing_info(decision, match)

            request = self._build_submit_request(decision, match, merged_parameters)

            if not decision.user_confirmed and not request.confirm:
                return self._format_ready_for_confirmation(decision, match, request)

            plan = self.submit_tool.build_plan(request)
            return self._format_submit_report(decision, match, request, plan)

        return self._format_refusal(
            SubmitMasterPlannerDecision(
                intent="refuse",
                refusal_reason=f"Unsupported Submit Master intent: {decision.intent}",
            )
        )

    def _run_monitor(self, decision: SubmitMasterPlannerDecision) -> str:
        params = self._merge_defaults(decision.provided_parameters)

        if not params.get("batch_id") and not params.get("workflow_name"):
            return "\n".join(
                [
                    "Submit Master needs more information",
                    "",
                    "Intent: monitor",
                    "Missing parameters:",
                    "- batch_id or workflow_name",
                    "",
                    "Please provide a batch_id or workflow_name to monitor.",
                ]
            )

        report = self.monitor.monitor(
            SubmitMasterMonitorRequest(
                batch_id=self._string_or_none(params.get("batch_id")),
                workflow_name=self._string_or_none(params.get("workflow_name")),
                argo_namespace=self._string_or_none(params.get("argo_namespace"))
                or self.submit_config.get("argo_namespace")
                or "argo",
                k8s_namespace=self._string_or_none(params.get("k8s_namespace"))
                or self._string_or_none(params.get("namespace"))
                or "bioops",
            )
        )

        return self._format_generic_report("Submit Master Monitor Report", report)

    def _run_failed_pods(self, decision: SubmitMasterPlannerDecision) -> str:
        params = self._merge_defaults(decision.provided_parameters)

        if not params.get("batch_id") and not params.get("workflow_name"):
            return "\n".join(
                [
                    "Submit Master needs more information",
                    "",
                    "Intent: failed_pods",
                    "Missing parameters:",
                    "- batch_id or workflow_name",
                    "",
                    "Please provide a batch_id or workflow_name to report failed pods.",
                ]
            )

        report = self.failed_pod_reporter.report(
            SubmitMasterFailedPodRequest(
                batch_id=self._string_or_none(params.get("batch_id")),
                workflow_name=self._string_or_none(params.get("workflow_name")),
                argo_namespace=self._string_or_none(params.get("argo_namespace"))
                or self.submit_config.get("argo_namespace")
                or "argo",
                k8s_namespace=self._string_or_none(params.get("k8s_namespace"))
                or self._string_or_none(params.get("namespace"))
                or "bioops",
            )
        )

        return self._format_generic_report("Submit Master Failed Pod Report", report)

    def _build_submit_request(
        self,
        decision: SubmitMasterPlannerDecision,
        match: StepMatchResult,
        params: dict[str, Any],
    ) -> SubmitRequest:
        extra_params = params.get("extra_params") or {}
        if not isinstance(extra_params, dict):
            extra_params = {}

        return SubmitRequest(
            sample_id=self._string_or_none(params.get("sample_ids") or params.get("sample_id")),
            batch_id=self._string_or_none(params.get("batch_id")),
            pipeline=self._string_or_none(params.get("pipeline")) or "pipeline-v3.0",
            step=self._string_or_none(params.get("step")) or match.step,
            steps_order=self._string_or_none(params.get("steps_order")) or match.step,
            stage=self._string_or_none(params.get("stage")) or match.stage,
            seq_type=self._string_or_none(params.get("seq_type")) or match.platform,
            cluster_name=self._string_or_none(params.get("cluster_name")),
            mongo_cluster_name=self._string_or_none(params.get("mongo_cluster_name")),
            contour=self._string_or_none(params.get("contour"))
            or self.submit_config.get("contour")
            or "prod",
            input_uri=self._string_or_none(params.get("input_uri")),
            output_uri=self._string_or_none(params.get("output_uri")),
            workflow_file=self._string_or_none(params.get("workflow_file"))
            or self.submit_config.get("workflow_file"),
            namespace=self._string_or_none(params.get("namespace")) or "bioops",
            wait=self._bool(params.get("wait"), default=True),
            only_good=self._bool(params.get("only_good"), default=True),
            delay=self._int(params.get("delay"), default=0),
            delay_step=self._int(params.get("delay_step"), default=1),
            chunk_size=self._int(params.get("chunk_size"), default=1),
            confirm=decision.user_confirmed or self._bool(params.get("confirm"), default=False),
            extra_params=extra_params,
        )

    def _merge_defaults(self, params: dict[str, Any]) -> dict[str, Any]:
        merged = {
            "seq_type": "illumina",
            "namespace": self.submit_config.get("namespace")
            or self.submit_config.get("k8s_namespace")
            or "bioops",
            "contour": self.submit_config.get("contour", "prod"),
            "wait": True,
            "only_good": True,
            "delay": 0,
            "delay_step": 1,
            "chunk_size": 1,
            "confirm": False,
        }

        for key, value in (params or {}).items():
            if value not in (None, "", [], {}):
                merged[key] = value

        if "platform" in merged and "seq_type" not in merged:
            merged["seq_type"] = merged["platform"]

        return merged

    def _planner_context(self) -> dict[str, Any]:
        return {
            "submit_master_yaml": {
                "enabled": bool(self.submit_config.get("enabled", False)),
                "allow_launch": bool(self.submit_config.get("allow_launch", False)),
                "argo_namespace": self.submit_config.get("argo_namespace", "argo"),
                "k8s_namespace": self.submit_config.get("k8s_namespace", "bioops"),
                "namespace": self.submit_config.get("namespace", "bioops"),
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
                "allow_launch": bool(self.submit_config.get("allow_launch", False)),
            },
            "safe_environment_availability": self._safe_environment_availability(),
            "known_intents": [
                "build_or_launch",
                "monitor",
                "failed_pods",
                "restart_failed_pods",
                "explain_config",
                "refuse",
            ],
            "known_step_examples": [
                "stage1/cutadapt/illumina",
                "stage1/fq2bam/illumina",
                "stage2/haplotypecaller/illumina",
                "stage3/hla/illumina",
                "stage3/beagle/illumina",
                "stage3/final_checker/illumina",
            ],
            "safety": {
                "llm_may_not_launch": True,
                "launch_requires_user_confirmation": True,
                "launch_requires_yaml_allow_launch": True,
                "yaml_allow_launch": bool(self.submit_config.get("allow_launch", False)),
                "d5_restart_failed_pods_implemented": False,
            },
        }

    def _safe_environment_availability(self) -> dict[str, bool]:
        import os

        keys = [
            "KUBECONFIG",
            "ARGO_SERVER",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_VERSION",
            "AZURE_OPENAI_CHAT_DEPLOYMENT",
            "SUBMIT_MASTER_ENTRYPOINT",
        ]

        return {key: bool(os.getenv(key)) for key in keys}

    def _format_ready_for_confirmation(
        self,
        decision: SubmitMasterPlannerDecision,
        match: StepMatchResult,
        request: SubmitRequest,
    ) -> str:
        lines = [
            "Submit Master config is ready for confirmation",
            "",
            "Matched step:",
            f"- Stage: {match.stage}",
            f"- Step: {match.step}",
            f"- Platform: {match.platform}",
            f"- Completion: {match.completion_percent}%",
            "",
            "Parameter comparison:",
            *self._match_lines(match),
            "",
            "Planned Submit Master request:",
            f"- batch_id: {request.batch_id or 'not provided'}",
            f"- sample_ids: {request.sample_id or 'not provided'}",
            f"- cluster_name: {request.cluster_name or 'not provided'}",
            f"- mongo_cluster_name: {request.mongo_cluster_name or 'not provided'}",
            f"- namespace: {request.namespace}",
            f"- contour: {request.contour}",
            "",
            "No launch was attempted yet.",
            "To continue, reply with an explicit confirmation such as: confirm=true.",
        ]

        if not self.submit_config.get("allow_launch", False):
            lines.extend(
                [
                    "",
                    "Safety note:",
                    "- YAML allow_launch is false, so even confirm=true will only prepare/save the launch plan unless allow_launch is enabled.",
                ]
            )

        return "\n".join(lines)

    def _format_missing_info(
        self,
        decision: SubmitMasterPlannerDecision,
        match: StepMatchResult,
    ) -> str:
        lines = [
            "Submit Master needs more information",
            "",
            "Closest matching step:",
            f"- Stage: {match.stage}",
            f"- Step: {match.step}",
            f"- Platform: {match.platform}",
            f"- Completion: {match.completion_percent}%",
            "",
            "Parameter comparison:",
            *self._match_lines(match),
        ]

        if match.recommendations:
            lines.extend(["", "Recommendations:"])
            lines.extend(f"- {item}" for item in match.recommendations)

        lines.extend(
            [
                "",
                "Provide the missing variables, then I can rebuild the config and ask for confirmation.",
            ]
        )

        return "\n".join(lines)

    def _format_config_guidance(
        self,
        decision: SubmitMasterPlannerDecision,
        match: StepMatchResult,
    ) -> str:
        lines = [
            "Submit Master config guidance",
            "",
            "Best matching step:",
            f"- Stage: {match.stage}",
            f"- Step: {match.step}",
            f"- Platform: {match.platform}",
            f"- Completion with current information: {match.completion_percent}%",
            "",
            "Parameter comparison:",
            *self._match_lines(match),
        ]

        if match.recommendations:
            lines.extend(["", "Recommendations:"])
            lines.extend(f"- {item}" for item in match.recommendations)

        return "\n".join(lines)

    def _format_submit_report(
        self,
        decision: SubmitMasterPlannerDecision,
        match: StepMatchResult,
        request: SubmitRequest,
        plan: SubmitPlan,
    ) -> str:
        lines = [
            "Submit Master Report",
            "",
            f"Status: {plan.status}",
            "",
            "Matched step:",
            f"- Stage: {match.stage}",
            f"- Step: {match.step}",
            f"- Platform: {match.platform}",
            f"- Completion: {match.completion_percent}%",
            "",
            "Parameter comparison:",
            *self._match_lines(match),
            "",
            "Generated submit-master JSON config:",
            plan.config_preview,
            "",
            "D2 launch result:",
        ]

        launch = plan.launch_result
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

        lines.extend(["", "Notes:"])
        lines.extend(f"- {item}" for item in plan.notes)

        return "\n".join(lines)

    def _match_lines(self, match: StepMatchResult) -> list[str]:
        lines = ["- Required parameters:"]
        lines.extend(f"  - {item}" for item in match.required_parameters)

        lines.append("- Provided/default parameters:")
        if match.provided_parameters:
            lines.extend(f"  - {key}: {value}" for key, value in match.provided_parameters.items())
        else:
            lines.append("  - none")

        lines.append("- Missing parameters:")
        if match.missing_parameters:
            lines.extend(f"  - {item}" for item in match.missing_parameters)
        else:
            lines.append("  - none")

        return lines

    def _format_refusal(self, decision: SubmitMasterPlannerDecision) -> str:
        return "\n".join(
            [
                "Submit Master request was not executed",
                "",
                f"Reason: {decision.refusal_reason or decision.explanation or 'The request could not be safely planned.'}",
                "",
                "No config was generated.",
                "No launch was attempted.",
            ]
        )

    def _format_restart_not_implemented(self, decision: SubmitMasterPlannerDecision) -> str:
        return "\n".join(
            [
                "Submit Master restart is not implemented yet",
                "",
                "D5 restart failed pods is intentionally unavailable in this branch.",
                "No pod or workflow was restarted.",
            ]
        )

    def _format_planner_error(self, error: Exception) -> str:
        return "\n".join(
            [
                "Submit Master planner unavailable",
                "",
                f"Error: {type(error).__name__}: {error}",
                "",
                "No config was generated.",
                "No launch was attempted.",
            ]
        )

    def _format_generic_report(self, title: str, report: Any) -> str:
        payload = self._to_plain_data(report)

        lines = [title, ""]
        if isinstance(payload, dict):
            for key, value in payload.items():
                lines.append(f"{key}: {value}")
        else:
            lines.append(str(payload))

        return "\n".join(lines)

    def _load_config(self, config_path: str) -> dict[str, Any]:
        path = Path(config_path)
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def _to_plain_data(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)

        if isinstance(value, list):
            return [self._to_plain_data(item) for item in value]

        if isinstance(value, dict):
            return {key: self._to_plain_data(item) for key, item in value.items()}

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
