from bioops.tools.argo_tool import ArgoNodeStatus, ArgoWorkflowStatus
from bioops.tools.k8s_health import PodStatus
from bioops.tools.submit_master_failed_pods import (
    SubmitMasterFailedPodRequest,
    SubmitMasterFailedPodReporter,
)


class FakeArgoTool:
    def __init__(self, workflows):
        self.workflows = workflows

    def list_workflow_statuses(self, namespace=None):
        return self.workflows


class FakeK8sTool:
    def __init__(self, pods, logs_by_pod=None):
        self.pods = pods
        self.logs_by_pod = logs_by_pod or {}

    def get_pods(self):
        return self.pods

    def get_pod_logs(self, pod_name, tail_lines=None):
        return self.logs_by_pod.get(pod_name, "")


class FakeK8sFactory:
    def __init__(self, pods, logs_by_pod=None):
        self.pods = pods
        self.logs_by_pod = logs_by_pod or {}

    def __call__(self, namespace):
        return FakeK8sTool(self.pods, self.logs_by_pod)


def make_workflow(name="haplotypecaller-batch140325", phase="Failed"):
    failed_step = ArgoNodeStatus(
        name="node1",
        display_name="haplotypecaller",
        phase="Failed",
        node_type="Pod",
        template_name="haplotypecaller",
        started_at="",
        finished_at="",
        message="exit code 1",
    )

    return ArgoWorkflowStatus(
        name=name,
        namespace="argo",
        phase=phase,
        progress="1/2",
        started_at="",
        finished_at="",
        message="",
        labels={"batch_id": "batch140325"},
        running_steps=[],
        failed_steps=[failed_step],
        all_steps=[failed_step],
    )


def make_pod(name, phase="Failed", step="haplotypecaller"):
    return PodStatus(
        name=name,
        namespace="bioops",
        phase=phase,
        node_name="node-1",
        pipeline_step=step,
        started_at=None,
        runtime_minutes=42.0,
    )


def test_failed_pod_report_finds_failed_pod_and_logs():
    pod = make_pod("haplotypecaller-batch140325-pod")
    logs = {
        pod.name: "starting\nERROR missing input file\nfailed with exit code 1"
    }

    reporter = SubmitMasterFailedPodReporter(
        argo_tool=FakeArgoTool([make_workflow()]),
        k8s_tool_factory=FakeK8sFactory([pod], logs),
    )

    report = reporter.report(
        SubmitMasterFailedPodRequest(batch_id="batch140325")
    )

    assert report.status == "failed_pods_found"
    assert report.failed_pod_count == 1

    detail = report.failed_pods[0]
    assert detail.pod_name == pod.name
    assert detail.phase == "Failed"
    assert detail.workflow_name == "haplotypecaller-batch140325"
    assert any("missing input file" in line for line in detail.error_lines)
    assert "input" in detail.suggested_action.lower() or "path" in detail.suggested_action.lower()


def test_failed_pod_report_ignores_running_pods():
    pod = make_pod("haplotypecaller-batch140325-pod", phase="Running")

    reporter = SubmitMasterFailedPodReporter(
        argo_tool=FakeArgoTool([make_workflow(phase="Running")]),
        k8s_tool_factory=FakeK8sFactory([pod]),
    )

    report = reporter.report(
        SubmitMasterFailedPodRequest(batch_id="batch140325")
    )

    assert report.status == "no_failed_pods_found"
    assert report.failed_pod_count == 0


def test_failed_pod_report_detects_oom_suggestion():
    pod = make_pod("haplotypecaller-batch140325-pod")
    logs = {
        pod.name: "container terminated: OOMKilled"
    }

    reporter = SubmitMasterFailedPodReporter(
        argo_tool=FakeArgoTool([make_workflow()]),
        k8s_tool_factory=FakeK8sFactory([pod], logs),
    )

    report = reporter.report(
        SubmitMasterFailedPodRequest(batch_id="batch140325")
    )

    assert "memory" in report.failed_pods[0].suggested_action.lower()
