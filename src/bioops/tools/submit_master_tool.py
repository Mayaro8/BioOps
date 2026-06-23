from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bioops.tools.argo_tool import (
    ArgoSubmitPreview,
    ArgoSubmitResult,
    ArgoTool,
)
from bioops.tools.submit_master_config_builder import (
    SubmitMasterConfigBuilder,
    SubmitMasterConfigInput,
)
from bioops.tools.submit_master_runner import (
    SubmitMasterLaunchRequest,
    SubmitMasterLaunchResult,
    SubmitMasterRunner,
)


@dataclass
class SubmitRequest:
    sample_id: str | None = None
    batch_id: str | None = None
    pipeline: str | None = None
    step: str | None = None
    steps_order: str | None = None
    stage: str | None = None
    seq_type: str | None = None
    cluster_name: str | None = None
    mongo_cluster_name: str | None = None
    contour: str | None = None
    input_uri: str | None = None
    output_uri: str | None = None
    workflow_file: str | None = None
    namespace: str | None = None
    wait: bool = True
    only_good: bool = True
    delay: int = 0
    delay_step: int = 1
    chunk_size: int = 1
    confirm: bool = False
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubmitPlan:
    status: str
    missing_fields: list[str]
    config_preview: str
    argo_preview: ArgoSubmitPreview
    submit_result: ArgoSubmitResult
    launch_result: SubmitMasterLaunchResult | None
    job_launched: bool
    parameters: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class SubmitMasterTool:
    """Builds submit-master configs and safely launches submit master for D2."""

    def __init__(
        self,
        argo_tool: ArgoTool | None = None,
        config_builder: SubmitMasterConfigBuilder | None = None,
        runner: SubmitMasterRunner | None = None,
        submit_master_entrypoint: str = "",
        generated_config_dir: str = "logs/submit_master_configs",
        contour: str = "prod",
        python_executable: str = "python",
        launch_timeout_seconds: int = 900,
        allow_launch: bool = False,
    ):
        self.argo_tool = argo_tool or ArgoTool()
        self.config_builder = config_builder or SubmitMasterConfigBuilder()
        self.runner = runner or SubmitMasterRunner()
        self.submit_master_entrypoint = submit_master_entrypoint
        self.generated_config_dir = generated_config_dir
        self.contour = contour
        self.python_executable = python_executable
        self.launch_timeout_seconds = launch_timeout_seconds
        self.allow_launch = allow_launch

    def build_plan(self, request: SubmitRequest) -> SubmitPlan:
        config_input = self._build_config_input(request)
        config_result = self.config_builder.build(config_input)

        missing_fields = list(config_result.errors)
        parameters = self._build_argo_parameters(request)

        argo_preview = self.argo_tool.prepare_submit_command(
            workflow_file=request.workflow_file,
            namespace=request.namespace,
            parameters=parameters,
        )

        notes = [
            "D1: generated original-compatible submit-master JSON config.",
            "D2: saved generated config and prepared safe submit-master launch command.",
            "Real launch requires confirm=true and allow_launch=true.",
            "Do not copy original submit-master secrets or service-account files into BioOps.",
        ]
        notes.extend(config_result.warnings)

        launch_result: SubmitMasterLaunchResult | None = None

        if missing_fields:
            launch_result = SubmitMasterLaunchResult(
                launched=False,
                saved_config_path=None,
                command=[],
                returncode=None,
                stdout="",
                stderr="",
                message="Launch skipped because generated config has validation errors.",
                blocked_reason="invalid config",
            )
        else:
            launch_result = self.runner.prepare_or_launch(
                SubmitMasterLaunchRequest(
                    config_text=config_result.json_text,
                    confirm=request.confirm,
                    allow_launch=self.allow_launch,
                    submit_master_entrypoint=self.submit_master_entrypoint,
                    generated_config_dir=self.generated_config_dir,
                    contour=request.contour or self.contour,
                    python_executable=self.python_executable,
                    timeout_seconds=self.launch_timeout_seconds,
                    label_parts={
                        "stage": request.stage or "",
                        "step": request.steps_order or request.step or "",
                        "batch": request.batch_id or "",
                    },
                )
            )

        submit_result = self._build_submit_result(argo_preview, launch_result)
        status = self._status_from_launch_result(launch_result)

        return SubmitPlan(
            status=status,
            missing_fields=missing_fields,
            config_preview=config_result.json_text,
            argo_preview=argo_preview,
            submit_result=submit_result,
            launch_result=launch_result,
            job_launched=bool(launch_result and launch_result.launched),
            parameters=parameters,
            notes=notes,
        )

    def _build_config_input(self, request: SubmitRequest) -> SubmitMasterConfigInput:
        return SubmitMasterConfigInput(
            stage=request.stage or "",
            steps_order=request.steps_order or request.step or "",
            seq_type=request.seq_type or "illumina",
            cluster_name=request.cluster_name or "",
            mongo_cluster_name=request.mongo_cluster_name or "",
            namespace=request.namespace or "default",
            sample_ids=self._parse_sample_ids(request.sample_id),
            batch_id=request.batch_id,
            run_id=request.extra_params.get("run_id"),
            delay=request.delay,
            delay_step=request.delay_step,
            chunk_size=request.chunk_size,
            wait=request.wait,
            only_good=request.only_good,
            extra_params=request.extra_params,
        )

    def _parse_sample_ids(self, value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _build_argo_parameters(self, request: SubmitRequest) -> dict[str, str]:
        return {
            "SAMPLE_IDS": request.sample_id or "",
            "BATCH_ID": request.batch_id or "",
            "PIPELINE": request.pipeline or "pipeline-v3.0",
            "STEP": request.step or request.steps_order or "",
            "INPUT_URI": request.input_uri or "",
            "OUTPUT_URI": request.output_uri or "",
        }

    def _build_submit_result(
        self,
        argo_preview: ArgoSubmitPreview,
        launch_result: SubmitMasterLaunchResult | None,
    ) -> ArgoSubmitResult:
        if launch_result is None:
            return ArgoSubmitResult(
                submitted=False,
                workflow_name=None,
                namespace=argo_preview.namespace,
                phase="NotSubmitted",
                message="No launch result was produced.",
                error=None,
            )

        if not launch_result.launched:
            return ArgoSubmitResult(
                submitted=False,
                workflow_name=None,
                namespace=argo_preview.namespace,
                phase="NotSubmitted",
                message=launch_result.message,
                error=launch_result.blocked_reason,
            )

        if launch_result.returncode == 0:
            phase = "LaunchSucceeded"
            error = None
        else:
            phase = "LaunchFailed"
            error = launch_result.blocked_reason or launch_result.stderr

        return ArgoSubmitResult(
            submitted=launch_result.returncode == 0,
            workflow_name=None,
            namespace=argo_preview.namespace,
            phase=phase,
            message=launch_result.message,
            error=error,
        )

    def _status_from_launch_result(self, launch_result: SubmitMasterLaunchResult | None) -> str:
        if launch_result is None:
            return "not launched"

        if launch_result.launched and launch_result.returncode == 0:
            return "launch succeeded"

        if launch_result.launched:
            return "launch failed"

        return "dry-run or blocked"
