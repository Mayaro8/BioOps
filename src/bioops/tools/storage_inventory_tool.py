import csv
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StorageObject:
    key: str
    size_bytes: int


@dataclass
class StorageSummary:
    status: str
    bucket_name: str | None
    inventory_path: str | None
    prefix: str | None
    extension: str | None
    total_objects: int
    total_size_bytes: int
    file_type_counts: dict[str, int]
    top_prefixes: dict[str, int]
    missing_config: list[str]


class StorageInventoryTool:
    """
    Read-only storage inventory tool.

    MVP behavior:
    - reads a local CSV inventory if configured
    - summarizes object count, total size, extensions, and prefixes
    - does not scan live buckets yet
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        inventory_path: str | None = None,
    ):
        self.bucket_name = bucket_name or os.getenv("BIOOPS_STORAGE_BUCKET")
        self.inventory_path = inventory_path or os.getenv("BIOOPS_STORAGE_INVENTORY_PATH")

    def summarize(
        self,
        prefix: str | None = None,
        extension: str | None = None,
    ) -> StorageSummary:
        missing_config = self._missing_config()

        if not self.inventory_path:
            return StorageSummary(
                status="not configured",
                bucket_name=self.bucket_name,
                inventory_path=self.inventory_path,
                prefix=prefix,
                extension=extension,
                total_objects=0,
                total_size_bytes=0,
                file_type_counts={},
                top_prefixes={},
                missing_config=missing_config,
            )

        inventory_file = Path(self.inventory_path)

        if not inventory_file.exists():
            return StorageSummary(
                status="not configured",
                bucket_name=self.bucket_name,
                inventory_path=self.inventory_path,
                prefix=prefix,
                extension=extension,
                total_objects=0,
                total_size_bytes=0,
                file_type_counts={},
                top_prefixes={},
                missing_config=[*missing_config, f"inventory file not found: {inventory_file}"],
            )

        objects = self._load_inventory(inventory_file)
        filtered_objects = self._filter_objects(objects, prefix=prefix, extension=extension)

        return StorageSummary(
            status="ok",
            bucket_name=self.bucket_name,
            inventory_path=str(inventory_file),
            prefix=prefix,
            extension=extension,
            total_objects=len(filtered_objects),
            total_size_bytes=sum(obj.size_bytes for obj in filtered_objects),
            file_type_counts=self._count_file_types(filtered_objects),
            top_prefixes=self._count_top_prefixes(filtered_objects, prefix=prefix),
            missing_config=missing_config,
        )

    def _missing_config(self) -> list[str]:
        missing: list[str] = []

        if not self.bucket_name:
            missing.append("bucket_name or BIOOPS_STORAGE_BUCKET")

        if not self.inventory_path:
            missing.append("inventory_path or BIOOPS_STORAGE_INVENTORY_PATH")

        return missing

    def _load_inventory(self, inventory_file: Path) -> list[StorageObject]:
        objects: list[StorageObject] = []

        with inventory_file.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)

            for row in reader:
                normalized = {
                    (key or "").strip().lower(): (value or "").strip()
                    for key, value in row.items()
                }

                key = (
                    normalized.get("key")
                    or normalized.get("object_key")
                    or normalized.get("object key")
                )

                size_raw = (
                    normalized.get("size")
                    or normalized.get("size_bytes")
                    or normalized.get("object_size")
                    or "0"
                )

                if not key:
                    continue

                try:
                    size_bytes = int(float(size_raw))
                except ValueError:
                    size_bytes = 0

                objects.append(StorageObject(key=key, size_bytes=size_bytes))

        return objects

    def _filter_objects(
        self,
        objects: list[StorageObject],
        prefix: str | None,
        extension: str | None,
    ) -> list[StorageObject]:
        filtered = objects

        if prefix:
            filtered = [obj for obj in filtered if obj.key.startswith(prefix)]

        if extension:
            normalized_extension = self._normalize_extension(extension)
            filtered = [
                obj for obj in filtered
                if self._detect_extension(obj.key) == normalized_extension
            ]

        return filtered

    def _count_file_types(self, objects: list[StorageObject]) -> dict[str, int]:
        counts = Counter(self._detect_extension(obj.key) for obj in objects)
        return dict(counts.most_common())

    def _count_top_prefixes(
        self,
        objects: list[StorageObject],
        prefix: str | None,
    ) -> dict[str, int]:
        counts: Counter[str] = Counter()

        for obj in objects:
            key = obj.key

            if prefix and key.startswith(prefix):
                key = key[len(prefix):].lstrip("/")

            top_prefix = key.split("/", 1)[0] if "/" in key else "(root)"
            counts[top_prefix] += 1

        return dict(counts.most_common(10))

    def _detect_extension(self, key: str) -> str:
        lowered = key.lower()

        compressed_extensions = [
            ".fastq.gz",
            ".fq.gz",
            ".vcf.gz",
            ".tsv.gz",
            ".csv.gz",
        ]

        for extension in compressed_extensions:
            if lowered.endswith(extension):
                return extension

        suffix = Path(lowered).suffix
        return suffix if suffix else "(no extension)"

    def _normalize_extension(self, extension: str) -> str:
        extension = extension.lower().strip()

        if not extension.startswith("."):
            extension = f".{extension}"

        return extension

    def format_size(self, size_bytes: int) -> str:
        value = float(size_bytes)
        units = ["B", "KB", "MB", "GB", "TB", "PB"]

        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.2f} {unit}"
            value /= 1024

        return f"{size_bytes} B"
