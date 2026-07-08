from bioops.tools.eta_tool import ETAReport


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
