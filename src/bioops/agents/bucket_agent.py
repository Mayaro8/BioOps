from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from bioops.tools.bucket_inventory import BucketInventoryTool
from bioops.tools.bucket_query_parser import BucketQueryParser


class BucketAgent:
    """Answer read-only questions using a bucket inventory CSV snapshot."""

    name = "storage"
    description = (
        "Answers questions about bucket structure, object counts, total size, "
        "storage classes, matching files, and inventory freshness."
    )

    def __init__(
        self,
        config_path: str | Path = "configs/agents.yaml",
        inventory_tool: BucketInventoryTool | None = None,
        query_parser: BucketQueryParser | None = None,
    ) -> None:
        config = self._load_storage_config(Path(config_path))

        self.bucket_name = os.getenv(
            "BUCKET_NAME",
            str(config.get("bucket_name", "genotek-testing")),
        )
        inventory_path = os.getenv(
            "BUCKET_INVENTORY_PATH",
            str(config.get("inventory_path", "data/bucket_inventory.csv")),
        )
        inventory_date = os.getenv(
            "BUCKET_INVENTORY_DATE",
            str(config.get("inventory_date", "")),
        )

        known_suffixes = config.get("known_name_suffixes") or [
            "beagle.imputation.vcf.gz",
            "imputation.vcf.gz",
        ]
        if isinstance(known_suffixes, str):
            known_suffixes = [value.strip() for value in known_suffixes.split(",") if value.strip()]

        self.query_parser = query_parser or BucketQueryParser(list(known_suffixes))
        self.tool = inventory_tool or BucketInventoryTool(
            inventory_path=inventory_path,
            bucket_name=self.bucket_name,
            inventory_date=inventory_date,
        )
        self.max_listed_files = int(
            os.getenv("BUCKET_MAX_LISTED_FILES", str(config.get("max_listed_files", 50)))
        )

    def run(self, message: str, **_: Any) -> str:
        try:
            query = self.query_parser.parse(message)

            if query.aggregate == "storage_class":
                return self._format_storage_classes(query.prefix, query.extension, query.name_suffix)
            if query.aggregate == "list_files":
                return self._format_file_list(query.prefix, query.extension, query.name_suffix)
            if query.aggregate == "structure":
                return self._format_structure()
            if query.aggregate == "extension_breakdown":
                return self._format_extension_breakdown()

            stats = self.tool.filtered_stats(
                prefix=query.prefix,
                extension=query.extension,
                name_suffix=query.name_suffix,
                known_name_suffixes=self.query_parser.known_name_suffixes,
            )
            return self._format_stats(stats, query.aggregate)
        except FileNotFoundError as exc:
            return (
                "Bucket inventory is unavailable.\n\n"
                f"Reason: {exc}\n"
                "Run the inventory exporter or configure BUCKET_INVENTORY_PATH."
            )
        except Exception as exc:  # Defensive user-facing boundary.
            return f"Bucket Agent could not answer the question: {exc}"

    def _format_stats(self, stats: dict[str, object], aggregate: str) -> str:
        if aggregate == "count":
            title = "Bucket Object Count"
        elif aggregate == "total_size":
            title = "Bucket Size Summary"
        else:
            title = "Bucket Inventory Summary"

        lines = [
            title,
            "",
            f"Bucket: {self.bucket_name}",
            f"Path scope: {stats['prefix']}",
        ]
        if stats.get("name_suffix"):
            lines.append(f"Filename suffix: {stats['name_suffix']}")
        else:
            lines.append(f"File type: {stats['extension']}")
        lines.extend(
            [
                f"Objects: {stats['objects']}",
                f"Total size: {self.tool.format_bytes(int(stats['bytes']))}",
            ]
        )
        return self._with_inventory_footer(lines)

    def _format_storage_classes(
        self,
        prefix: str | None,
        extension: str | None,
        name_suffix: str | None,
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
            f"Objects: {stats['objects']}",
            f"Total size: {self.tool.format_bytes(int(stats['bytes']))}",
            "",
            "Storage classes:",
        ]
        storage_classes = list(stats.get("storage_classes", []))
        if not storage_classes:
            lines.append("- No matching objects")
        else:
            for row in storage_classes:
                lines.append(
                    f"- {row['storage_class']}: {row['objects']} objects, "
                    f"{self.tool.format_bytes(int(row['bytes']))}"
                )
        return self._with_inventory_footer(lines)

    def _format_file_list(
        self,
        prefix: str | None,
        extension: str | None,
        name_suffix: str | None,
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
            f"Matched objects: {len(objects)}",
            f"Total matched size: {self.tool.format_bytes(int(stats['bytes']))}",
            "",
            "Files:",
        ]
        if not objects:
            lines.append("- No matching objects")
        else:
            for obj in objects[: self.max_listed_files]:
                lines.append(
                    f"- {obj.key} | {self.tool.format_bytes(obj.size)} | "
                    f"{obj.storage_class or 'UNKNOWN'}"
                )
            if len(objects) > self.max_listed_files:
                lines.append(f"... {len(objects) - self.max_listed_files} more objects not shown")
        return self._with_inventory_footer(lines)

    def _format_structure(self) -> str:
        rows = self.tool.top_prefixes(depth=1, limit=20)
        lines = [
            "Bucket Structure",
            "",
            f"Bucket: {self.bucket_name}",
            "Top-level prefixes:",
        ]
        if not rows:
            lines.append("- No objects")
        else:
            for row in rows:
                lines.append(
                    f"- {row['prefix']}: {row['objects']} objects, "
                    f"{self.tool.format_bytes(int(row['bytes']))}"
                )
        return self._with_inventory_footer(lines)

    def _format_extension_breakdown(self) -> str:
        rows = self.tool.extension_breakdown(limit=20)
        lines = [
            "Bucket File-Type Breakdown",
            "",
            f"Bucket: {self.bucket_name}",
            "File types:",
        ]
        if not rows:
            lines.append("- No objects")
        else:
            for row in rows:
                lines.append(
                    f"- {row['extension']}: {row['objects']} objects, "
                    f"{self.tool.format_bytes(int(row['bytes']))}"
                )
        return self._with_inventory_footer(lines)

    def _with_inventory_footer(self, lines: list[str]) -> str:
        lines.extend(
            [
                "",
                f"Inventory date: {self.tool.inventory_date()}",
                f"Inventory file: {self.tool.inventory_file}",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _load_storage_config(path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}
        storage = data.get("storage", {})
        return storage if isinstance(storage, dict) else {}
