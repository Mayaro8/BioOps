from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.tools.alert_tool import AlertTool


FAILURE_KEYWORDS = [
    "unhealthy",
    "failed",
    "error",
    "exception",
    "traceback",
    "oomkilled",
    "crashloopbackoff",
]


RUNNING_KEYWORDS = [
    "currently running",
    "running pipeline steps",
    "running pods",
]


def report_has_failure(report: str) -> bool:
    lowered = report.lower()
    return any(keyword in lowered for keyword in FAILURE_KEYWORDS)


def report_has_running_work(report: str) -> bool:
    lowered = report.lower()

    if "no running pipeline steps found" in lowered:
        return False

    return any(keyword in lowered for keyword in RUNNING_KEYWORDS)


def main() -> None:
    alert_tool = AlertTool()

    try:
        agent = ClusterHealthAgent()
        report = agent.run("scheduled cluster health check")
    except Exception as error:
        alert_tool.send_alert(
            title="Cluster health monitor failed",
            message=f"Error: {error}",
            severity="critical",
        )
        return

    if report_has_failure(report):
        alert_tool.send_alert(
            title="Cluster issue detected",
            message=report,
            severity="warning",
        )
        return

    if report_has_running_work(report):
        alert_tool.send_status(
            title="Pipeline is running",
            message=report,
        )
        return

    alert_tool.send_status(
        title="Cluster health OK",
        message=report,
    )


if __name__ == "__main__":
    main()
