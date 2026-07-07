"""Scheduled Infra & Cost monitor for BioOps Epic E."""

from __future__ import annotations

from bioops.agents.infra_cost_agent import InfraCostAgent
from bioops.tools.alert_tool import AlertTool


def report_has_compute_alerts(report: str) -> bool:
    """Return True when the InfraCostAgent report contains VM findings."""

    lowered = report.lower()

    if "alerts: 0" in lowered:
        return False

    return "warning:" in lowered or "alerts:" in lowered


def report_is_unavailable(report: str) -> bool:
    """Return True when the monitor could not check infrastructure."""

    return "status: unavailable" in report.lower()


def main() -> None:
    alert_tool = AlertTool()

    try:
        agent = InfraCostAgent()
        report = agent.run("scheduled infrastructure cost check")
    except Exception as error:
        alert_tool.send_alert(
            title="Infra cost monitor failed",
            message=f"Error: {error}",
            severity="critical",
        )
        return

    if report_is_unavailable(report):
        alert_tool.send_alert(
            title="Infra cost monitor unavailable",
            message=report,
            severity="critical",
        )
        return

    if report_has_compute_alerts(report):
        alert_tool.send_alert(
            title="Expensive VM detected",
            message=report,
            severity="warning",
        )
        return

    alert_tool.send_status(
        title="Infrastructure cost OK",
        message=report,
    )


if __name__ == "__main__":
    main()
