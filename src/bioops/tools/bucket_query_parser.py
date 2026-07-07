from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class BucketQuery:
    aggregate: str = "summary"
    prefix: str | None = None
    extension: str | None = None
    name_suffix: str | None = None


class BucketQueryParser:
    """Deterministically convert a bucket question into filters and an action."""

    DEFAULT_EXTENSIONS = (
        ".fastq.gz",
        ".gvcf.gz",
        ".vcf.gz",
        ".fq.gz",
        ".tar.gz",
        ".csv",
        ".json",
        ".bam",
        ".bai",
        ".vcf",
        ".txt",
        ".filter",
    )

    def __init__(self, known_name_suffixes: list[str] | None = None) -> None:
        env_suffixes = [
            value.strip()
            for value in os.getenv("BUCKET_KNOWN_NAME_SUFFIXES", "").split(",")
            if value.strip()
        ]
        configured = known_name_suffixes or env_suffixes or [
            "beagle.imputation.vcf.gz",
            "imputation.vcf.gz",
        ]
        self.known_name_suffixes = sorted(
            {value.lower().lstrip(".") for value in configured},
            key=len,
            reverse=True,
        )

    def parse(self, message: str) -> BucketQuery:
        lowered = " ".join((message or "").strip().lower().split())
        return BucketQuery(
            aggregate=self._extract_aggregate(lowered),
            prefix=self._extract_prefix(message),
            extension=self._extract_extension(lowered),
            name_suffix=self._extract_name_suffix(lowered),
        )

    @staticmethod
    def _extract_aggregate(lowered: str) -> str:
        if any(phrase in lowered for phrase in ("storage class", "storage tier", "which class", "which tier")):
            return "storage_class"
        if any(phrase in lowered for phrase in ("list files", "show files", "which files", "what files", "files are there", "actual files", "list objects", "show objects")):
            return "list_files"
        if any(phrase in lowered for phrase in ("bucket structure", "folder structure", "prefix structure", "organize the bucket", "organisation", "organization")):
            return "structure"
        if any(phrase in lowered for phrase in ("extension breakdown", "file type breakdown", "types of files", "extensions")):
            return "extension_breakdown"
        if any(phrase in lowered for phrase in ("how many", "number of", "count of", "count ")):
            return "count"
        if any(phrase in lowered for phrase in ("total size", "how large", "how much space", "size of")):
            return "total_size"
        return "summary"

    def _extract_name_suffix(self, lowered: str) -> str | None:
        for suffix in self.known_name_suffixes:
            variants = {suffix, suffix.replace(".", " ")}
            if any(variant in lowered for variant in variants):
                return suffix
        return None

    def _extract_extension(self, lowered: str) -> str | None:
        if self._extract_name_suffix(lowered):
            return None

        for extension in sorted(self.DEFAULT_EXTENSIONS, key=len, reverse=True):
            variants = {extension, extension.lstrip("."), extension.lstrip(".").replace(".", " ")}
            if any(re.search(rf"(?<![a-z0-9]){re.escape(variant)}(?![a-z0-9])", lowered) for variant in variants):
                return extension
        return None

    @staticmethod
    def _extract_prefix(message: str) -> str | None:
        raw = (message or "").strip()

        s3_match = re.search(r"s3://[^\s,;]+", raw, flags=re.IGNORECASE)
        if s3_match:
            value = s3_match.group(0).rstrip(".,;:?!")
            without_scheme = value[5:]
            return without_scheme.split("/", 1)[1].rstrip("/") if "/" in without_scheme else None

        # Prefer a path following common scope words.
        scoped = re.search(
            r"\b(?:under|in|inside|within|from|prefix|folder|path)\s+['\"]?([^'\"\s,;?]+/[^'\"\s,;?]*|[^'\"\s,;?]+/)['\"]?",
            raw,
            flags=re.IGNORECASE,
        )
        if scoped:
            return scoped.group(1).strip("'\".,;:?!/")

        # Otherwise accept a path-like token, but not a lone filename extension.
        for token in re.findall(r"[^\s,;]+", raw):
            cleaned = token.strip("'\"()[]{}.,;:?!")
            if "/" in cleaned and not cleaned.startswith("http"):
                return cleaned.strip("/")
        return None
