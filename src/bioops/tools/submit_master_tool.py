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
    job_launched: bool
    parameters: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class SubmitMasterTool:
    """Builds submit-master configs and keeps launch gated behind confirm=true."""

    def __init__(
        self,
        argo_tool: ArgoTool | None = None,
        config_builder: SubmitMasterConfigBuilder | None = None,
    ):
        self.argo_tool = argo_tool or ArgoTool()
        self.config_builder = config_builder or SubmitMasterConfigBuilder()

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
            "D1 implemented: generated original-compatible submit-master JSON config.",
            "This step is still dry-run oriented.",
            "Real submit-master launch will be implemented separately and must require confirm=true.",
            "Do not copy original submit-master secrets or service-account files into BioOps.",
        ]
        notes.extend(config_result.warnings)

        submit_result = ArgoSubmitResult(
            submitted=False,
            workflow_name=None,
            namespace=argo_preview.namespace,
            phase="NotSubmitted",
            message="Dry run only. D2 submit-master launch is not implemented in this slice.",
            error=None,
        )

        status = "dry-run only"

        return SubmitPlan(
            status=status,
            missing_fields=missing_fields,
            config_preview=config_result.json_text,
            argo_preview=argo_preview,
            submit_result=submit_result,
            job_launched=False,
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
