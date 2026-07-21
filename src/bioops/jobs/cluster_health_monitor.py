from __future__ import annotations

import argparse

from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.tools.alert_tool import AlertTool
from bioops.tools.pod_error_analysis import analyze_pod_errors


def _error_severity(errors: list[str]) -> str:
    analyses = analyze_pod_errors(errors)
    if any(item.severity == "critical" for item in analyses):
        return "critical"
    return "warning"


def run_error_check(
    agent: ClusterHealthAgent,
    alerts: AlertTool,
) -> None:
    errors = agent.health_tool.get_recent_errors(
        limit=agent.error_report_limit,
    )
    if not errors:
        print("No recent pod errors. No browser notification sent.")
        return

    finding_word = "finding" if len(errors) == 1 else "findings"
    alerts.send_alert(
        title=f"{len(errors)} recent workflow pod error {finding_word}",
        message=agent.format_analyzed_errors(errors),
        severity=_error_severity(errors),
    )


def run_hourly_health_check(
    agent: ClusterHealthAgent,
    alerts: AlertTool,
) -> None:
    pods = agent.health_tool.get_pods()
    errors = agent.health_tool.get_recent_errors(
        limit=agent.error_report_limit,
    )
    report = agent.format_overall_health(pods, errors)
    status = (
        "Degraded"
        if "Overall status: Degraded" in report
        else "Healthy"
    )

    alerts.send_status(
        title=f"Hourly workflow health: {status}",
        message=report,
    )


def main(mode: str = "status") -> None:
    alerts = AlertTool()

    try:
        agent = ClusterHealthAgent()
        if mode == "errors":
            run_error_check(agent, alerts)
        elif mode == "status":
            run_hourly_health_check(agent, alerts)
        else:
            raise ValueError(f"Unsupported cluster health monitor mode: {mode}")
    except Exception as error:
        alerts.send_alert(
            title=f"Workflow health {mode} monitor failed",
            message=f"{type(error).__name__}: {error}",
            severity="critical",
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a deterministic workflow pod health scheduled check."
    )
    parser.add_argument(
        "--mode",
        choices=("status", "errors"),
        default="status",
        help="status sends the hourly C1 report; errors sends C2 findings.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main(_parse_args().mode)
