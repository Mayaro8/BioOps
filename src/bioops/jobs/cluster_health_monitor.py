from __future__ import annotations

from statistics import fmean, quantiles

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
    total_pods = len(pods)
    pods_by_step: dict[str, int] = {}

    for pod in pods:
        step = pod.pipeline_step or "unknown"
        pods_by_step[step] = pods_by_step.get(step, 0) + 1

    lines = [
        f"Active pipeline pods: {total_pods}",
        "",
        "Pipeline steps:",
    ]

    for step, count in sorted(pods_by_step.items()):
        percentage = count / total_pods * 100
        pod_word = "pod" if count == 1 else "pods"

        lines.append(
            f"- {step}: {count} {pod_word} "
            f"({percentage:.1f}%)"
        )

    runtime_pods = [
        pod
        for pod in pods
        if pod.runtime_minutes is not None
    ]

    if runtime_pods:
        runtimes = sorted(
            float(pod.runtime_minutes)
            for pod in runtime_pods
            if pod.runtime_minutes is not None
        )

        if len(runtimes) == 1:
            q1 = q2 = q3 = runtimes[0]
        else:
            q1, q2, q3 = quantiles(
                runtimes,
                n=4,
                method="inclusive",
            )

        shortest = min(
            runtime_pods,
            key=lambda pod: float(
                pod.runtime_minutes or 0.0
            ),
        )
        longest = max(
            runtime_pods,
            key=lambda pod: float(
                pod.runtime_minutes or 0.0
            ),
        )

        lines.extend(
            [
                "",
                "Runtime statistics:",
                f"- Average: {fmean(runtimes):.1f} min",
                f"- Q1: {q1:.1f} min",
                f"- Median: {q2:.1f} min",
                f"- Q3: {q3:.1f} min",
                (
                    f"- Shortest: {shortest.name} "
                    f"({shortest.pipeline_step}, "
                    f"{shortest.runtime_minutes:.1f} min)"
                ),
                (
                    f"- Longest: {longest.name} "
                    f"({longest.pipeline_step}, "
                    f"{longest.runtime_minutes:.1f} min)"
                ),
            ]
        )

    if errors:
        lines.extend(
            [
                "",
                "Last pod errors:",
                *(f"- {error}" for error in errors[:3]),
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
