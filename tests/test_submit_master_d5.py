import pytest

from bioops.jobs.submit_master_d5_retry_bitrix_report import (
    _has_active_retry,
    _resubmit_workflow,
    _retry_decision,
    _target_retry_spec,
)


class FakeApi:
    def __init__(self, workflows=None):
        self.workflows = workflows or []
        self.calls = []
        self.created = None

    def list_namespaced_custom_object(self, **kwargs):
        self.calls.append(kwargs)
        return {"items": self.workflows}

    def create_namespaced_custom_object(self, **kwargs):
        self.created = kwargs["body"]
        return {"metadata": {"name": "sample-retry"}}


def failed_workflow(message="NodeLost"):
    return {
        "metadata": {
            "name": "sample-workflow",
            "labels": {
                "bioops.dev/workload": "submit-master",
                "bioops.dev/batch-id": "B104",
                "bioops.dev/sample-id": "S927",
                "workflows.argoproj.io/completed": "true",
            },
        },
        "spec": {"arguments": {"parameters": []}},
        "status": {
            "phase": "Failed",
            "nodes": {
                "node": {
                    "phase": "Failed",
                    "message": message,
                }
            },
        },
    }

def test_retry_decision():
    retryable, _ = _retry_decision(
        failed_workflow("NodeLost")
    )
    blocked, _ = _retry_decision(
        failed_workflow("ImagePullBackOff")
    )

    assert retryable is True
    assert blocked is False


def test_retry_preserves_sample_identity():
    api = FakeApi()

    _resubmit_workflow(
        api=api,
        workflow=failed_workflow(),
        namespace="bioops-dev",
        root_workflow="sample-workflow",
        next_retry_count=1,
    )

    labels = api.created["metadata"]["labels"]
    parameters = api.created["spec"]["arguments"]["parameters"]

    assert labels["bioops.dev/batch-id"] == "B104"
    assert labels["bioops.dev/sample-id"] == "S927"
    assert labels["bioops.dev/attempt"] == "1"
    assert "workflows.argoproj.io/completed" not in labels
    assert {
        item["name"]: item["value"]
        for item in parameters
    }["attempt"] == "1"


def test_active_retry_uses_root_label():
    api = FakeApi([])

    assert _has_active_retry(
        api=api,
        namespace="bioops-dev",
        root_workflow="sample-workflow",
        current_workflow_name="sample-workflow",
    ) is False

    assert api.calls[0]["label_selector"] == (
        "bioops.dev/d5-root=sample-workflow"
    )


def failed_batch_workflow():
    def task_template(name, sample):
        return {
            "name": name,
            "metadata": {"labels": {"bioops.dev/sample-id": sample}},
            "container": {"image": "mock"},
        }

    return {
        "metadata": {
            "name": "batch-workflow",
            "labels": {
                "bioops.dev/workload": "submit-master",
                "bioops.dev/batch-id": "B104",
            },
        },
        "spec": {
            "entrypoint": "pipeline",
            "templates": [
                {
                    "name": "pipeline",
                    "dag": {"tasks": [
                        {"name": "sample1-a", "template": "sample1-a"},
                        {"name": "sample1-b", "template": "sample1-b", "dependencies": ["sample1-a"]},
                        {"name": "sample2-a", "template": "sample2-a"},
                        {"name": "sample2-b", "template": "sample2-b", "dependencies": ["sample2-a"]},
                    ]},
                },
                task_template("sample1-a", "sample1"),
                task_template("sample1-b", "sample1"),
                task_template("sample2-a", "sample2"),
                task_template("sample2-b", "sample2"),
            ],
        },
        "status": {
            "phase": "Failed",
            "nodes": {
                "failed": {
                    "phase": "Failed",
                    "templateName": "sample2-b",
                    "message": "NodeLost",
                }
            },
        },
    }


def test_target_retry_spec_keeps_only_failed_sample_chain():
    spec, samples = _target_retry_spec(failed_batch_workflow())
    tasks = spec["templates"][0]["dag"]["tasks"]
    assert samples == ["sample2"]
    assert [task["name"] for task in tasks] == ["sample2-a", "sample2-b"]
    assert {template["name"] for template in spec["templates"]} == {
        "pipeline", "sample2-a", "sample2-b"
    }


def test_batch_retry_labels_target_and_excludes_successful_sample():
    api = FakeApi()
    _resubmit_workflow(
        api=api,
        workflow=failed_batch_workflow(),
        namespace="bioops-dev",
        root_workflow="batch-workflow",
        next_retry_count=1,
    )
    labels = api.created["metadata"]["labels"]
    annotations = api.created["metadata"]["annotations"]
    template_names = {item["name"] for item in api.created["spec"]["templates"]}
    assert labels["bioops.dev/sample-id"] == "sample2"
    assert annotations["bioops.dev/d5-target-samples"] == "sample2"
    assert "sample1-a" not in template_names


def test_batch_retry_fails_closed_without_sample_mapping():
    workflow = failed_batch_workflow()
    workflow["status"]["nodes"]["failed"]["templateName"] = "unknown-template"
    with pytest.raises(ValueError, match="retry scope is unknown"):
        _target_retry_spec(workflow)
