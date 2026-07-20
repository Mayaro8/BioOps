from bioops.jobs import cluster_health_monitor


class FakeAlertTool:
    records: list[tuple[str, str, str, str]] = []

    def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "warning",
    ):
        self.records.append(("alert", title, severity, message))

    def send_status(self, title: str, message: str):
        self.records.append(("status", title, "info", message))


class FakeHealthTool:
    def __init__(self, pods: list[object], errors: list[str]) -> None:
        self.pods = pods
        self.errors = errors

    def get_pods(self) -> list[object]:
        return self.pods

    def get_recent_errors(self, limit: int = 3) -> list[str]:
        return self.errors[:limit]


class FakeAgent:
    error_report_limit = 20

    def __init__(self, pods: list[object], errors: list[str]) -> None:
        self.health_tool = FakeHealthTool(pods, errors)

    @staticmethod
    def format_overall_health(
        pods: list[object],
        errors: list[str],
    ) -> str:
        status = "Degraded" if errors else "Healthy"
        return f"Overall status: {status}\nTotal pods: {len(pods)}"

    @staticmethod
    def format_analyzed_errors(errors: list[str]) -> str:
        return "Analyzed Pod Errors\n" + "\n".join(errors)


def install_fakes(
    monkeypatch,
    pods: list[object],
    errors: list[str],
) -> None:
    FakeAlertTool.records = []
    monkeypatch.setattr(
        cluster_health_monitor,
        "ClusterHealthAgent",
        lambda: FakeAgent(pods, errors),
    )
    monkeypatch.setattr(
        cluster_health_monitor,
        "AlertTool",
        FakeAlertTool,
    )


def test_hourly_check_always_sends_full_status(monkeypatch) -> None:
    install_fakes(monkeypatch, [object(), object()], [])

    cluster_health_monitor.main("status")

    assert FakeAlertTool.records == [
        (
            "status",
            "Hourly cluster health: Healthy",
            "info",
            "Overall status: Healthy\nTotal pods: 2",
        )
    ]


def test_hourly_check_sends_status_while_idle(monkeypatch) -> None:
    install_fakes(monkeypatch, [], [])

    cluster_health_monitor.main("status")

    assert FakeAlertTool.records[0][0] == "status"
    assert FakeAlertTool.records[0][1] == "Hourly cluster health: Healthy"


def test_error_check_sends_analyzed_critical_notification(monkeypatch) -> None:
    install_fakes(monkeypatch, [], ["sample/container OOMKilled"])

    cluster_health_monitor.main("errors")

    assert FakeAlertTool.records[0][:3] == (
        "alert",
        "1 recent Kubernetes pod error finding",
        "critical",
    )
    assert "Analyzed Pod Errors" in FakeAlertTool.records[0][3]


def test_error_check_is_quiet_when_no_errors(monkeypatch) -> None:
    install_fakes(monkeypatch, [], [])

    cluster_health_monitor.main("errors")

    assert FakeAlertTool.records == []
