from bioops.tools.submit_master_config_creator import (
    SubmitMasterConfigCreatorCatalog,
    SubmitMethodContract,
)
from bioops.tools.submit_master_parameter_matcher import SubmitMasterParameterMatcher


def test_matcher_does_not_ask_for_params_provided_by_config_creator():
    catalog = SubmitMasterConfigCreatorCatalog(
        method_map={"haplotypecaller": "submit_haplotypecaller"},
        method_contracts={
            "submit_haplotypecaller": SubmitMethodContract(
                submit_method="submit_haplotypecaller",
                required_parameters=(
                    "paths",
                    "input_paths_list",
                    "reference_panel",
                    "regions_without_homopolymers",
                ),
                provided_by_config_creator=(
                    "paths",
                    "input_paths_list",
                ),
                source="test",
            )
        },
        stage1_all_steps={},
        stage2_all_steps={"illumina": ["haplotypecaller"]},
        stage3_all_steps=[],
        stage3_no_beagle_steps=[],
        source="test",
    )

    matcher = SubmitMasterParameterMatcher(creator_catalog=catalog)

    result = matcher.match(
        provided_parameters={
            "stage": "stage2",
            "step": "haplotypecaller",
            "seq_type": "illumina",
            "cluster_name": "3",
            "namespace": "default",
            "batch_id": "batch140325",
        },
        candidate_stage="stage2",
        candidate_step="haplotypecaller",
        candidate_platform="illumina",
    )

    assert result.ready is False

    assert "paths" not in result.missing_parameters
    assert "input_paths_list" not in result.missing_parameters

    assert "reference_panel" in result.missing_parameters
    assert "regions_without_homopolymers" in result.missing_parameters


def test_matcher_asks_for_paths_when_config_creator_does_not_provide_them():
    catalog = SubmitMasterConfigCreatorCatalog(
        method_map={"haplotypecaller": "submit_haplotypecaller"},
        method_contracts={
            "submit_haplotypecaller": SubmitMethodContract(
                submit_method="submit_haplotypecaller",
                required_parameters=(
                    "paths",
                    "input_paths_list",
                    "reference_panel",
                ),
                provided_by_config_creator=(),
                source="test",
            )
        },
        stage1_all_steps={},
        stage2_all_steps={"illumina": ["haplotypecaller"]},
        stage3_all_steps=[],
        stage3_no_beagle_steps=[],
        source="test",
    )

    matcher = SubmitMasterParameterMatcher(creator_catalog=catalog)

    result = matcher.match(
        provided_parameters={
            "stage": "stage2",
            "step": "haplotypecaller",
            "seq_type": "illumina",
            "cluster_name": "3",
            "namespace": "default",
            "batch_id": "batch140325",
        },
        candidate_stage="stage2",
        candidate_step="haplotypecaller",
        candidate_platform="illumina",
    )

    assert "paths" in result.missing_parameters
    assert "input_paths_list" in result.missing_parameters
    assert "reference_panel" in result.missing_parameters
