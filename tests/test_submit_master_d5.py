from bioops.jobs.submit_master_d5_retry_bitrix_report import (
    _has_active_retry,
    _resubmit_workflow,
    _retry_decision,
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
