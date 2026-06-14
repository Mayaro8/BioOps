from bioops.agents.base import BaseAgent
from bioops.tools.batch_status import BatchStatusReport, BatchStatusTool


class BatchStatusAgent(BaseAgent):
    """Summarizes pipeline batch status from Kubernetes pod states."""

    name = "batch_status"
    description = "Reports batch/job progress, running steps, failed steps, and completion status."

    def __init__(self, batch_status_tool: BatchStatusTool | None = None):
        self.batch_status_tool = batch_status_tool or BatchStatusTool()

    def run(self, message: str) -> str:
        try:
            report = self.batch_status_tool.get_status()
        except Exception as error:
            return (
                "Batch Status Agent failed to collect batch status.\n\n"
                f"Error: {type(error).__name__}: {error}\n\n"
                "Check Kubernetes access, kubeconfig, and Docker volume mounts."
            )

        return self._format_report(report)

    def _format_report(self, report: BatchStatusReport) -> str:
        lines = [
            "Batch Status Report",
            "",
            "Summary:",
            f"- Total pods: {report.total_pods}",
            f"- Running: {report.running}",
            f"- Failed: {report.failed}",
            f"- Succeeded: {report.succeeded}",
            f"- Pending: {report.pending}",
            "",
            "Pipeline steps:",
        ]

        if not report.steps:
            lines.append("- No pipeline steps detected.")
            return "\n".join(lines)

        for step in report.steps:
            lines.append(
                f"- {step.step}: total={step.total}, "
                f"running={step.running}, failed={step.failed}, "
                f"succeeded={step.succeeded}, pending={step.pending}"
            )

        failed_steps = [step for step in report.steps if step.failed > 0]

        if failed_steps:
            lines.extend(
                [
                    "",
                    "Failed steps:",
                ]
            )

            for step in failed_steps:
                lines.append(f"- {step.step}: {step.failed} failed pod(s)")

        running_steps = [step for step in report.steps if step.running > 0]

        if running_steps:
            lines.extend(
                [
                    "",
                    "Currently running:",
                ]
            )

            for step in running_steps:
                lines.append(f"- {step.step}: {step.running} running pod(s)")

        return "\n".join(lines)

