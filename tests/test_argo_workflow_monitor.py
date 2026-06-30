from bioops.tools.argo_workflow_monitor import ArgoWorkflowMonitor


def test_summarize_workflow_groups_nodes_by_step_and_phase():
    monitor = ArgoWorkflowMonitor(namespace="argo")

    workflow = {
        "metadata": {
            "name": "bioops-submit-master-test",
            "namespace": "argo",
        },
        "spec": {
            "entrypoint": "main-dag",
        },
        "status": {
            "phase": "Running",
            "startedAt": "2026-06-29T10:00:00Z",
            "nodes": {
                "node-1": {
                    "type": "Pod",
                    "displayName": "config-creator",
                    "templateName": "config-creator",
                    "phase": "Succeeded",
                },
                "node-2": {
                    "type": "Pod",
                    "displayName": "haplotypecaller sample_001",
                    "templateName": "haplotypecaller",
                    "phase": "Running",
                },
                "node-3": {
                    "type": "Pod",
                    "displayName": "haplotypecaller sample_002",
                    "templateName": "haplotypecaller",
                    "phase": "Failed",
                    "message": "example failure",
                },
            },
        },
    }

    summary = monitor._summarize_workflow(workflow)

    assert summary["name"] == "bioops-submit-master-test"
    assert summary["phase"] == "Running"
    assert summary["step_counts"]["config-creator"]["Succeeded"] == 1
    assert summary["step_counts"]["haplotypecaller"]["Running"] == 1
    assert summary["step_counts"]["haplotypecaller"]["Failed"] == 1
    assert summary["failed_count"] == 1
    assert summary["current_bottleneck"] == "haplotypecaller"


def test_format_summary_does_not_dump_raw_pod_health_report():
    monitor = ArgoWorkflowMonitor(namespace="argo")

    summary = {
        "name": "bioops-submit-master-test",
        "namespace": "argo",
        "phase": "Running",
        "entrypoint": "main-dag",
        "runtime": "12.0 min",
        "step_counts": {
            "haplotypecaller": {
                "Running": 120,
                "Succeeded": 73,
                "Failed": 7,
            }
        },
        "current_bottleneck": "haplotypecaller",
        "failed_items": ["haplotypecaller sample_034 [Failed]"],
        "failed_count": 7,
        "active_items": ["haplotypecaller sample_001 [Running]"],
        "active_count": 120,
        "message": "",
    }

    report = monitor._format_summary(summary)

    assert "SubmitMaster Workflow Progress" in report
    assert "haplotypecaller" in report
    assert "Current bottleneck" in report
    assert "Failed nodes/samples: 7" in report
    assert "Total pods" not in report
    assert "Unhealthy pods" not in report
