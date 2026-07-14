from bioops.jobs import cluster_health_monitor
from bioops.tools.k8s_health import PodStatus


class FakeAlertTool:
    records: list[tuple[str, str, str]] = []

    def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "warning",
    ):
        self.records.append(
            ("alert", title, severity)
        )

    def send_status(
        self,
        title: str,
        message: str,
    ):
        self.records.append(
            ("status", title, "info")
        )


class FakeHealthTool:
    def __init__(
        self,
        pods: list[PodStatus],
        errors: list[str],
    ) -> None:
        self.pods = pods
        self.errors = errors

    def get_pods(self) -> list[PodStatus]:
        return self.pods

    def get_recent_errors(
        self,
        limit: int = 3,
    ) -> list[str]:
        return self.errors[:limit]


def make_pod(
    *,
    phase: str = "Running",
    pipeline_step: str | None = "bam-to-gvcf",
) -> PodStatus:
    return PodStatus(
        name="pipeline-test",
        namespace="bioops-dev",
        phase=phase,
        node_name="node-test",
        pipeline_step=pipeline_step,
        started_at=None,
        runtime_minutes=12.0,
    )


def install_fakes(
    monkeypatch,
    pods: list[PodStatus],
    errors: list[str],
) -> None:
    FakeAlertTool.records = []

    fake_agent = type(
        "FakeAgent",
        (),
        {
            "health_tool": FakeHealthTool(
                pods,
                errors,
            )
        },
    )()

    monkeypatch.setattr(
        cluster_health_monitor,
        "ClusterHealthAgent",
        lambda: fake_agent,
    )

    monkeypatch.setattr(
        cluster_health_monitor,
        "AlertTool",
        FakeAlertTool,
    )


def test_running_labeled_pod_sends_status(
    monkeypatch,
) -> None:
    install_fakes(
        monkeypatch,
        [make_pod()],
        [],
    )

    cluster_health_monitor.main()

    assert FakeAlertTool.records == [
        (
            "status",
            "1 pipeline pod(s) running",
            "info",
        )
    ]


def test_idle_cluster_sends_no_notification(
    monkeypatch,
) -> None:
    install_fakes(
        monkeypatch,
        [
            make_pod(
                phase="Running",
                pipeline_step=None,
            )
        ],
        [],
    )

    cluster_health_monitor.main()

    assert FakeAlertTool.records == []


def test_recent_errors_send_warning(
    monkeypatch,
) -> None:
    install_fakes(
        monkeypatch,
        [],
        ["pod failed"],
    )

    cluster_health_monitor.main()

    assert FakeAlertTool.records == [
        (
            "alert",
            "Recent Kubernetes pod errors",
            "warning",
        )
    ]
