from bioops.jobs import infra_cost_monitor


def test_infra_cost_monitor_sends_alert_for_vm_findings(monkeypatch) -> None:
    events = []

    class FakeAgent:
        def run(self, message: str) -> str:
            return (
                "Infra & Cost Report\n\n"
                "Compute Cloud VMs:\n"
                "- Checked: 6\n"
                "- Alerts: 1\n\n"
                "Findings:\n\n"
                "WARNING: expensive-cpu-long"
            )

    class FakeAlertTool:
        def send_alert(
            self,
            title: str,
            message: str,
            severity: str = "warning",
        ) -> None:
            events.append(("alert", title, severity, message))

        def send_status(self, title: str, message: str) -> None:
            events.append(("status", title, message))

    monkeypatch.setattr(infra_cost_monitor, "InfraCostAgent", FakeAgent)
    monkeypatch.setattr(infra_cost_monitor, "AlertTool", FakeAlertTool)

    infra_cost_monitor.main()

    assert len(events) == 1
    assert events[0][0] == "alert"
    assert events[0][1] == "Expensive VM detected"
    assert events[0][2] == "warning"


def test_infra_cost_monitor_sends_status_when_no_findings(monkeypatch) -> None:
    events = []

    class FakeAgent:
        def run(self, message: str) -> str:
            return (
                "Infra & Cost Report\n\n"
                "Compute Cloud VMs:\n"
                "- Checked: 6\n"
                "- Alerts: 0\n\n"
                "No expensive long-running VMs detected."
            )

    class FakeAlertTool:
        def send_alert(
            self,
            title: str,
            message: str,
            severity: str = "warning",
        ) -> None:
            events.append(("alert", title, severity, message))

        def send_status(self, title: str, message: str) -> None:
            events.append(("status", title, message))

    monkeypatch.setattr(infra_cost_monitor, "InfraCostAgent", FakeAgent)
    monkeypatch.setattr(infra_cost_monitor, "AlertTool", FakeAlertTool)

    infra_cost_monitor.main()

    assert len(events) == 1
    assert events[0][0] == "status"
    assert events[0][1] == "Infrastructure cost OK"


def test_infra_cost_monitor_sends_critical_alert_when_agent_fails(
    monkeypatch,
) -> None:
    events = []

    class FakeAgent:
        def run(self, message: str) -> str:
            raise RuntimeError("boom")

    class FakeAlertTool:
        def send_alert(
            self,
            title: str,
            message: str,
            severity: str = "warning",
        ) -> None:
            events.append(("alert", title, severity, message))

        def send_status(self, title: str, message: str) -> None:
            events.append(("status", title, message))

    monkeypatch.setattr(infra_cost_monitor, "InfraCostAgent", FakeAgent)
    monkeypatch.setattr(infra_cost_monitor, "AlertTool", FakeAlertTool)

    infra_cost_monitor.main()

    assert len(events) == 1
    assert events[0][0] == "alert"
    assert events[0][1] == "Infra cost monitor failed"
    assert events[0][2] == "critical"
    assert "boom" in events[0][3]


def test_infra_cost_monitor_sends_critical_alert_when_report_unavailable(
    monkeypatch,
) -> None:
    events = []

    class FakeAgent:
        def run(self, message: str) -> str:
            return (
                "Infra & Cost Report\n\n"
                "Status: unavailable\n"
                "Reason: failed to check Compute Cloud VMs"
            )

    class FakeAlertTool:
        def send_alert(
            self,
            title: str,
            message: str,
            severity: str = "warning",
        ) -> None:
            events.append(("alert", title, severity, message))

        def send_status(self, title: str, message: str) -> None:
            events.append(("status", title, message))

    monkeypatch.setattr(infra_cost_monitor, "InfraCostAgent", FakeAgent)
    monkeypatch.setattr(infra_cost_monitor, "AlertTool", FakeAlertTool)

    infra_cost_monitor.main()

    assert len(events) == 1
    assert events[0][0] == "alert"
    assert events[0][1] == "Infra cost monitor unavailable"
    assert events[0][2] == "critical"
