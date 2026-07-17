from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from bioops.tools.bucket_inventory import BucketInventoryTool, BucketObject
from bioops.tools.llm_action_router import (
    LLMActionRouter,
    format_action_routing_error,
)


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
        action_router: LLMActionRouter | None = None,
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
        self.known_name_suffixes = self._known_suffixes(config)
        self.tool = inventory_tool or BucketInventoryTool(
            inventory_path=inventory_path,
            bucket_name=self.bucket_name,
            inventory_date=inventory_date,
        )
        self.max_listed_files = int(
            os.getenv(
                "BUCKET_MAX_LISTED_FILES",
                str(config.get("max_listed_files", 50)),
            )
        )
        self.action_router = action_router or self._build_action_router()

    def run(self, message: str, **_: Any) -> str:
        try:
            decision = self.action_router.route(message)
        except Exception as error:
            return format_action_routing_error("Bucket Agent", error)

        try:
            parameters = decision.parameters
            prefix = self._optional_text(parameters.get("prefix"))
            extension = self._optional_text(parameters.get("extension"))
            name_suffix = self._optional_text(parameters.get("name_suffix"))
            storage_class = self._optional_text(parameters.get("storage_class"))
            limit = self._bounded_limit(
                parameters.get("limit"),
                default=self.max_listed_files,
                maximum=self.max_listed_files,
            )

            if decision.action == "storage_class":
                return self._format_storage_classes(
                    prefix, extension, name_suffix, storage_class
                )
            if decision.action == "list_files":
                return self._format_file_list(
                    prefix,
                    extension,
                    name_suffix,
                    storage_class,
                    limit,
                )
            if decision.action == "structure":
                return self._format_structure()
            if decision.action == "extension_breakdown":
                return self._format_extension_breakdown()
            if decision.action == "help":
                return self._help()

            stats = self._filtered_stats(
                prefix=prefix,
                extension=extension,
                name_suffix=name_suffix,
                storage_class=storage_class,
            )
            return self._format_stats(stats, decision.action)
        except FileNotFoundError as error:
            return (
                "Bucket inventory is unavailable.\n\n"
                f"Reason: {error}\n"
                "Run the inventory exporter or configure BUCKET_INVENTORY_PATH."
            )
        except Exception as error:
            return f"Bucket Agent could not answer the question: {error}"

    def _filtered_objects(
        self,
        *,
        prefix: str | None,
        extension: str | None,
        name_suffix: str | None,
        storage_class: str | None,
    ) -> list[BucketObject]:
        rows = self.tool.filter_objects(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            known_name_suffixes=self.known_name_suffixes,
        )
        if storage_class:
            expected = storage_class.casefold()
            rows = [
                obj
                for obj in rows
                if (obj.storage_class or "UNKNOWN").strip().casefold() == expected
            ]
        return rows

    def _filtered_stats(
        self,
        *,
        prefix: str | None,
        extension: str | None,
        name_suffix: str | None,
        storage_class: str | None,
    ) -> dict[str, object]:
        rows = self._filtered_objects(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            storage_class=storage_class,
        )
        by_class: dict[str, dict[str, object]] = {}
        for obj in rows:
            class_name = (obj.storage_class or "UNKNOWN").strip() or "UNKNOWN"
            entry = by_class.setdefault(
                class_name,
                {"storage_class": class_name, "objects": 0, "bytes": 0},
            )
            entry["objects"] = int(entry["objects"]) + 1
            entry["bytes"] = int(entry["bytes"]) + obj.size
        normalized_prefix = self.tool.normalize_key(prefix or "").rstrip("/")
        return {
            "prefix": f"{normalized_prefix}/" if normalized_prefix else "(bucket root)",
            "extension": extension or "(all files)",
            "name_suffix": name_suffix or "",
            "storage_class_filter": storage_class or "",
            "objects": len(rows),
            "bytes": sum(obj.size for obj in rows),
            "storage_classes": sorted(
                by_class.values(),
                key=lambda row: (-int(row["bytes"]), str(row["storage_class"])),
            ),
        }

    def _format_stats(self, stats: dict[str, object], action: str) -> str:
        title = {
            "count": "Bucket Object Count",
            "total_size": "Bucket Size Summary",
            "summary": "Bucket Inventory Summary",
        }.get(action, "Bucket Inventory Summary")
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
        if stats.get("storage_class_filter"):
            lines.append(f"Storage class filter: {stats['storage_class_filter']}")
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
        storage_class: str | None,
    ) -> str:
        stats = self._filtered_stats(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            storage_class=storage_class,
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
        storage_class: str | None,
        limit: int,
    ) -> str:
        objects = self._filtered_objects(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            storage_class=storage_class,
        )
        stats = self._filtered_stats(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            storage_class=storage_class,
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
            for obj in objects[:limit]:
                lines.append(
                    f"- {obj.key} | {self.tool.format_bytes(obj.size)} | "
                    f"{obj.storage_class or 'UNKNOWN'}"
                )
            if len(objects) > limit:
                lines.append(f"... {len(objects) - limit} more objects not shown")
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

    def _build_action_router(self) -> LLMActionRouter:
        suffixes = ", ".join(self.known_name_suffixes) or "none configured"
        return LLMActionRouter(
            agent_name="Bucket Agent",
            actions={
                "summary": "Show object count and total size for a scope.",
                "count": "Show the number of matching objects.",
                "total_size": "Show the total size of matching objects.",
                "storage_class": "Show storage-class totals for matching objects.",
                "list_files": "List matching object keys and sizes.",
                "structure": "Show top-level bucket prefixes.",
                "extension_breakdown": "Show counts and sizes grouped by file type.",
                "help": "Explain supported Bucket Agent questions.",
            },
            parameter_schema={
                "prefix": (
                    f"Optional exact object-key prefix inside {self.bucket_name}; "
                    "remove s3://bucket/ when present."
                ),
                "extension": "Optional generic file type, preserving compounds such as vcf.gz or fastq.gz.",
                "name_suffix": f"Optional exact product suffix. Configured suffixes: {suffixes}.",
                "storage_class": "Optional storage class such as STANDARD, COLD, or TICE.",
                "limit": "Optional integer maximum number of files to display.",
            },
            rules=[
                "Choose count for how many/number of objects.",
                "Choose total_size for total size, disk usage, or how large a scope is.",
                "Choose list_files only when object keys/files should be displayed.",
                "Choose summary when both count and total size are requested.",
                "Choose structure for folders, directories, or top-level prefixes.",
                "Choose extension_breakdown for grouping or breakdown by file type.",
                "Choose storage_class for a breakdown by storage class; when listing files in one named class, choose list_files and set storage_class.",
                "Use name_suffix for product suffixes such as beagle.imputation.vcf.gz.",
                "Use extension for generic file types such as vcf.gz.",
                "Never put a generic compound extension in name_suffix.",
                "Preserve the complete requested prefix, including batch/sample directories.",
                "Do not calculate counts or sizes; select filters and let the inventory tool calculate.",
                "Do not invent a prefix or suffix that is absent from the request.",
                "All operations are read-only against the local inventory snapshot.",
            ],
            examples=[
                {
                    "request": "List imputation.vcf.gz files under results/batch-1/",
                    "action": "list_files",
                    "parameters": {
                        "prefix": "results/batch-1/",
                        "extension": None,
                        "name_suffix": "imputation.vcf.gz",
                        "storage_class": None,
                        "limit": None,
                    },
                    "reason": "A specific configured product suffix was requested.",
                },
                {
                    "request": "Which storage classes are under data/c2023/?",
                    "action": "storage_class",
                    "parameters": {
                        "prefix": "data/c2023/",
                        "extension": None,
                        "name_suffix": None,
                        "storage_class": None,
                        "limit": None,
                    },
                    "reason": "The user requests a storage-class breakdown.",
                },
                {
                    "request": "How many .bam files are under batches/batch140325/?",
                    "action": "count",
                    "parameters": {
                        "prefix": "batches/batch140325/",
                        "extension": "bam",
                        "name_suffix": None,
                        "storage_class": None,
                        "limit": None,
                    },
                    "reason": "The user requests a count for a generic extension and prefix.",
                },
                {
                    "request": "What is the total size of vcf.gz objects in s3://genotek-testing/results/batch-1/?",
                    "action": "total_size",
                    "parameters": {
                        "prefix": "results/batch-1/",
                        "extension": "vcf.gz",
                        "name_suffix": None,
                        "storage_class": None,
                        "limit": None,
                    },
                    "reason": "The inventory tool must total a generic compound extension.",
                },
                {
                    "request": "List up to 10 BAM files in COLD storage under data/",
                    "action": "list_files",
                    "parameters": {
                        "prefix": "data/",
                        "extension": "bam",
                        "name_suffix": None,
                        "storage_class": "COLD",
                        "limit": 10,
                    },
                    "reason": "The user wants keys filtered by type, class, prefix, and limit.",
                },
            ],
        )

    def _help(self) -> str:
        return (
            "Bucket Agent\n\n"
            "Supported read-only inventory requests:\n"
            "- bucket summary, object count, or total size\n"
            "- storage-class breakdown\n"
            "- list files by prefix, extension, filename suffix, or storage class\n"
            "- top-level bucket structure\n"
            "- file-type breakdown"
        )

    @staticmethod
    def _known_suffixes(config: dict[str, object]) -> list[str]:
        values = config.get("known_name_suffixes") or [
            "beagle.imputation.vcf.gz",
            "imputation.vcf.gz",
        ]
        if isinstance(values, str):
            values = [value.strip() for value in values.split(",") if value.strip()]
        return [str(value).strip() for value in values if str(value).strip()]

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    @staticmethod
    def _bounded_limit(value: Any, *, default: int, maximum: int) -> int:
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(1, min(parsed, maximum))

    @staticmethod
    def _load_storage_config(path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}

        agents = data.get("agents", {})
        if isinstance(agents, dict):
            nested = agents.get("storage", {})
            if isinstance(nested, dict):
                return nested

        legacy = data.get("storage", {})
        return legacy if isinstance(legacy, dict) else {}
