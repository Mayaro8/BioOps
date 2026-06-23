from bioops.tools.submit_master_parameter_matcher import SubmitMasterParameterMatcher


def test_matcher_reports_complete_step_when_required_params_present():
    matcher = SubmitMasterParameterMatcher()

    result = matcher.match(
        provided_parameters={
            "stage": "stage2",
            "step": "haplotypecaller",
            "seq_type": "illumina",
            "cluster_name": "k8s-prod",
            "mongo_cluster_name": "mongo-prod",
            "namespace": "bioops",
            "batch_id": "batch140325",
        },
        candidate_stage="stage2",
        candidate_step="haplotypecaller",
        candidate_platform="illumina",
    )

    assert result.ready is True
    assert result.completion_percent == 100
    assert result.stage == "stage2"
    assert result.step == "haplotypecaller"
    assert result.missing_parameters == []


def test_matcher_returns_closest_step_and_missing_parameters():
    matcher = SubmitMasterParameterMatcher()

    result = matcher.match(
        provided_parameters={
            "stage": "stage2",
            "step": "haplotypecaller",
            "seq_type": "illumina",
            "namespace": "bioops",
            "batch_id": "batch140325",
        },
        candidate_stage="stage2",
        candidate_step="haplotypecaller",
        candidate_platform="illumina",
    )

    assert result.ready is False
    assert result.completion_percent < 100
    assert result.stage == "stage2"
    assert result.step == "haplotypecaller"
    assert "cluster_name" in result.missing_parameters
