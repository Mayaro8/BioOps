from types import SimpleNamespace

from kubernetes.config.config_exception import ConfigException

from bioops.tools import k8s_health
from bioops.tools.k8s_health import K8sHealthTool


def test_uses_incluster_config_inside_kubernetes(monkeypatch) -> None:
    calls: list[str] = []
    fake_api = object()

    monkeypatch.setattr(
        k8s_health.config,
        "load_incluster_config",
        lambda: calls.append("incluster"),
    )
    monkeypatch.setattr(
        k8s_health.config,
        "load_kube_config",
        lambda: calls.append("kubeconfig"),
    )
    monkeypatch.setattr(
        k8s_health.client,
        "CoreV1Api",
        lambda: fake_api,
    )

    tool = K8sHealthTool(namespace="bioops-dev")

    assert calls == ["incluster"]
    assert tool.core_api is fake_api
    assert tool.namespace == "bioops-dev"


def test_falls_back_to_local_kubeconfig(monkeypatch) -> None:
    calls: list[str] = []
    fake_api = object()

    def fail_incluster_config() -> None:
        calls.append("incluster")
        raise ConfigException("Not running inside Kubernetes")

    monkeypatch.setattr(
        k8s_health.config,
        "load_incluster_config",
        fail_incluster_config,
    )
    monkeypatch.setattr(
        k8s_health.config,
        "load_kube_config",
        lambda: calls.append("kubeconfig"),
    )
    monkeypatch.setattr(
        k8s_health.client,
        "CoreV1Api",
        lambda: fake_api,
    )

    tool = K8sHealthTool()

    assert calls == ["incluster", "kubeconfig"]
    assert tool.core_api is fake_api


def test_get_pod_logs_uses_configured_tail_lines(monkeypatch) -> None:
    received: dict[str, object] = {}

    class FakeCoreApi:
        def read_namespaced_pod_log(self, **kwargs):
            received.update(kwargs)
            return "pod output"

    monkeypatch.setattr(
        k8s_health.config,
        "load_incluster_config",
        lambda: None,
    )
    monkeypatch.setattr(
        k8s_health.client,
        "CoreV1Api",
        FakeCoreApi,
    )

    tool = K8sHealthTool(
        namespace="bioops-dev",
        request_timeout_seconds=7,
        log_tail_lines=25,
    )

    result = tool.get_pod_logs("bioops-api-test")

    assert result == "pod output"
    assert received == {
        "name": "bioops-api-test",
        "namespace": "bioops-dev",
        "tail_lines": 25,
        "_request_timeout": 7,
    }


def test_no_recent_errors_returns_empty_list(monkeypatch) -> None:
    running_pod = SimpleNamespace(
        metadata=SimpleNamespace(name="bioops-api-test"),
        status=SimpleNamespace(
            phase="Running",
            container_statuses=[],
        ),
    )

    class FakeCoreApi:
        def list_namespaced_pod(self, **kwargs):
            return SimpleNamespace(items=[running_pod])

    monkeypatch.setattr(
        k8s_health.config,
        "load_incluster_config",
        lambda: None,
    )
    monkeypatch.setattr(
        k8s_health.client,
        "CoreV1Api",
        FakeCoreApi,
    )

    tool = K8sHealthTool(namespace="bioops-dev")

    assert tool.get_recent_errors() == []


def test_normal_container_creating_state_is_not_an_error(monkeypatch) -> None:
    waiting = SimpleNamespace(
        reason="ContainerCreating",
        message="Container image is being prepared",
    )
    status = SimpleNamespace(
        name="pipeline",
        state=SimpleNamespace(waiting=waiting, terminated=None),
    )
    pending_pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="pipeline-test",
            labels={
                "workflows.argoproj.io/workflow": "workflow-test",
            },
        ),
        status=SimpleNamespace(
            phase="Pending",
            start_time=None,
            init_container_statuses=[],
            container_statuses=[status],
        ),
    )

    class FakeCoreApi:
        def list_namespaced_pod(self, **_kwargs):
            return SimpleNamespace(items=[pending_pod])

        def read_namespaced_pod_log(self, **_kwargs):
            return "still starting"

    monkeypatch.setattr(
        k8s_health.config,
        "load_incluster_config",
        lambda: None,
    )
    monkeypatch.setattr(
        k8s_health.client,
        "CoreV1Api",
        FakeCoreApi,
    )

    tool = K8sHealthTool(namespace="bioops-dev")

    assert tool.get_recent_errors() == []


