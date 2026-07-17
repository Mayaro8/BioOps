from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-prefix", required=True)
    args = parser.parse_args()
    directory = Path(args.input_prefix)
    directory.mkdir(parents=True, exist_ok=True)

    # Mixed-stage files prove Config Creator selects only the requested inputs.
    names = []
    for sample in ("sample1", "sample2", "sample3"):
        names.extend([
            f"{sample}_R1.fastq.gz",
            f"{sample}_R2.fastq.gz",
            f"{sample}_R1.trimmed.fastq.gz",
            f"{sample}_R2.trimmed.fastq.gz",
            f"{sample}.recalibrated.bam",
            f"{sample}.unrelated.txt",
        ])
    for name in names:
        (directory / name).write_text(f"mock data for {name}\n", encoding="utf-8")
    print(f"Seeded {len(names)} mixed mock files under {directory}")


if __name__ == "__main__":
    main()
