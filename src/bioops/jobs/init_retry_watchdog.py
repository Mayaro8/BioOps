"""Retry Argo pods whose init containers remain unfinished too long."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException


WORKFLOW_LABEL = "workflows.argoproj.io/workflow"


@dataclass(frozen=True)
class StuckInitPod:
    name: str
    workflow_name: str
    age_minutes: float


def _unfinished_init_container(status: Any) -> bool:
    state = getattr(status, "state", None)
    waiting = getattr(state, "waiting", None)
    running = getattr(state, "running", None)
    return waiting is not None or running is not None


def find_stuck_init_pods(
    pods: list[Any],
    *,
    now: datetime,
    threshold_minutes: int,
) -> list[StuckInitPod]:
    cutoff = now - timedelta(minutes=threshold_minutes)
    stuck: list[StuckInitPod] = []

    for pod in pods:
        labels = getattr(pod.metadata, "labels", None) or {}
        workflow_name = labels.get(WORKFLOW_LABEL)
        if not workflow_name:
            continue

        init_statuses = (
            getattr(pod.status, "init_container_statuses", None) or []
        )
        if not any(_unfinished_init_container(item) for item in init_statuses):
            continue

        started_at = getattr(pod.status, "start_time", None)
        if started_at is None:
            started_at = getattr(pod.metadata, "creation_timestamp", None)
        if started_at is None or started_at >= cutoff:
            continue

        age_minutes = (now - started_at).total_seconds() / 60
        stuck.append(
            StuckInitPod(
                name=pod.metadata.name,
                workflow_name=workflow_name,
                age_minutes=round(age_minutes, 1),
            )
        )

    return sorted(stuck, key=lambda item: item.name)


def retry_stuck_init_pods(
    *,
    namespace: str,
    threshold_minutes: int = 30,
) -> list[StuckInitPod]:
    try:
        config.load_incluster_config()
    except ConfigException:
        config.load_kube_config()

    core_api = client.CoreV1Api()
    response = core_api.list_namespaced_pod(namespace=namespace)
    stuck = find_stuck_init_pods(
        response.items,
        now=datetime.now(timezone.utc),
        threshold_minutes=threshold_minutes,
    )

    for pod in stuck:
        core_api.delete_namespaced_pod(
            name=pod.name,
            namespace=namespace,
            body=client.V1DeleteOptions(
                grace_period_seconds=0,
                propagation_policy="Background",
            ),
        )

    return stuck


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--namespace",
        default=os.getenv("K8S_NAMESPACE", "bioops-dev"),
    )
    parser.add_argument("--threshold-minutes", type=int, default=30)
    args = parser.parse_args()

    retried = retry_stuck_init_pods(
        namespace=args.namespace,
        threshold_minutes=args.threshold_minutes,
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "threshold_minutes": args.threshold_minutes,
                "retried_count": len(retried),
                "pods": [asdict(pod) for pod in retried],
            }
        )
    )


if __name__ == "__main__":
    main()
