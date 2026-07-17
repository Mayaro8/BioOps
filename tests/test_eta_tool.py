from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.tools.eta_tool import ETAReport, ETATool
from bioops.tools.k8s_health import PodStatus


def test_eta_report_compatibility_aliases() -> None:
    report = ETAReport(
        pod_name="test-pod",
        step_name="bam-to-gvcf",
        expected_minutes=120.0,
        runtime_minutes=30.0,
        remaining_minutes=90.0,
        note="configured estimate",
    )

    assert report.pipeline_step == "bam-to-gvcf"
    assert report.source == "configured estimate"


def test_cluster_health_eta_groups_pods_by_step() -> None:
    agent = ClusterHealthAgent.__new__(ClusterHealthAgent)
    agent.eta_tool = ETATool(
        {
            "bam-to-gvcf": 120,
            "gvcf-to-vcf": 45,
        }
    )

    pods = [
        _pod("bam-a", "bam-to-gvcf", 30.0),
        _pod("bam-b", "bam-to-gvcf", 90.0),
        _pod("vcf-a", "gvcf-to-vcf", 10.0),
        _pod("beagle-a", "beagle", 5.0),
    ]

    assert agent._format_eta_section(pods) == [
        "",
        "ETA:",
        (
            "- bam-to-gvcf: average ~60.0 min remaining "
            "across 2 pods"
        ),
        (
            "- gvcf-to-vcf: average ~35.0 min remaining "
            "across 1 pod"
        ),
    ]


def _pod(
    name: str,
    pipeline_step: str,
    runtime_minutes: float,
) -> PodStatus:
    return PodStatus(
        name=name,
        namespace="bioops-dev",
        phase="Running",
        node_name="worker-1",
        pipeline_step=pipeline_step,
        started_at=None,
        runtime_minutes=runtime_minutes,
    )
