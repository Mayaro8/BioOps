from pathlib import Path

from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.tools.k8s_health import PodStatus
from bioops.tools.llm_action_router import ActionDecision


class FakeActionRouter:
    def __init__(self, action: str) -> None:
        self.action = action

    def route(self, _message: str) -> ActionDecision:
        return ActionDecision(
            action=self.action,
            parameters={},
            reason="test",
        )


class FailingActionRouter:
    def route(self, _message: str) -> ActionDecision:
        raise RuntimeError("router unavailable")


class FakeHealthTool:
    recent_error_minutes = 60

    def __init__(
        self,
        pods: list[PodStatus],
        errors: list[str] | None = None,
    ) -> None:
        self.pods = pods
        self.errors = errors or []
        self.queries: list[str] = []

    def get_pods(self) -> list[PodStatus]:
        self.queries.append("pods")
        return self.pods

    def get_recent_errors(self, limit: int = 3) -> list[str]:
        self.queries.append(f"errors:{limit}")
        return self.errors[:limit]


def make_pod(
    name: str,
    phase: str,
    step: str | None = None,
    runtime: float | None = 10.0,
) -> PodStatus:
    return PodStatus(
        name=name,
        namespace="bioops-dev",
        phase=phase,
        node_name="node-test",
        pipeline_step=step,
        started_at=None,
        runtime_minutes=runtime,
    )


def cluster_pods() -> list[PodStatus]:
    return [
        make_pod("bioops-api-1", "Running"),
        make_pod("qdrant-1", "Running"),
        make_pod("sample-1", "Running", "fastqc"),
        make_pod("sample-2", "Running", "fastqc"),
        make_pod("sample-3", "Running", "align-reference"),
        make_pod("sample-4", "Pending", "align-reference"),
        make_pod("sample-5", "Succeeded", "validate-fastq"),
    ]


def build_agent(
    tmp_path: Path,
    action: str,
    health_tool: FakeHealthTool,
) -> ClusterHealthAgent:
    return ClusterHealthAgent(
        health_tool=health_tool,
        config_path=str(tmp_path / "missing.yaml"),
        action_router=FakeActionRouter(action),
    )


def test_overall_health_reports_phase_and_step_percentages(
    tmp_path: Path,
) -> None:
    agent = build_agent(
        tmp_path,
        "overall_health",
        FakeHealthTool(cluster_pods()),
    )

    report = agent.run("natural-language overall question")

    assert "Running: 5 pods (71.4% of all pods)" in report
    assert "Pending: 1 pod (14.3% of all pods)" in report
    assert "Succeeded: 1 pod (14.3% of all pods)" in report
    assert "fastqc: 2 pods (66.7% of active pipeline pods)" in report
    assert "align-reference: 1 pod (33.3% of active pipeline pods)" in report


def test_running_steps_action_only_queries_pods(tmp_path: Path) -> None:
    health_tool = FakeHealthTool(cluster_pods())
    agent = build_agent(tmp_path, "running_steps", health_tool)

    report = agent.run("what work is happening")

    assert "Current Pipeline Steps" in report
    assert health_tool.queries == ["pods"]


def test_recent_errors_returns_analyzed_log(tmp_path: Path) -> None:
    agent = build_agent(
        tmp_path,
        "recent_errors",
        FakeHealthTool([], ["sample/container OOMKilled"]),
    )

    report = agent.run("diagnose the failed pod")

    assert "Category: resource_exhaustion" in report
    assert "Likely cause: The container exceeded its memory limit." in report
    assert "Evidence: sample/container OOMKilled" in report


def test_inner_llm_failure_does_not_query_kubernetes(tmp_path: Path) -> None:
    health_tool = FakeHealthTool(cluster_pods())
    agent = ClusterHealthAgent(
        health_tool=health_tool,
        config_path=str(tmp_path / "missing.yaml"),
        action_router=FailingActionRouter(),
    )

    report = agent.run("check it")

    assert "Status: action_routing_error" in report
    assert health_tool.queries == []
