from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BucketQuery:
    prefix: str | None = None
    extension: str | None = None
    name_suffix: str | None = None
    aggregate: str = "summary"


class BucketQueryParser:
    """Parse bucket questions into structured filters.

    LLM is optional and only extracts filters. Python still performs all
    deterministic matching and size/count calculations.
    """

    KNOWN_EXTENSIONS = [
        "fastq.gz",
        "fq.gz",
        "gvcf.gz",
        "vcf.gz",
        "bam.bai",
        "bam",
        "bai",
        "cram",
        "crai",
        "gvcf",
        "vcf",
        "fastq",
        "fq",
        "csv",
        "tsv",
        "json",
        "txt",
        "gz",
    ]

    DEFAULT_NAME_SUFFIXES = [
        "beagle.imputation.vcf.gz",
        "imputation.vcf.gz",
    ]

    def __init__(
        self,
        use_llm: bool | None = None,
        known_name_suffixes: list[str] | None = None,
    ) -> None:
        if use_llm is None:
            use_llm = os.getenv("BUCKET_AGENT_USE_LLM_PARSER", "").lower() in {
                "1",
                "true",
                "yes",
            }

        env_suffixes = [
            value.strip()
            for value in os.getenv("BUCKET_KNOWN_NAME_SUFFIXES", "").split(",")
            if value.strip()
        ]

        self.use_llm = use_llm
        self.known_name_suffixes = self._dedupe_suffixes(
            (known_name_suffixes or []) + env_suffixes + self.DEFAULT_NAME_SUFFIXES
        )

    def parse(self, message: str) -> BucketQuery:
        fallback = self._parse_deterministic(message)

        if not self.use_llm:
            return fallback

        try:
            llm_query = self._parse_with_llm(message)
        except Exception:
            return fallback

        return BucketQuery(
            prefix=fallback.prefix or llm_query.prefix,
            extension=fallback.extension or llm_query.extension,
            name_suffix=fallback.name_suffix or llm_query.name_suffix,
            aggregate=llm_query.aggregate or fallback.aggregate,
        )

    def _parse_deterministic(self, message: str) -> BucketQuery:
        name_suffix = self._extract_name_suffix(message)
        extension = None if name_suffix else self._extract_extension(message)

        return BucketQuery(
            prefix=self._extract_prefix(message),
            extension=extension,
            name_suffix=name_suffix,
            aggregate=self._extract_aggregate(message),
        )

    def _parse_with_llm(self, message: str) -> BucketQuery:
        try:
            from langchain_openai import AzureChatOpenAI
        except ImportError as error:
            raise RuntimeError("langchain_openai is not available") from error

        deployment = (
            os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        )

        if not deployment:
            raise RuntimeError("Missing Azure OpenAI chat deployment env var")

        llm = AzureChatOpenAI(
            azure_deployment=deployment,
            temperature=0,
        )

        known_suffixes = ", ".join(self.known_name_suffixes)

        prompt = f"""
Extract bucket inventory filters from the user question.

Return ONLY valid JSON with these keys:
- prefix: string or null. A bucket path/prefix mentioned by the user.
- extension: string or null. Broad file extension such as ".bam", ".vcf.gz", ".fastq.gz".
- name_suffix: string or null. Precise filename/product suffix such as "imputation.vcf.gz" or "beagle.imputation.vcf.gz".
- aggregate: one of "total_size", "count", "summary", "structure", "extension_breakdown",
            "list_files", "storage_class".

Known precise suffixes:
{known_suffixes}

Rules:
- Do not invent a path.
- Do not calculate any size.
- If a precise product suffix is mentioned, put it in name_suffix and set extension to null.
- If only a broad type is mentioned, use extension.
- If no path is mentioned, prefix must be null.
- If no file type or suffix is mentioned, extension and name_suffix must be null.

User question:
{message}
""".strip()

        response = llm.invoke(prompt)
        content = getattr(response, "content", str(response))
        data = json.loads(content)

        prefix = data.get("prefix")
        extension = data.get("extension")
        name_suffix = data.get("name_suffix")
        aggregate = data.get("aggregate") or "summary"

        prefix = prefix.strip() if isinstance(prefix, str) and prefix.strip() else None
        extension = (
            self._normalize_extension(extension)
            if isinstance(extension, str) and extension.strip()
            else None
        )
        name_suffix = (
            self._normalize_suffix(name_suffix)
            if isinstance(name_suffix, str) and name_suffix.strip()
            else None
        )

        if aggregate not in {
            "total_size",
            "count",
            "summary",
            "structure",
            "extension_breakdown",
            "list_files",
            "storage_class",
        }:
            aggregate = "summary"

        return BucketQuery(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            aggregate=aggregate,
        )

    def _extract_name_suffix(self, message: str) -> str | None:
        lowered = message.lower()

        for suffix in sorted(self.known_name_suffixes, key=len, reverse=True):
            normalized = suffix.lower().lstrip(".")
            if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", lowered):
                return self._normalize_suffix(suffix)

        # Generic precise suffix pattern: at least three filename tokens ending
        # in a known compressed/genomic extension, e.g. beagle.imputation.vcf.gz.
        generic = re.search(
            r"\b([a-z0-9_-]+(?:\.[a-z0-9_-]+){2,})\b",
            lowered,
        )
        if generic:
            candidate = generic.group(1)
            if any(
                candidate.endswith(ext)
                for ext in ["vcf.gz", "gvcf.gz", "fastq.gz", "fq.gz", "bam", "cram"]
            ):
                return self._normalize_suffix(candidate)

        return None

    def _extract_extension(self, message: str) -> str | None:
        lowered = message.lower()

        for ext in sorted(self.KNOWN_EXTENSIONS, key=len, reverse=True):
            normalized = ext.lower().lstrip(".")
            if re.search(rf"\b{re.escape(normalized)}\b", lowered):
                return self._normalize_extension(ext)

        dotted = re.search(r"\.([a-z0-9]+(?:\.[a-z0-9]+)?)\b", lowered)
        if dotted:
            return self._normalize_extension(dotted.group(0))

        return None

    def _extract_prefix(self, message: str) -> str | None:
        patterns = [
            r"\b(?:folder|prefix|directory|path)\s+[`'\"]?([^`'\"\s]+)",
            r"\b(?:in|under|inside|within|from)\s+[`'\"]?([^`'\"\s]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip().strip("`'\".,:;()[]{}?")
                if "/" in candidate or candidate.startswith("s3://"):
                    return candidate

        for token in message.split():
            token = token.strip("`'\".,:;()[]{}?")
            if "/" in token and not token.startswith("http"):
                return token

        return None

    def _extract_aggregate(self, message: str) -> str:
        lowered = message.lower()

        if any(word in lowered for word in ["structure", "layout", "organized", "prefixes"]):
            return "structure"

        if any(phrase in lowered for phrase in ["storage class", "storage tier", "which class", "which tier"]):
            return "storage_class"

        if any(phrase in lowered for phrase in ["list files", "show files", "which files", "what files", "files are there", "actual files"]):
            return "list_files"

        if any(word in lowered for word in ["breakdown", "types", "extensions"]):
            return "extension_breakdown"

        if any(word in lowered for word in ["how many", "count", "number of"]):
            return "count"

        if any(word in lowered for word in ["size", "total", "large", "big", "footprint"]):
            return "total_size"

        return "summary"

    @staticmethod
    def _normalize_extension(extension: str) -> str:
        extension = extension.lower().strip()
        if not extension:
            return ""
        if not extension.startswith("."):
            extension = f".{extension}"
        return extension

    @staticmethod
    def _normalize_suffix(suffix: str) -> str:
        return suffix.lower().strip().lstrip(".")

    @classmethod
    def _dedupe_suffixes(cls, suffixes: list[str]) -> list[str]:
        seen = set()
        result = []

        for suffix in suffixes:
            normalized = cls._normalize_suffix(suffix)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)

        return result
