from pathlib import Path

from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.tools.k8s_health import (
    NodePressureReport,
    NodePressureStatus,
    PodStatus,
)
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

    def get_node_pressure_report(self) -> NodePressureReport:
        self.queries.append("nodes")
        return NodePressureReport(
            nodes=[
                NodePressureStatus(
                    name="worker-1",
                    ready=True,
                    memory_pressure=True,
                    disk_pressure=False,
                    pid_pressure=False,
                    network_unavailable=False,
                ),
                NodePressureStatus(
                    name="worker-2",
                    ready=False,
                    memory_pressure=False,
                    disk_pressure=False,
                    pid_pressure=False,
                    network_unavailable=False,
                ),
            ],
            active_pods=150,
            pod_capacity=220,
            cpu_usage_percent=68.4,
            memory_usage_percent=81.2,
            metrics_nodes=2,
            unschedulable_workflow_pods=10,
            scheduling_reasons={"Insufficient memory": 7, "Insufficient CPU": 3},
        )


def make_pod(
    name: str,
    phase: str,
    step: str | None = None,
    runtime: float | None = 10.0,
    workflow: str | None = None,
    batch_id: str | None = None,
    sample_id: str | None = None,
) -> PodStatus:
    return PodStatus(
        name=name,
        namespace="bioops-dev",
        phase=phase,
        node_name="node-test",
        pipeline_step=step,
        started_at=None,
        runtime_minutes=runtime,
        workflow_name=workflow,
        batch_id=batch_id,
        sample_id=sample_id,
    )


def cluster_pods() -> list[PodStatus]:
    return [
        make_pod("bioops-api-1", "Running"),
        make_pod("qdrant-1", "Running"),
        make_pod(
            "sample-1",
            "Running",
            "fastqc",
            workflow="workflow-a",
            batch_id="batch-1",
            sample_id="sample-1",
        ),
        make_pod(
            "sample-2",
            "Running",
            "fastqc",
            workflow="workflow-a",
            batch_id="batch-1",
            sample_id="sample-2",
        ),
        make_pod(
            "sample-3",
            "Running",
            "align-reference",
            workflow="workflow-b",
            batch_id="batch-2",
            sample_id="sample-3",
        ),
        make_pod(
            "sample-4",
            "Pending",
            "align-reference",
            workflow="workflow-b",
            batch_id="batch-2",
            sample_id="sample-4",
        ),
        make_pod(
            "sample-5",
            "Succeeded",
            "validate-fastq",
            workflow="workflow-b",
            batch_id="batch-2",
            sample_id="sample-5",
        ),
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

    assert "Workflow Health Report" in report
    assert "Batches represented: 2" in report
    assert "Workflows observed: 2" in report
    assert "Samples represented: 5" in report
    assert "Total workflow pods: 5" in report
    assert "Batch: batch-1" in report
    assert "Workflows: 1" in report
    assert "Samples represented: 2" in report
    assert "Running: 1 workflow (100.0% of workflows)" in report
    assert "Running: 2 pods (100.0% of workflow pods)" in report
    assert "fastqc: 2 pods (100.0% of active workflow pods)" in report
    assert "Batch: batch-2" in report
    assert "Pending: 1 pod (33.3% of workflow pods)" in report
    assert "Succeeded: 1 pod (33.3% of workflow pods)" in report
    assert "align-reference: 1 pod (100.0% of active workflow pods)" in report
    assert "Workflow: workflow-a" not in report
    assert "sample-1" not in report
    assert "bioops-api" not in report
    assert "qdrant" not in report


def test_large_batch_is_aggregated_without_listing_samples(
    tmp_path: Path,
) -> None:
    pods = [
        make_pod(
            f"pod-{index}",
            (
                "Running"
                if index < 490
                else "Pending"
                if index < 630
                else "Succeeded"
            ),
            "fastqc" if index < 350 else "align-reference",
            workflow=f"workflow-{index}",
            batch_id="batch-700",
            sample_id=f"sample-{index}",
        )
        for index in range(700)
    ]
    agent = build_agent(
        tmp_path,
        "overall_health",
        FakeHealthTool(pods),
    )

    report = agent.run("show workflow health")

    assert "Batches represented: 1" in report
    assert "Workflows observed: 700" in report
    assert "Samples represented: 700" in report
    assert "Running: 490 workflows (70.0% of workflows)" in report
    assert "Pending: 140 workflows (20.0% of workflows)" in report
    assert "Succeeded: 70 workflows (10.0% of workflows)" in report
    assert "fastqc: 350 pods (71.4% of active workflow pods)" in report
    assert "align-reference: 140 pods (28.6% of active workflow pods)" in report
    assert "sample-699" not in report
    assert "pod-699" not in report


def test_running_steps_action_only_queries_pods(tmp_path: Path) -> None:
    health_tool = FakeHealthTool(cluster_pods())
    agent = build_agent(tmp_path, "running_steps", health_tool)

    report = agent.run("what work is happening")

    assert "Current Workflow Pipeline Steps" in report
    assert "Active workflows: 2" in report
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


def test_node_pressure_action_returns_aggregate_node_report(
    tmp_path: Path,
) -> None:
    health_tool = FakeHealthTool([])
    agent = build_agent(tmp_path, "node_pressure", health_tool)

    report = agent.run("show node pressure")

    assert "Kubernetes Node Pressure Report" in report
    assert "Overall status: Degraded" in report
    assert "managed control-plane internals are provider-managed" in report
    assert "Ready nodes: 1 (50.0%)" in report
    assert "MemoryPressure: 1 nodes (50.0%)" in report
    assert "CPU usage: 68.4%" in report
    assert "Pod capacity: 150/220 active pods (68.2%)" in report
    assert "Unschedulable workflow pods: 10" in report
    assert "Insufficient memory: 7 pods (70.0%)" in report
    assert health_tool.queries == ["nodes"]


def test_node_pressure_router_understands_master_node_wording() -> None:
    prompt = ClusterHealthAgent._build_action_router()._build_prompt(
        "Show master node report"
    )

    assert "master node report" in prompt
    assert '"action": "node_pressure"' in prompt
    assert "control-plane report" in prompt


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
