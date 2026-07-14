from __future__ import annotations

from bioops.agents.cluster_health_agent import (
    ClusterHealthAgent,
)
from bioops.tools.alert_tool import AlertTool
from bioops.tools.k8s_health import PodStatus


def running_pipeline_pods(
    pods: list[PodStatus],
) -> list[PodStatus]:
    """Return only labeled pipeline pods that are running."""

    return [
        pod
        for pod in pods
        if pod.phase == "Running"
        and bool(pod.pipeline_step)
    ]


def format_pipeline_report(
    pods: list[PodStatus],
    errors: list[str],
) -> str:
    lines = [
        f"Active pipeline pods: {len(pods)}",
        "",
    ]

    for pod in pods:
        runtime = (
            f"{pod.runtime_minutes:.1f} min"
            if pod.runtime_minutes is not None
            else "unknown"
        )

        node = pod.node_name or "unscheduled"

        lines.append(
            f"- Step: {pod.pipeline_step}\n"
            f"  Pod: {pod.name}\n"
            f"  Runtime: {runtime}\n"
            f"  Node: {node}"
        )

    if errors:
        lines.extend(
            [
                "",
                "Last pod errors:",
                *(
                    f"- {error}"
                    for error in errors[:3]
                ),
            ]
        )

    return "\n".join(lines)


def format_error_report(errors: list[str]) -> str:
    return "\n".join(
        [
            "Last pod errors:",
            *(
                f"- {error}"
                for error in errors[:3]
            ),
        ]
    )


def main() -> None:
    alerts = AlertTool()

    try:
        agent = ClusterHealthAgent()

        pods = agent.health_tool.get_pods()
        errors = agent.health_tool.get_recent_errors(
            limit=3
        )
    except Exception as error:
        alerts.send_alert(
            title="Cluster health monitor failed",
            message=(
                f"{type(error).__name__}: {error}"
            ),
            severity="critical",
        )
        return

    active_pods = running_pipeline_pods(pods)

    if errors:
        alerts.send_alert(
            title="Recent Kubernetes pod errors",
            message=(
                format_pipeline_report(
                    active_pods,
                    errors,
                )
                if active_pods
                else format_error_report(errors)
            ),
            severity="warning",
        )
        return

    if active_pods:
        alerts.send_status(
            title=(
                f"{len(active_pods)} pipeline pod(s) running"
            ),
            message=format_pipeline_report(
                active_pods,
                [],
            ),
        )
        return

    # C5 does not require repeated notifications while idle.
    print(
        "No running labeled pipeline pods and no recent "
        "errors. No browser notification sent."
    )


if __name__ == "__main__":
    main()