def test_image_pull_backoff_is_reported(monkeypatch) -> None:
    waiting = SimpleNamespace(
        reason="ImagePullBackOff",
        message="registry denied access",
    )
    status = SimpleNamespace(
        name="pipeline",
        state=SimpleNamespace(waiting=waiting, terminated=None),
    )
    pending_pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="pipeline-test",
            labels={
                "workflows.argoproj.io/workflow": "workflow-test",
            },
        ),
        status=SimpleNamespace(
            phase="Pending",
            start_time=None,
            init_container_statuses=[],
            container_statuses=[status],
        ),
    )

    class FakeCoreApi:
        def list_namespaced_pod(self, **_kwargs):
            return SimpleNamespace(items=[pending_pod])

        def read_namespaced_pod_log(self, **_kwargs):
            return ""

    monkeypatch.setattr(
        k8s_health.config,
        "load_incluster_config",
        lambda: None,
    )
    monkeypatch.setattr(
        k8s_health.client,
        "CoreV1Api",
        FakeCoreApi,
    )

    tool = K8sHealthTool(namespace="bioops-dev")

    errors = tool.get_recent_errors()

    assert len(errors) == 1
    assert "ImagePullBackOff" in errors[0]


def test_get_pods_captures_argo_workflow_labels(monkeypatch) -> None:
    pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="workflow-test-fastqc",
            namespace="bioops-dev",
            labels={
                "workflows.argoproj.io/workflow": "workflow-test",
                "bioops.dev/batch-id": "batch-1",
                "bioops.dev/sample-id": "sample-1",
                "pipeline_step": "fastqc",
            },
        ),
        spec=SimpleNamespace(node_name="worker-1"),
        status=SimpleNamespace(
            phase="Running",
            start_time=None,
        ),
    )

    class FakeCoreApi:
        def list_namespaced_pod(self, **_kwargs):
            return SimpleNamespace(items=[pod])

    monkeypatch.setattr(
        k8s_health.config,
        "load_incluster_config",
        lambda: None,
    )
    monkeypatch.setattr(
        k8s_health.client,
        "CoreV1Api",
        FakeCoreApi,
    )

    result = K8sHealthTool(namespace="bioops-dev").get_pods()

    assert len(result) == 1
    assert result[0].workflow_name == "workflow-test"
    assert result[0].batch_id == "batch-1"
    assert result[0].sample_id == "sample-1"
    assert result[0].pipeline_step == "fastqc"


def test_get_node_pressure_report_aggregates_metrics_and_scheduling(
    monkeypatch,
) -> None:
    def condition(kind: str, status: str = "True"):
        return SimpleNamespace(type=kind, status=status)

    nodes = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="worker-1"),
            status=SimpleNamespace(
                conditions=[condition("Ready"), condition("MemoryPressure")],
                allocatable={"cpu": "4", "memory": "8Gi", "pods": "110"},
            ),
        ),
        SimpleNamespace(
            metadata=SimpleNamespace(name="worker-2"),
            status=SimpleNamespace(
                conditions=[condition("Ready", "False")],
                allocatable={"cpu": "4", "memory": "8Gi", "pods": "110"},
            ),
        ),
    ]
    pending = SimpleNamespace(
        metadata=SimpleNamespace(
            name="workflow-pending",
            namespace="bioops-dev",
            labels={"workflows.argoproj.io/workflow": "workflow-a"},
        ),
        spec=SimpleNamespace(node_name=None),
        status=SimpleNamespace(
            phase="Pending",
            conditions=[
                SimpleNamespace(
                    type="PodScheduled",
                    status="False",
                    reason="Unschedulable",
                    message="0/2 nodes: 2 Insufficient memory.",
                )
            ],
        ),
    )
    running = SimpleNamespace(
        metadata=SimpleNamespace(
            name="running", namespace="other", labels={}
        ),
        spec=SimpleNamespace(node_name="worker-1"),
        status=SimpleNamespace(phase="Running", conditions=[]),
    )

    class FakeCoreApi:
        def list_node(self, **_kwargs):
            return SimpleNamespace(items=nodes)

        def list_pod_for_all_namespaces(self, **_kwargs):
            return SimpleNamespace(items=[pending, running])

    class FakeMetricsApi:
        def list_cluster_custom_object(self, **_kwargs):
            return {
                "items": [
                    {
                        "metadata": {"name": "worker-1"},
                        "usage": {"cpu": "2", "memory": "4Gi"},
                    },
                    {
                        "metadata": {"name": "worker-2"},
                        "usage": {"cpu": "1", "memory": "2Gi"},
                    },
                ]
            }

    monkeypatch.setattr(
        k8s_health.config, "load_incluster_config", lambda: None
    )
    monkeypatch.setattr(k8s_health.client, "CoreV1Api", FakeCoreApi)
    monkeypatch.setattr(
        k8s_health.client, "CustomObjectsApi", FakeMetricsApi
    )

    report = K8sHealthTool(namespace="bioops-dev").get_node_pressure_report()

    assert len(report.nodes) == 2
    assert report.nodes[0].memory_pressure is True
    assert report.nodes[1].ready is False
    assert report.active_pods == 2
    assert report.pod_capacity == 220
    assert report.cpu_usage_percent == 37.5
    assert report.memory_usage_percent == 37.5
    assert report.metrics_nodes == 2
    assert report.unschedulable_workflow_pods == 1
    assert report.scheduling_reasons == {"Insufficient memory": 1}
