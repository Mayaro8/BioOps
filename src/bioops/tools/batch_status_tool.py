from dataclasses import dataclass, field

from bioops.tools.argo_tool import ArgoTool, ArgoWorkflowStatus


@dataclass
class BatchStatusRequest:
    batch_id: str | None = None
    sample_id: str | None = None
    step: str | None = None
    workflow_name: str | None = None
    namespace: str | None = None


@dataclass
class BatchStatusResult:
    namespace: str
    workflows: list[ArgoWorkflowStatus] = field(default_factory=list)
    message: str = ""
    error: str | None = None


class BatchStatusTool:
    """
    Reads batch/workflow status from Argo Workflows.
    """

    def __init__(self, argo_tool: ArgoTool | None = None):
        self.argo_tool = argo_tool or ArgoTool()

    def get_status(self, request: BatchStatusRequest) -> BatchStatusResult:
        namespace = request.namespace or self.argo_tool.namespace

        try:
            if request.workflow_name:
                workflow = self.argo_tool.get_workflow_status(
                    name=request.workflow_name,
                    namespace=namespace,
                )
                workflows = [workflow]
            else:
                workflows = self.argo_tool.list_workflow_statuses(namespace=namespace)
                workflows = self._filter_workflows(workflows, request)

            if not workflows:
                return BatchStatusResult(
                    namespace=namespace,
                    workflows=[],
                    message="No matching Argo workflows found.",
                    error=None,
                )

            return BatchStatusResult(
                namespace=namespace,
                workflows=workflows,
                message=f"Found {len(workflows)} matching workflow(s).",
                error=None,
            )

        except Exception as error:
            return BatchStatusResult(
                namespace=namespace,
                workflows=[],
                message="Failed to read Argo workflow status.",
                error=f"{type(error).__name__}: {error}",
            )

    def _filter_workflows(
        self,
        workflows: list[ArgoWorkflowStatus],
        request: BatchStatusRequest,
    ) -> list[ArgoWorkflowStatus]:
        filtered = workflows

        if request.batch_id:
            filtered = [
                workflow for workflow in filtered
                if workflow.labels.get("batch_id") == request.batch_id
                or request.batch_id in workflow.name
            ]

        if request.sample_id:
            filtered = [
                workflow for workflow in filtered
                if workflow.labels.get("sample_id") == request.sample_id
                or workflow.labels.get("tube_id") == request.sample_id
                or request.sample_id in workflow.name
            ]

        if request.step:
            filtered = [
                workflow for workflow in filtered
                if workflow.labels.get("pipeline_step") == request.step
                or any(node.display_name == request.step for node in workflow.all_steps)
                or any(node.template_name == request.step for node in workflow.all_steps)
            ]

        return filtered
