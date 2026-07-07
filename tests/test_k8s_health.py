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
