from __future__ import annotations

STAGE1_ALL_STEPS: dict[str, list[str]] = {
    "illumina": ["cutadapt_illumina", "fq2bam_illumina", "bamqc", "batchqc"],
    "mgi": ["cutadapt_mgi", "fq2bam_mgi", "bamqc", "batchqc"],
    "surf": ["cutadapt_surf", "fq2bam_illumina", "bamqc", "batchqc"],
    "salus": ["cutadapt_salus", "fq2bam_illumina", "bamqc_salus", "batchqc"],
}

STAGE2_ALL_STEPS: dict[str, list[str]] = {
    "illumina": ["sex_bitrix", "split", "imputation", "haplotypecaller", "transfer_vcf", "post_imp"],
    "mgi": ["sex_bitrix", "split", "imputation", "haplotypecaller", "transfer_vcf", "post_imp"],
    "surf": ["sex_bitrix", "split", "imputation", "haplotypecaller", "transfer_vcf", "post_imp"],
    "salus": ["sex_bitrix", "split_salus", "imputation", "haplotypecaller", "transfer_vcf", "post_imp"],
}

STAGE3_ALL_STEPS: list[str] = [
    "beagle",
    "inher",
    "hla",
    "hla_parser",
    "lk",
    "apoe",
    "transfer_bam",
    "y",
    "deep_mito",
    "anal",
    "batch_report",
    "b2c",
    "final_checker",
]

STAGE3_NO_BEAGLE_STEPS: list[str] = [
    "inher",
    "hla",
    "hla_parser",
    "lk",
    "apoe",
    "transfer_bam",
    "y",
    "deep_mito",
    "anal",
    "batch_report",
    "b2c",
    "final_checker",
]
