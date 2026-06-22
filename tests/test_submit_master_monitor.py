from bioops.tools.argo_tool import ArgoNodeStatus, ArgoWorkflowStatus
from bioops.tools.k8s_health import PodStatus
from bioops.tools.submit_master_monitor import (
    SubmitMasterMonitor,
    SubmitMasterMonitorRequest,
)


class FakeArgoTool:
    def __init__(self, workflows):
        self.workflows = workflows

    def list_workflow_statuses(self, namespace=None):
        return self.workflows


class FakeK8sTool:
    def __init__(self, namespace, pods=None, errors=None):
        self.namespace = namespace
        self.pods = pods or []
        self.errors = errors or ["No recent errors found."]

    def get_pods(self):
        return self.pods

    def get_recent_errors(self):
        return self.errors


class FakeK8sFactory:
    def __init__(self, pods=None, errors=None):
        self.pods = pods or []
        self.errors = errors or ["No recent errors found."]

    def __call__(self, namespace):
        return FakeK8sTool(namespace=namespace, pods=self.pods, errors=self.errors)


def make_workflow(name, phase, labels=None, failed_steps=None):
    return ArgoWorkflowStatus(
        name=name,
        namespace="argo",
        phase=phase,
        progress="1/2",
        started_at="",
        finished_at="",
        message="",
        labels=labels or {},
        running_steps=[],
        failed_steps=failed_steps or [],
        all_steps=[],
    )


def make_pod(name, phase="Running", step="haplotypecaller"):
    return PodStatus(
        name=name,
        namespace="bioops",
        phase=phase,
        node_name="node-1",
        pipeline_step=step,
        started_at=None,
        runtime_minutes=12.0,
    )


def test_monitor_reports_running_batch():
    workflows = [
        make_workflow(
            name="haplotypecaller-batch140325",
            phase="Running",
            labels={"batch_id": "batch140325"},
        )
    ]
    pods = [make_pod("haplotypecaller-batch140325-pod")]

    monitor = SubmitMasterMonitor(
        argo_tool=FakeArgoTool(workflows),
        k8s_tool_factory=FakeK8sFactory(pods=pods),
    )

    report = monitor.monitor(
        SubmitMasterMonitorRequest(
            batch_id="batch140325",
            argo_namespace="argo",
            k8s_namespace="bioops",
        )
    )

    assert report.status == "running"
    assert report.workflow_count == 1
    assert report.running_workflows == 1
    assert report.pod_count == 1
    assert report.running_pods == 1


def test_monitor_reports_failed_workflow_step():
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

    workflows = [
        make_workflow(
            name="haplotypecaller-batch140325",
            phase="Failed",
            labels={"batch_id": "batch140325"},
            failed_steps=[failed_step],
        )
    ]

    monitor = SubmitMasterMonitor(
        argo_tool=FakeArgoTool(workflows),
        k8s_tool_factory=FakeK8sFactory(),
    )

    report = monitor.monitor(SubmitMasterMonitorRequest(batch_id="batch140325"))

    assert report.status == "failed_or_unhealthy"
    assert report.failed_workflows == 1
    assert any("exit code 1" in error for error in report.errors)


def test_monitor_handles_argo_read_error():
    class BrokenArgoTool:
        def list_workflow_statuses(self, namespace=None):
            raise RuntimeError("cluster unavailable")

    monitor = SubmitMasterMonitor(
        argo_tool=BrokenArgoTool(),
        k8s_tool_factory=FakeK8sFactory(),
    )

    report = monitor.monitor(SubmitMasterMonitorRequest(batch_id="batch140325"))

    assert report.status == "failed_or_unhealthy"
    assert any("cluster unavailable" in error for error in report.errors)
