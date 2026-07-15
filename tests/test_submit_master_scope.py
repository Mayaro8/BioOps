from types import SimpleNamespace

from bioops.tools.submit_master_scope import SubmitMasterScopeMonitor


def workflow(index, phase, step):
    node_phase = {
        "Succeeded": "Succeeded",
        "Pending": "Pending",
        "Failed": "Failed",
    }.get(phase, "Running")

    return {
        "metadata": {
            "name": f"workflow-{index:04d}",
            "creationTimestamp": "2026-07-15T10:00:00Z",
            "labels": {
                "bioops.dev/workload": "submit-master",
                "bioops.dev/batch-id": "B104",
                "bioops.dev/sample-id": f"S{index:04d}",
                "bioops.dev/attempt": "0",
            },
        },
        "status": {
            "phase": phase,
            "startedAt": "2026-07-15T10:00:00Z",
            "finishedAt": "2026-07-15T10:10:00Z",
            "nodes": {
                "node": {
                    "type": "Pod",
                    "phase": node_phase,
                    "displayName": step,
                    "templateName": step,
                }
            },
        },
    }


class FakeApi:
    def __init__(self, workflows):
        self.workflows = workflows
        self.calls = []

    def list_namespaced_custom_object(self, **kwargs):
        self.calls.append(kwargs)
        return {"items": self.workflows, "metadata": {}}

    def get_namespaced_custom_object(self, **kwargs):
        return self.workflows[0]


class FakeCore:
    def __init__(self, pods=None):
        self.pods = pods or []
        self.calls = []

    def list_namespaced_pod(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            items=self.pods,
            metadata=SimpleNamespace(_continue=None),
        )

def test_batch_aggregates_one_thousand_samples():
    workflows = [
        *[workflow(i, "Succeeded", "beagle") for i in range(650)],
        *[workflow(i, "Running", "beagle") for i in range(650, 900)],
        *[workflow(i, "Pending", "gvcf-to-vcf") for i in range(900, 980)],
        *[workflow(i, "Failed", "haplotypecaller") for i in range(980, 1000)],
    ]

    monitor = SubmitMasterScopeMonitor(
        "bioops-dev",
        "bioops-submit-master",
        "bioops-submit-master-local",
        custom_api=FakeApi(workflows),
        core_api=FakeCore(),
    )
    report = monitor.render_batch_status("B104")

    assert "Samples: 1000" in report
    assert "Succeeded: 650 (65.0%)" in report
    assert "Running: 250 (25.0%)" in report
    assert "Pending: 80 (8.0%)" in report
    assert "Failed: 20 (2.0%)" in report
    assert "Average: 10.0 min" in report
    assert "Median: 10.0 min" in report


def test_sample_report_reads_workflow_pods():
    item = workflow(927, "Running", "beagle")
    pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="sample-927-beagle",
            labels={"pipeline_step": "beagle"},
        ),
        status=SimpleNamespace(phase="Running"),
    )
    core = FakeCore([pod])
    monitor = SubmitMasterScopeMonitor(
        "bioops-dev",
        "bioops-submit-master",
        "bioops-submit-master-local",
        custom_api=FakeApi([item]),
        core_api=core,
    )

    report = monitor.render_sample_status("S0927", "B104")

    assert "Sample: S0927" in report
    assert "Current step: beagle" in report
    assert "beagle [Running]: 1 (100.0%)" in report
    assert core.calls[0]["label_selector"] == (
        "workflows.argoproj.io/workflow=workflow-0927"
    )
