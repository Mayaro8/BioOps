from dataclasses import dataclass, field

from bioops.tools.argo_tool import (
    ArgoSubmitPreview,
    ArgoSubmitResult,
    ArgoTool,
)


@dataclass
class SubmitRequest:
    sample_id: str | None = None
    batch_id: str | None = None
    pipeline: str | None = None
    step: str | None = None
    input_uri: str | None = None
    output_uri: str | None = None
    workflow_file: str | None = None
    namespace: str | None = None
    confirm: bool = False


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
    """
    Builds and optionally submits Argo workflow plans.

    Submission happens only when request.confirm is True.
    """

    def __init__(self, argo_tool: ArgoTool | None = None):
        self.argo_tool = argo_tool or ArgoTool()

    def build_plan(self, request: SubmitRequest) -> SubmitPlan:
        missing_fields = self._validate_request(request)
        parameters = self._build_argo_parameters(request)

        argo_preview = self.argo_tool.prepare_submit_command(
            workflow_file=request.workflow_file,
            namespace=request.namespace,
            parameters=parameters,
        )

        notes = [
            "SubmitMasterAgent is Argo-aware.",
            "Dry-run preview is always generated before submission.",
            "Real submission requires confirm=true.",
        ]

        submit_result = ArgoSubmitResult(
            submitted=False,
            workflow_name=None,
            namespace=argo_preview.namespace,
            phase="NotSubmitted",
            message="Dry run only. Add confirm=true to submit.",
            error=None,
        )

        if request.confirm:
            if missing_fields:
                submit_result = ArgoSubmitResult(
                    submitted=False,
                    workflow_name=None,
                    namespace=argo_preview.namespace,
                    phase="NotSubmitted",
                    message="Submission blocked because required fields are missing.",
                    error=", ".join(missing_fields),
                )
            elif argo_preview.missing_config:
                submit_result = ArgoSubmitResult(
                    submitted=False,
                    workflow_name=None,
                    namespace=argo_preview.namespace,
                    phase="NotSubmitted",
                    message="Submission blocked because Argo config is incomplete.",
                    error=", ".join(argo_preview.missing_config),
                )
            else:
                submit_result = self.argo_tool.submit_workflow(
                    workflow_file=argo_preview.workflow_file,
                    namespace=argo_preview.namespace,
                    parameters=parameters,
                )

        status = "submitted" if submit_result.submitted else "dry-run only"

        return SubmitPlan(
            status=status,
            missing_fields=missing_fields,
            config_preview=self._build_config_preview(request, parameters),
            argo_preview=argo_preview,
            submit_result=submit_result,
            job_launched=submit_result.submitted,
            parameters=parameters,
            notes=notes,
        )

    def _validate_request(self, request: SubmitRequest) -> list[str]:
        missing: list[str] = []

        if not request.sample_id and not request.batch_id:
            missing.append("sample_id or batch_id")

        if not request.pipeline:
            missing.append("pipeline")

        if not request.step:
            missing.append("step")

        if not request.input_uri:
            missing.append("input_uri")

        if not request.output_uri:
            missing.append("output_uri")

        return missing

    def _build_argo_parameters(self, request: SubmitRequest) -> dict[str, str]:
        return {
            "SAMPLE_IDS": request.sample_id or "",
            "BATCH_ID": request.batch_id or "",
            "PIPELINE": request.pipeline or "",
            "STEP": request.step or "",
            "INPUT_URI": request.input_uri or "",
            "OUTPUT_URI": request.output_uri or "",
        }

    def _build_config_preview(
        self,
        request: SubmitRequest,
        parameters: dict[str, str],
    ) -> str:
        lines = [
            "submission:",
            f"  sample_id: {request.sample_id or 'null'}",
            f"  batch_id: {request.batch_id or 'null'}",
            f"  pipeline: {request.pipeline or 'null'}",
            f"  step: {request.step or 'null'}",
            f"  input_uri: {request.input_uri or 'null'}",
            f"  output_uri: {request.output_uri or 'null'}",
            f"  argo_namespace: {request.namespace or 'default-from-tool'}",
            f"  workflow_file: {request.workflow_file or 'default-from-tool'}",
            f"  confirm: {str(request.confirm).lower()}",
            "  argo_parameters:",
        ]

        for key, value in parameters.items():
            lines.append(f"    {key}: {value or 'null'}")

        return "\n".join(lines)
