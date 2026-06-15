import re
from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.storage_inventory_tool import StorageInventoryTool, StorageSummary


class StorageAgent(BaseAgent):
    """Summarizes BioOps bucket/object-storage inventory."""

    name = "storage"
    description = "Answers read-only questions about bucket contents, prefixes, file counts, and storage size."

    def __init__(
        self,
        storage_tool: StorageInventoryTool | None = None,
        config_path: str = "configs/agents.yaml",
    ):
        self.config = self._load_config(config_path)
        self.storage_config = self.config.get("agents", {}).get("storage", {})
        self.storage_tool = storage_tool

    def run(self, message: str) -> str:
        request = self._parse_message(message)

        tool = self.storage_tool or StorageInventoryTool(
            bucket_name=request.get("bucket_name") or self.storage_config.get("bucket_name"),
            inventory_path=request.get("inventory_path") or self.storage_config.get("inventory_path"),
        )

        summary = tool.summarize(
            prefix=request.get("prefix") or self.storage_config.get("default_prefix"),
            extension=request.get("extension"),
        )

        return self._format_report(summary, tool)

    def _load_config(self, config_path: str) -> dict[str, Any]:
        path = Path(config_path)

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def _parse_message(self, message: str) -> dict[str, str | None]:
        values = self._parse_key_value_pairs(message)

        extension = (
            values.get("extension")
            or values.get("ext")
            or self._detect_requested_extension(message)
        )

        return {
            "bucket_name": values.get("bucket") or values.get("bucket_name"),
            "inventory_path": values.get("inventory") or values.get("inventory_path"),
            "prefix": values.get("prefix"),
            "extension": extension,
        }

    def _parse_key_value_pairs(self, message: str) -> dict[str, str]:
        pattern = r"(\w+)=([^\s]+)"
        matches = re.findall(pattern, message)

        return {key.lower(): value for key, value in matches}

    def _detect_requested_extension(self, message: str) -> str | None:
        lowered = message.lower()

        known_extensions = {
            "bam": ".bam",
            "cram": ".cram",
            "vcf": ".vcf",
            "vcf.gz": ".vcf.gz",
            "gvcf": ".g.vcf",
            "fastq": ".fastq",
            "fastq.gz": ".fastq.gz",
            "fq.gz": ".fq.gz",
            "csv": ".csv",
            "tsv": ".tsv",
        }

        for word, extension in known_extensions.items():
            if word in lowered:
                return extension

        return None

    def _format_report(
        self,
        summary: StorageSummary,
        tool: StorageInventoryTool,
    ) -> str:
        lines = [
            "Storage / Bucket Report",
            "",
            f"Status: {summary.status}",
            f"Bucket: {summary.bucket_name or 'not configured'}",
            f"Inventory path: {summary.inventory_path or 'not configured'}",
            f"Prefix filter: {summary.prefix or 'none'}",
            f"Extension filter: {summary.extension or 'none'}",
            "",
        ]

        if summary.status != "ok":
            lines.extend(
                [
                    "Storage inventory is not configured yet.",
                    "",
                    "Missing configuration:",
                ]
            )

            if summary.missing_config:
                lines.extend(f"- {item}" for item in summary.missing_config)
            else:
                lines.append("- unknown")

            lines.extend(
                [
                    "",
                    "Can answer after inventory/access is configured:",
                    "- count files by extension",
                    "- calculate total size by prefix",
                    "- list top prefixes",
                    "- summarize BAM/CRAM/VCF/FASTQ files",
                ]
            )

            return "\n".join(lines)

        lines.extend(
            [
                f"Total objects: {summary.total_objects}",
                f"Total size: {tool.format_size(summary.total_size_bytes)}",
                "",
                "File types:",
            ]
        )

        if summary.file_type_counts:
            for extension, count in summary.file_type_counts.items():
                lines.append(f"- {extension}: {count}")
        else:
            lines.append("- none")

        lines.extend(
            [
                "",
                "Top prefixes:",
            ]
        )

        if summary.top_prefixes:
            for prefix, count in summary.top_prefixes.items():
                lines.append(f"- {prefix}: {count}")
        else:
            lines.append("- none")

        if summary.missing_config:
            lines.extend(
                [
                    "",
                    "Configuration notes:",
                ]
            )
            lines.extend(f"- {item}" for item in summary.missing_config)

        return "\n".join(lines)
