import json

from bioops.tools.submit_master_config_builder import (
    SubmitMasterConfigBuilder,
    SubmitMasterConfigInput,
)


def test_stage2_haplotypecaller_config_is_original_compatible():
    builder = SubmitMasterConfigBuilder()

    result = builder.build(
        SubmitMasterConfigInput(
            stage="2",
            steps_order="haplotypecaller",
            seq_type="illumina",
            cluster_name="3",
            namespace="default",
            sample_ids=["sample1", "sample2"],
            batch_id="batch140325",
        )
    )

    assert result.errors == []

    config = json.loads(result.json_text)

    assert len(config) == 1
    assert config[0]["submit_method"] == "submit_haplotypecaller_gvcf2vcf_full_multiple_tubes"
    assert config[0]["k8s_cluster_name"] == "pipeline-v3-3"
    assert config[0]["namespace"] == "default"
    assert config[0]["sample_ids"] == [
        {"sample_id": "sample1"},
        {"sample_id": "sample2"},
    ]
    assert config[0]["batch_id"] == "batch140325"
    assert config[0]["delay_config"] == {
        "delay": 0,
        "step": 1,
        "chunk_size": 1,
    }
    assert config[0]["wait"] is True
    assert config[0]["only_good"] is True


def test_stage1_all_salus_expands_expected_steps():
    builder = SubmitMasterConfigBuilder()

    result = builder.build(
        SubmitMasterConfigInput(
            stage="stage1",
            steps_order="all",
            seq_type="salus",
            cluster_name="3",
            sample_ids=["tube1"],
            batch_id="batch080526",
        )
    )

    assert result.errors == []

    config = json.loads(result.json_text)
    methods = [entry["submit_method"] for entry in config]

    assert methods == [
        "submit_cutadapt_salus_multi_tube",
        "submit_fq2bam_s3_mounted_multiple_tubes_delay",
        "submit_qc_fq2bam_salus_multiple_tubes_mounted",
        "submit_batchqc",
    ]


def test_sex_bitrix_uses_mongo_cluster():
    builder = SubmitMasterConfigBuilder()

    result = builder.build(
        SubmitMasterConfigInput(
            stage="2",
            steps_order="sex_bitrix,split",
            seq_type="illumina",
            cluster_name="3",
            mongo_cluster_name="5",
            sample_ids=["sample1"],
            batch_id="batch140325",
        )
    )

    assert result.errors == []

    config = json.loads(result.json_text)

    assert config[0]["submit_method"] == "submit_gender_comparison_mongo_bitrix"
    assert config[0]["k8s_cluster_name"] == "pipeline-v3-common-2"

    assert config[1]["submit_method"] == "submit_split_bam_multiple_tubes_s3_mounted"
    assert config[1]["k8s_cluster_name"] == "pipeline-v3-3"


def test_unknown_step_returns_error():
    builder = SubmitMasterConfigBuilder()

    result = builder.build(
        SubmitMasterConfigInput(
            stage="2",
            steps_order="unknown_step",
            seq_type="illumina",
            cluster_name="3",
            sample_ids=["sample1"],
        )
    )

    assert "Unsupported submit-master step: unknown_step" in result.errors


def test_missing_cluster_returns_error():
    builder = SubmitMasterConfigBuilder()

    result = builder.build(
        SubmitMasterConfigInput(
            stage="2",
            steps_order="haplotypecaller",
            seq_type="illumina",
            cluster_name="",
            sample_ids=["sample1"],
        )
    )

    assert "cluster_name is required" in result.errors
