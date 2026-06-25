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
                required_parameters=(
                    "paths",
                    "input_paths_list",
                    "reference_panel",
                    "hla_resource_uri",
                ),
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


def test_matcher_requests_all_common_and_method_specific_parameters():
    matcher = SubmitMasterParameterMatcher(creator_catalog=fake_catalog())

    result = matcher.match(
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

    assert result.ready is False
    assert result.submit_method == "submit_hla"

    assert "paths" in result.missing_parameters
    assert "input_paths_list" in result.missing_parameters
    assert "reference_panel" in result.missing_parameters
    assert "hla_resource_uri" in result.missing_parameters

    assert "paths or extra_params.paths" in result.required_parameters
    assert "input_paths_list or extra_params.input_paths_list" in result.required_parameters
    assert "reference_panel or extra_params.reference_panel" in result.required_parameters
    assert "hla_resource_uri or extra_params.hla_resource_uri" in result.required_parameters


def test_matcher_accepts_all_parameters_when_provided():
    matcher = SubmitMasterParameterMatcher(creator_catalog=fake_catalog())

    result = matcher.match(
        provided_parameters={
            "stage": "stage3",
            "step": "hla",
            "seq_type": "illumina",
            "cluster_name": "3",
            "namespace": "bioops",
            "batch_id": "batch123",
            "paths": {
                "input_dir_s3": "s3://input",
                "output_dir_s3": "s3://output",
            },
            "input_paths_list": [
                "s3://input/sample1",
                "s3://input/sample2",
            ],
            "reference_panel": "grch38-hla",
            "hla_resource_uri": "s3://resources/hla",
        },
        candidate_stage="stage3",
        candidate_step="hla",
        candidate_platform="illumina",
    )

    assert result.ready is True
    assert result.missing_parameters == []


def test_builder_writes_paths_and_input_paths_list():
    builder = SubmitMasterConfigBuilder(creator_catalog=fake_catalog())

    result = builder.build(
        SubmitMasterConfigInput(
            stage="stage3",
            steps_order="hla",
            seq_type="illumina",
            cluster_name="3",
            namespace="bioops",
            batch_id="batch123",
            paths={
                "input_dir_s3": "s3://input",
                "output_dir_s3": "s3://output",
            },
            input_paths_list=[
                "s3://input/sample1",
                "s3://input/sample2",
            ],
            extra_params={
                "reference_panel": "grch38-hla",
                "hla_resource_uri": "s3://resources/hla",
            },
            strict_method_contracts=True,
        )
    )

    assert result.errors == []

    config = json.loads(result.json_text)
    assert config[0]["paths"] == {
        "input_dir_s3": "s3://input",
        "output_dir_s3": "s3://output",
    }
    assert config[0]["input_paths_list"] == [
        "s3://input/sample1",
        "s3://input/sample2",
    ]
    assert config[0]["reference_panel"] == "grch38-hla"
    assert config[0]["hla_resource_uri"] == "s3://resources/hla"
