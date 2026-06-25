import json

from bioops.tools.submit_master_config_builder import (
    SubmitMasterConfigBuilder,
    SubmitMasterConfigInput,
)
from bioops.tools.submit_master_config_creator import (
    SubmitMasterConfigCreatorCatalog,
    SubmitMethodContract,
)
from bioops.tools.submit_master_parameter_matcher import SubmitMasterParameterMatcher


def fake_catalog():
    return SubmitMasterConfigCreatorCatalog(
        method_map={"hla": "submit_hla"},
        method_contracts={
            "submit_hla": SubmitMethodContract(
                submit_method="submit_hla",
                required_parameters=("reference_panel", "hla_resource_uri"),
                optional_parameters=("threads",),
                source="test",
            )
        },
        stage1_all_steps={},
        stage2_all_steps={},
        stage3_all_steps=["hla"],
        stage3_no_beagle_steps=["hla"],
        source="test",
    )


def test_builder_requires_method_specific_parameters():
    builder = SubmitMasterConfigBuilder(creator_catalog=fake_catalog())

    result = builder.build(
        SubmitMasterConfigInput(
            stage="stage3",
            steps_order="hla",
            seq_type="illumina",
            cluster_name="3",
            namespace="bioops",
            batch_id="batch123",
            strict_method_contracts=True,
        )
    )

    assert "submit_hla requires method-specific parameter: reference_panel" in result.errors
    assert "submit_hla requires method-specific parameter: hla_resource_uri" in result.errors


def test_builder_accepts_method_specific_parameters_from_extra_params():
    builder = SubmitMasterConfigBuilder(creator_catalog=fake_catalog())

    result = builder.build(
        SubmitMasterConfigInput(
            stage="stage3",
            steps_order="hla",
            seq_type="illumina",
            cluster_name="3",
            namespace="bioops",
            batch_id="batch123",
            extra_params={
                "reference_panel": "grch38-hla",
                "hla_resource_uri": "s3://bucket/hla",
                "threads": 8,
            },
        )
    )

    assert result.errors == []

    config = json.loads(result.json_text)
    assert config[0]["submit_method"] == "submit_hla"
    assert config[0]["reference_panel"] == "grch38-hla"
    assert config[0]["hla_resource_uri"] == "s3://bucket/hla"
    assert config[0]["threads"] == 8


def test_matcher_reports_method_specific_missing_parameters():
    matcher = SubmitMasterParameterMatcher(creator_catalog=fake_catalog(), strict_method_contracts=True)

    match = matcher.match(
        provided_parameters={
            "stage": "stage3",
            "step": "hla",
            "seq_type": "illumina",
            "cluster_name": "3",
            "namespace": "bioops",
            "batch_id": "batch123",
        },
        candidate_stage="stage3",
        candidate_step="hla",
        candidate_platform="illumina",
    )

    assert match.ready is False
    assert "reference_panel or extra_params.reference_panel" in match.missing_parameters
    assert "hla_resource_uri or extra_params.hla_resource_uri" in match.missing_parameters


def test_matcher_accepts_method_specific_parameters_inside_extra_params():
    matcher = SubmitMasterParameterMatcher(creator_catalog=fake_catalog(), strict_method_contracts=True)

    match = matcher.match(
        provided_parameters={
            "stage": "stage3",
            "step": "hla",
            "seq_type": "illumina",
            "cluster_name": "3",
            "namespace": "bioops",
            "batch_id": "batch123",
            "extra_params": {
                "reference_panel": "grch38-hla",
                "hla_resource_uri": "s3://bucket/hla",
            },
        },
        candidate_stage="stage3",
        candidate_step="hla",
        candidate_platform="illumina",
    )

    assert match.ready is True
    assert match.missing_parameters == []
