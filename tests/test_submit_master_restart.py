from dataclasses import dataclass

from bioops.tools.submit_master_restart import (
    SubmitMasterRestartRequest,
    SubmitMasterRestartTool,
)


@dataclass
class FakeFailedPod:
    workflow_name: str


@dataclass
class FakeFailedReport:
    failed_pod_count: int
    failed_pods: list[FakeFailedPod]


class FakeReporter:
    def __init__(self, report):
        self.report_value = report

    def report(self, request):
        return self.report_value


class FakeCompleted:
    def __init__(self, returncode=0, stdout="retried", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_restart_requires_confirmation():
    tool = SubmitMasterRestartTool(
        failed_pod_reporter=FakeReporter(
            FakeFailedReport(
                failed_pod_count=1,
                failed_pods=[FakeFailedPod(workflow_name="haplotypecaller-batch140325")],
            )
        ),
        allow_restart=True,
    )

    result = tool.restart(
        SubmitMasterRestartRequest(batch_id="batch140325", confirm=False)
    )

    assert result.status == "restart_confirmation_required"
    assert result.target_workflows == ["haplotypecaller-batch140325"]
    assert "confirm=true" in result.blocked_reason
    assert result.attempts[0].executed is False


def test_restart_blocked_by_yaml_config_even_when_confirmed():
    tool = SubmitMasterRestartTool(
        failed_pod_reporter=FakeReporter(
            FakeFailedReport(
                failed_pod_count=1,
                failed_pods=[FakeFailedPod(workflow_name="haplotypecaller-batch140325")],
            )
        ),
        allow_restart=False,
    )

    result = tool.restart(
        SubmitMasterRestartRequest(batch_id="batch140325", confirm=True)
    )

    assert result.status == "restart_blocked_by_config"
    assert "allow_restart" in result.blocked_reason
    assert result.attempts[0].executed is False


def test_restart_executes_argo_retry_when_confirmed_and_allowed():
    calls = []

    def fake_runner(command, capture_output, text, check):
        calls.append(command)
        return FakeCompleted(returncode=0, stdout="workflow retried")

    tool = SubmitMasterRestartTool(
        failed_pod_reporter=FakeReporter(
            FakeFailedReport(
                failed_pod_count=1,
                failed_pods=[FakeFailedPod(workflow_name="haplotypecaller-batch140325")],
            )
        ),
        allow_restart=True,
        command_runner=fake_runner,
    )

    result = tool.restart(
        SubmitMasterRestartRequest(
            batch_id="batch140325",
            argo_namespace="argo",
            confirm=True,
        )
    )

    assert result.status == "restart_submitted"
    assert calls == [["argo", "retry", "haplotypecaller-batch140325", "-n", "argo"]]
    assert result.attempts[0].executed is True
    assert result.attempts[0].success is True
