from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.bucket_inventory import BucketInventoryTool
from bioops.tools.bucket_query_parser import BucketQueryParser


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = PROJECT_ROOT / "configs" / "agents.yaml"


class BucketAgent(BaseAgent):
    """Answer Storage/Bucket questions from an inventory/listing file."""

    name = "storage"
    description = "Answers questions about bucket structure, object counts, and storage size."

    def __init__(self, config_path: Path = AGENTS_CONFIG_PATH) -> None:
        config = self._load_config(config_path)
        storage_config = config.get("agents", {}).get("storage", {}) or {}

        self.bucket_name = (
            os.getenv("BUCKET_NAME")
            or storage_config.get("bucket_name")
            or "genotek-testing"
        )

        self.inventory_path = (
            os.getenv("BUCKET_INVENTORY_PATH")
            or storage_config.get("inventory_path")
            or str(PROJECT_ROOT / "data" / "bucket_inventory.csv")
        )

        raw_suffixes = storage_config.get("known_name_suffixes", []) or []
        if isinstance(raw_suffixes, str):
            raw_suffixes = [item.strip() for item in raw_suffixes.split(",") if item.strip()]

        self.tool = BucketInventoryTool(
            inventory_path=self.inventory_path,
            bucket_name=self.bucket_name,
            inventory_date=(
                os.getenv("BUCKET_INVENTORY_DATE")
                or storage_config.get("inventory_date")
                or ""
            ),
        )
        self.query_parser = BucketQueryParser(known_name_suffixes=raw_suffixes)

    def run(self, message: str) -> str:
        message = (message or "").strip()

        if not message:
            return self._help()

        if not self.tool.objects:
            return self._with_inventory_footer([
                "Bucket Agent",
                "",
                f"No inventory records found for bucket `{self.bucket_name}`.",
                f"Expected inventory file: {self.inventory_path}",
                "",
                "Create or mount an inventory/listing file first.",
                "Supported formats:",
                "- CSV with at least key,size",
                "- plain inventory/listing lines such as: size path",
            ])

        query = self.query_parser.parse(message)

        if query.aggregate == "storage_class":
            return self._format_storage_classes(
                prefix=query.prefix,
                extension=query.extension,
                name_suffix=query.name_suffix,
            )

        if query.aggregate == "storage_class":
            return self._format_storage_classes(
                prefix=query.prefix,
                extension=query.extension,
                name_suffix=query.name_suffix,
            )

        if query.aggregate == "storage_class":
            return self._format_storage_classes(
                prefix=query.prefix,
                extension=query.extension,
                name_suffix=query.name_suffix,
            )

        if query.aggregate == "list_files":
            return self._format_file_list(
                prefix=query.prefix,
                extension=query.extension,
                name_suffix=query.name_suffix,
            )

        if query.prefix and (query.extension or query.name_suffix):
            return self._format_filtered(
                prefix=query.prefix,
                extension=query.extension,
                name_suffix=query.name_suffix,
            )

        if query.aggregate == "structure":
            return self._format_structure()

        if query.prefix:
            return self._format_prefix(query.prefix)

        if query.name_suffix:
            return self._format_filtered(
                prefix=None,
                extension=None,
                name_suffix=query.name_suffix,
            )

        if query.extension:
            return self._format_extension(query.extension)

        if query.aggregate == "extension_breakdown":
            return self._format_extension_breakdown()

        return self._format_overview()

    def process(self, message: str) -> str:
        return self.run(message)

    def handle(self, message: str) -> str:
        return self.run(message)

    def _format_overview(self) -> str:
        stats = self.tool.overview()
        return self._with_inventory_footer([
            f"Bucket Overview: {self.bucket_name}",
            "",
            f"Objects: {stats['objects']}",
            f"Total size: {self.tool.format_bytes(int(stats['bytes']))}",
            f"Inventory file: {self.inventory_path}",
        ])

    def _format_structure(self) -> str:
        rows = self.tool.top_prefixes(depth=1, limit=10)

        lines = [
            f"Bucket Structure: {self.bucket_name}",
            "",
            "Top prefixes by size:",
        ]

        for row in rows:
            lines.append(
                f"- {row['prefix']}: {row['objects']} objects, "
                f"{self.tool.format_bytes(int(row['bytes']))}"
            )

        return self._with_inventory_footer(lines)

    def _format_extension(self, extension: str) -> str:
        stats = self.tool.extension_stats(extension)

        return self._with_inventory_footer([
            f"Bucket File Type Summary: {stats['extension']}",
            "",
            f"Bucket: {self.bucket_name}",
            f"Path scope: {stats['prefix']}",
            f"Objects: {stats['objects']}",
            f"Total size: {self.tool.format_bytes(int(stats['bytes']))}",
        ])

    def _format_prefix(self, prefix: str) -> str:
        stats = self.tool.prefix_stats(prefix)

        return self._with_inventory_footer([
            f"Bucket Prefix Summary: {stats['prefix']}",
            "",
            f"Bucket: {self.bucket_name}",
            f"File type: {stats['extension']}",
            f"Objects: {stats['objects']}",
            f"Total size: {self.tool.format_bytes(int(stats['bytes']))}",
        ])

    def _format_filtered(
        self,
        prefix: str | None,
        extension: str | None,
        name_suffix: str | None = None,
    ) -> str:
        stats = self.tool.filtered_stats(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            known_name_suffixes=self.query_parser.known_name_suffixes,
        )

        lines = [
            "Bucket Filtered Summary",
            "",
            f"Bucket: {self.bucket_name}",
            f"Path scope: {stats['prefix']}",
        ]

        if stats.get("name_suffix"):
            lines.append(f"Filename suffix: {stats['name_suffix']}")
        else:
            lines.append(f"File type: {stats['extension']}")

        lines.extend([
            f"Objects: {stats['objects']}",
            f"Total size: {self.tool.format_bytes(int(stats['bytes']))}",
        ])

        return self._with_inventory_footer(lines)

    def _format_storage_classes(
        self,
        prefix: str | None = None,
        extension: str | None = None,
        name_suffix: str | None = None,
    ) -> str:
        stats = self.tool.filtered_stats(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            known_name_suffixes=self.query_parser.known_name_suffixes,
        )

        lines = [
            "Bucket Storage Class Summary",
            "",
            f"Bucket: {self.bucket_name}",
            f"Path scope: {stats['prefix']}",
        ]

        if stats.get("name_suffix"):
            lines.append(f"Filename suffix: {stats['name_suffix']}")
        else:
            lines.append(f"File type: {stats['extension']}")

        lines.extend([
            f"Objects: {stats['objects']}",
            f"Total size: {self.tool.format_bytes(int(stats['bytes']))}",
            "",
            "Storage classes:",
        ])

        for row in stats.get("storage_classes", []):
            lines.append(
                f"- {row['storage_class']}: {row['objects']} objects, "
                f"{self.tool.format_bytes(int(row['bytes']))}"
            )

        return self._with_inventory_footer(lines)


    def _format_file_list(
        self,
        prefix: str | None = None,
        extension: str | None = None,
        name_suffix: str | None = None,
        limit: int = 50,
    ) -> str:
        objects = self.tool.filter_objects(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            known_name_suffixes=self.query_parser.known_name_suffixes,
        )

        stats = self.tool.filtered_stats(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            known_name_suffixes=self.query_parser.known_name_suffixes,
        )

        lines = [
            "Bucket File List",
            "",
            f"Bucket: {self.bucket_name}",
            f"Path scope: {stats['prefix']}",
        ]

        if stats.get("name_suffix"):
            lines.append(f"Filename suffix: {stats['name_suffix']}")
        else:
            lines.append(f"File type: {stats['extension']}")

        lines.extend([
            f"Matched objects: {len(objects)}",
            f"Total matched size: {self.tool.format_bytes(int(stats['bytes']))}",
            "",
            "Files:",
        ])

        for obj in objects[:limit]:
            storage_class = obj.storage_class or "UNKNOWN"
            lines.append(
                f"- {obj.key} | {self.tool.format_bytes(obj.size)} | {storage_class}"
            )

        if len(objects) > limit:
            lines.append(f"... {len(objects) - limit} more files not shown")

        return self._with_inventory_footer(lines)


    def _format_extension_breakdown(self) -> str:
        rows = self.tool.extension_breakdown(limit=15)

        lines = [
            f"Bucket Extension Breakdown: {self.bucket_name}",
            "",
        ]

        for row in rows:
            lines.append(
                f"- {row['extension']}: {row['objects']} objects, "
                f"{self.tool.format_bytes(int(row['bytes']))}"
            )

        return self._with_inventory_footer(lines)

    def _help(self) -> str:
        return self._with_inventory_footer([
            "Bucket Agent",
            "",
            "I answer read-only questions from a bucket inventory/listing file.",
            "",
            "Try:",
            "- explain the genotek-testing bucket structure",
            "- total size of .bam files",
            "- size of all bam files in raw/batch-1",
            "- how many BAM files are under results/batch-001/",
            "- size of folder raw/",
            "- show object type breakdown",
            "",
            f"Bucket: {self.bucket_name}",
            f"Inventory file: {self.inventory_path}",
        ])

    def _with_inventory_footer(self, lines: list[str]) -> str:
        lines.extend([
            "",
            f"Inventory date: {self.tool.inventory_date()}",
        ])
        return "\n".join(lines).strip()

    def _load_config(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
