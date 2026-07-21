from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bioops.jobs.init_retry_watchdog import find_stuck_init_pods


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def make_pod(
    name: str,
    *,
    age_minutes: int,
    workflow: str | None = "workflow-a",
    init_state: str = "waiting",
):
    state = SimpleNamespace(waiting=None, running=None, terminated=None)
    setattr(state, init_state, SimpleNamespace())
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            labels=(
                {"workflows.argoproj.io/workflow": workflow}
                if workflow
                else {}
            ),
            creation_timestamp=NOW - timedelta(minutes=age_minutes),
        ),
        status=SimpleNamespace(
            start_time=NOW - timedelta(minutes=age_minutes),
            init_container_statuses=[SimpleNamespace(state=state)],
        ),
    )


def test_finds_argo_pod_stuck_in_initialization_over_30_minutes():
    pods = [
        make_pod("stuck", age_minutes=31),
        make_pod("exactly-thirty", age_minutes=30),
        make_pod("not-old-enough", age_minutes=29),
        make_pod("ordinary-pod", age_minutes=60, workflow=None),
        make_pod("completed-init", age_minutes=60, init_state="terminated"),
    ]

    result = find_stuck_init_pods(
        pods,
        now=NOW,
        threshold_minutes=30,
    )

    assert [pod.name for pod in result] == ["stuck"]
    assert result[0].workflow_name == "workflow-a"
    assert result[0].age_minutes == 31.0
