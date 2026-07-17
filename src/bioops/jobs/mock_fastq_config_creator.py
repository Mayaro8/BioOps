from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PIPELINE_STAGES = {
    1: [
        ("validate-fastq", "Validate FASTQ structure and read pairs"),
        ("fastqc", "Calculate mock read-quality metrics"),
        ("trim-adapters", "Remove adapters and low-quality read ends"),
    ],
    2: [
        ("align-reference", "Align reads to the mock reference genome"),
        ("sort-bam", "Sort alignments by genomic coordinate"),
        ("mark-duplicates", "Mark duplicate read pairs"),
        ("base-recalibration", "Recalibrate mock base-quality scores"),
    ],
    3: [
        ("call-variants", "Call mock SNVs and indels"),
        ("filter-variants", "Apply mock variant quality filters"),
        ("annotate-report", "Annotate variants and produce a report"),
    ],
}

RAW_FASTQ = re.compile(r"^(.+)_R([12])\.(?:fastq|fq)(?:\.gz)?$", re.IGNORECASE)
TRIMMED_FASTQ = re.compile(
    r"^(.+)_R([12])\.trimmed\.(?:fastq|fq)(?:\.gz)?$", re.IGNORECASE
)
RECALIBRATED_BAM = re.compile(r"^(.+)\.recalibrated\.bam$", re.IGNORECASE)


def discover_samples(input_prefix: str, stage: str) -> tuple[str, str, list[dict]]:
    directory = Path(input_prefix)
    if not directory.is_dir():
        raise ValueError(f"input_prefix is not a readable directory: {input_prefix}")

    if stage in {"all", "1"}:
        input_type, output_type, pattern = (
            "raw_fastq_batch",
            "annotated_report" if stage == "all" else "trimmed_fastq_batch",
            RAW_FASTQ,
        )
    elif stage == "2":
        input_type, output_type, pattern = (
            "trimmed_fastq_batch", "recalibrated_bam_batch", TRIMMED_FASTQ
        )
    elif stage == "3":
        input_type, output_type, pattern = (
            "recalibrated_bam_batch", "annotated_report", RECALIBRATED_BAM
        )
    else:
        raise ValueError("stage must be all, 1, 2, or 3")

    discovered: dict[str, dict[str, str]] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        match = pattern.fullmatch(path.name)
        if not match:
            continue
        sample_id = match.group(1)
        key = f"R{match.group(2)}" if pattern is not RECALIBRATED_BAM else "bam"
        if key in discovered.setdefault(sample_id, {}):
            raise ValueError(f"duplicate {key} input for sample {sample_id}")
        discovered[sample_id][key] = path.as_posix()

    if not discovered:
        raise ValueError(f"no {input_type} files found under {input_prefix}")

    samples = []
    required = {"bam"} if stage == "3" else {"R1", "R2"}
    for sample_id, files in discovered.items():
        missing = required - set(files)
        if missing:
            raise ValueError(f"sample {sample_id} is missing {', '.join(sorted(missing))}")
        samples.append({"sample_id": sample_id, "inputs": files})
    return input_type, output_type, samples


def create_config(*, batch_id: str, input_prefix: str, stage: str = "all") -> dict:
    input_type, output_type, samples = discover_samples(input_prefix, stage)
    selected = set(PIPELINE_STAGES) if stage == "all" else {int(stage)}
    steps = [
        {"name": name, "description": description, "stage": stage_number}
        for stage_number, definitions in PIPELINE_STAGES.items()
        if stage_number in selected
        for name, description in definitions
    ]
    return {
        "schema_version": 2,
        "pipeline": "mock-fastq-to-annotated-variants",
        "batch_id": batch_id,
        "input": {"type": input_type, "prefix": input_prefix},
        "stage": stage,
        "output_root": f"mock-results/{batch_id}",
        "output_type": output_type,
        "samples": samples,
        "steps": steps,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--input-prefix", required=True)
    parser.add_argument("--stage", choices=["all", "1", "2", "3"], default="all")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    value = create_config(
        batch_id=args.batch_id, input_prefix=args.input_prefix, stage=args.stage
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
