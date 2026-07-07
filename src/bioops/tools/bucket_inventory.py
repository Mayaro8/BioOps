from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote_plus


@dataclass(frozen=True)
class BucketObject:
    key: str
    size: int
    last_modified: str = ""
    storage_class: str = ""
    inventory_date: str = ""


class BucketInventoryTool:
    """Read-only helper for answering bucket questions from an inventory/listing file.

    Supported formats:
    - Header CSV: key,size,last_modified,storage_class,inventory_date
    - Headerless S3 inventory CSV: bucket,key,size,storage_class
    - Plain listing: key
    - Plain listing with size: size key
    """

    def __init__(
        self,
        inventory_path: str | Path,
        bucket_name: str = "genotek-testing",
        inventory_date: str | None = None,
    ) -> None:
        self.inventory_path = Path(inventory_path)
        self.bucket_name = bucket_name
        self.configured_inventory_date = inventory_date or ""
        self.resolved_inventory_path: Path | None = None
        self._objects: list[BucketObject] | None = None

    @property
    def objects(self) -> list[BucketObject]:
        if self._objects is None:
            self._objects = self._load_objects()
        return self._objects

    def inventory_date(self) -> str:
        if self.configured_inventory_date:
            return self.configured_inventory_date

        dates = sorted({obj.inventory_date for obj in self.objects if obj.inventory_date})
        if dates:
            return dates[-1]

        path = self.resolved_inventory_path or self._resolve_inventory_path()
        if path and path.exists():
            path_date = self._extract_date_from_path(path)
            if path_date:
                return path_date

            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            return mtime.date().isoformat()

        return "unknown"

    def overview(self) -> dict[str, int]:
        return {
            "objects": len(self.objects),
            "bytes": sum(obj.size for obj in self.objects),
        }

    def extension_stats(self, extension: str) -> dict[str, int | str]:
        return self.filtered_stats(extension=extension)

    def prefix_stats(self, prefix: str) -> dict[str, int | str]:
        return self.filtered_stats(prefix=prefix)

    def filtered_stats(
        self,
        prefix: str | None = None,
        extension: str | None = None,
        name_suffix: str | None = None,
        known_name_suffixes: list[str] | None = None,
    ) -> dict[str, int | str]:
        rows = self.objects

        normalized_prefix = ""
        if prefix:
            normalized_prefix = self.normalize_key(prefix).rstrip("/")
            rows = [
                obj for obj in rows
                if self._is_under_prefix(obj.key, normalized_prefix)
            ]

        normalized_name_suffix = ""
        if name_suffix:
            normalized_name_suffix = self._normalize_suffix(name_suffix)
            rows = [
                obj for obj in rows
                if self._matches_name_suffix(
                    obj.key,
                    normalized_name_suffix,
                    known_name_suffixes or [],
                )
            ]

        normalized_extension = ""
        if extension and not normalized_name_suffix:
            normalized_extension = extension.lower().strip()
            if not normalized_extension.startswith("."):
                normalized_extension = f".{normalized_extension}"

            rows = [
                obj for obj in rows
                if obj.key.lower().endswith(normalized_extension)
            ]

        storage_classes: dict[str, dict[str, int | str]] = {}
        for obj in rows:
            storage_class = obj.storage_class or "UNKNOWN"
            if storage_class not in storage_classes:
                storage_classes[storage_class] = {
                    "storage_class": storage_class,
                    "objects": 0,
                    "bytes": 0,
                }
            storage_classes[storage_class]["objects"] = int(storage_classes[storage_class]["objects"]) + 1
            storage_classes[storage_class]["bytes"] = int(storage_classes[storage_class]["bytes"]) + obj.size

        storage_class_breakdown = sorted(
            storage_classes.values(),
            key=lambda row: int(row["bytes"]),
            reverse=True,
        )

        return {
            "prefix": f"{normalized_prefix}/" if normalized_prefix else "(bucket root)",
            "extension": normalized_extension or "(all files)",
            "name_suffix": normalized_name_suffix or "",
            "objects": len(rows),
            "bytes": sum(obj.size for obj in rows),
            "storage_classes": storage_class_breakdown,
        }

    def filter_objects(
        self,
        prefix: str | None = None,
        extension: str | None = None,
        name_suffix: str | None = None,
        known_name_suffixes: list[str] | None = None,
    ) -> list[BucketObject]:
        rows = self.objects

        if prefix:
            normalized_prefix = self.normalize_key(prefix).rstrip("/")
            rows = [
                obj for obj in rows
                if self._is_under_prefix(obj.key, normalized_prefix)
            ]

        if name_suffix:
            normalized_name_suffix = self._normalize_suffix(name_suffix)
            rows = [
                obj for obj in rows
                if self._matches_name_suffix(
                    obj.key,
                    normalized_name_suffix,
                    known_name_suffixes or [],
                )
            ]

        if extension and not name_suffix:
            normalized_extension = extension.lower().strip()
            if not normalized_extension.startswith("."):
                normalized_extension = f".{normalized_extension}"

            rows = [
                obj for obj in rows
                if obj.key.lower().endswith(normalized_extension)
            ]

        return sorted(rows, key=lambda obj: obj.key)


    def top_prefixes(self, depth: int = 1, limit: int = 10) -> list[dict[str, int | str]]:
        stats: dict[str, dict[str, int | str]] = {}

        for obj in self.objects:
            parts = [part for part in obj.key.strip("/").split("/") if part]
            prefix = "(bucket root)" if not parts else f"{'/'.join(parts[:depth])}/"

            if prefix not in stats:
                stats[prefix] = {"prefix": prefix, "objects": 0, "bytes": 0}

            stats[prefix]["objects"] = int(stats[prefix]["objects"]) + 1
            stats[prefix]["bytes"] = int(stats[prefix]["bytes"]) + obj.size

        return sorted(
            stats.values(),
            key=lambda row: int(row["bytes"]),
            reverse=True,
        )[:limit]

    def extension_breakdown(self, limit: int = 20) -> list[dict[str, int | str]]:
        stats: dict[str, dict[str, int | str]] = {}

        for obj in self.objects:
            name = obj.key.rsplit("/", 1)[-1]
            if "." not in name:
                ext = "(no extension)"
            else:
                ext = f".{name.split('.')[-1].lower()}"

            if ext not in stats:
                stats[ext] = {"extension": ext, "objects": 0, "bytes": 0}

            stats[ext]["objects"] = int(stats[ext]["objects"]) + 1
            stats[ext]["bytes"] = int(stats[ext]["bytes"]) + obj.size

        return sorted(
            stats.values(),
            key=lambda row: int(row["bytes"]),
            reverse=True,
        )[:limit]

    @classmethod
    def normalize_key(cls, value: str) -> str:
        value = (value or "").strip()
        value = value.replace("\\", "/")

        if value.startswith("s3://"):
            parts = value.removeprefix("s3://").split("/", 1)
            value = parts[1] if len(parts) == 2 else ""

        while "//" in value:
            value = value.replace("//", "/")

        return unquote_plus(value.strip("/"))

    @classmethod
    def _is_under_prefix(cls, key: str, prefix: str) -> bool:
        normalized_key = cls.normalize_key(key)
        normalized_prefix = cls.normalize_key(prefix).rstrip("/")

        if not normalized_prefix:
            return True

        return (
            normalized_key == normalized_prefix
            or normalized_key.startswith(normalized_prefix + "/")
        )

    @classmethod
    def _matches_name_suffix(
        cls,
        key: str,
        suffix: str,
        known_name_suffixes: list[str],
    ) -> bool:
        filename = cls.normalize_key(key).rsplit("/", 1)[-1].lower()
        normalized_suffix = cls._normalize_suffix(suffix)

        if not normalized_suffix:
            return True

        if normalized_suffix == "beagle.imputation.vcf.gz":
            return (
                filename == normalized_suffix
                or filename.endswith(".beagle.imputation.vcf.gz")
            )

        if normalized_suffix == "imputation.vcf.gz":
            if not (
                filename == normalized_suffix
                or filename.endswith(".imputation.vcf.gz")
            ):
                return False

            tokens = filename.split(".")
            try:
                imputation_index = tokens.index("imputation")
            except ValueError:
                return False

            previous_token = tokens[imputation_index - 1] if imputation_index > 0 else ""
            return previous_token != "beagle"

        return filename == normalized_suffix or filename.endswith("." + normalized_suffix)

    @staticmethod
    def _normalize_suffix(suffix: str) -> str:
        return (suffix or "").lower().strip().lstrip(".")

    def _load_objects(self) -> list[BucketObject]:
        path = self._resolve_inventory_path()
        self.resolved_inventory_path = path

        if path is None or not path.exists() or not path.is_file():
            return []

        text = path.read_text(encoding="utf-8")
        first_data_line = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            "",
        )

        if "," in first_data_line:
            if self._looks_like_csv_header(first_data_line):
                return self._load_header_csv_objects(path)
            return self._load_headerless_csv_objects(path)

        return self._load_plain_inventory_objects(text)

    def _resolve_inventory_path(self) -> Path | None:
        if self.inventory_path.is_file():
            return self.inventory_path

        if not self.inventory_path.exists() or not self.inventory_path.is_dir():
            return self.inventory_path

        candidates = [
            path
            for path in self.inventory_path.rglob("*")
            if path.is_file()
            and not path.name.startswith(".")
            and path.suffix.lower() in {".csv", ".txt", ".tsv", ".inventory", ""}
        ]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda path: (
                self._path_date_sort_key(path),
                path.stat().st_mtime,
            ),
        )

    def _path_date_sort_key(self, path: Path) -> str:
        return self._extract_date_from_path(path) or ""

    @staticmethod
    def _extract_date_from_path(path: Path) -> str:
        text = str(path)

        iso = re.findall(r"(20\d{2})[-_/]?(0[1-9]|1[0-2])[-_/]?([0-2]\d|3[01])", text)
        if iso:
            year, month, day = iso[-1]
            return f"{year}-{month}-{day}"

        return ""

    def _load_header_csv_objects(self, path: Path) -> list[BucketObject]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            objects = []

            for row in reader:
                obj = self._parse_header_csv_row(row)
                if obj is not None:
                    objects.append(obj)

        return objects

    def _load_headerless_csv_objects(self, path: Path) -> list[BucketObject]:
        objects = []
        inventory_date = self._extract_date_from_path(path)

        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)

            for row in reader:
                obj = self._parse_headerless_csv_row(row, inventory_date=inventory_date)
                if obj is not None:
                    objects.append(obj)

        return objects

    def _load_plain_inventory_objects(self, text: str) -> list[BucketObject]:
        objects = []

        for line in text.splitlines():
            obj = self._parse_plain_inventory_line(line)
            if obj is not None:
                objects.append(obj)

        return objects

    def _parse_header_csv_row(self, row: dict[str, str]) -> BucketObject | None:
        normalized = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in row.items()
        }

        key = (
            normalized.get("key")
            or normalized.get("object_key")
            or normalized.get("object key")
            or normalized.get("s3_key")
            or normalized.get("path")
            or normalized.get("name")
        )

        if not key:
            return None

        size_raw = (
            normalized.get("size")
            or normalized.get("object_size")
            or normalized.get("object size")
            or normalized.get("bytes")
            or "0"
        )

        return BucketObject(
            key=self.normalize_key(key),
            size=self._parse_size(size_raw),
            last_modified=(
                normalized.get("last_modified")
                or normalized.get("lastmodifieddate")
                or normalized.get("last modified")
                or ""
            ),
            storage_class=(
                normalized.get("storage_class")
                or normalized.get("storageclass")
                or ""
            ),
            inventory_date=(
                normalized.get("inventory_date")
                or normalized.get("listing_date")
                or normalized.get("date")
                or ""
            ),
        )

    def _parse_headerless_csv_row(
        self,
        row: list[str],
        inventory_date: str = "",
    ) -> BucketObject | None:
        row = [(value or "").strip() for value in row]

        if len(row) < 3:
            return None

        # Real observed format:
        # bucket,key,size,storage_class
        if len(row) >= 4 and self._is_number(row[2]):
            return BucketObject(
                key=self.normalize_key(row[1]),
                size=self._parse_size(row[2]),
                storage_class=row[3],
                inventory_date=inventory_date,
            )

        # Fallback:
        # key,size,storage_class
        if len(row) >= 3 and self._is_number(row[1]):
            return BucketObject(
                key=self.normalize_key(row[0]),
                size=self._parse_size(row[1]),
                storage_class=row[2],
                inventory_date=inventory_date,
            )

        return None

    def _parse_plain_inventory_line(self, line: str) -> BucketObject | None:
        line = line.strip()
        if not line or line.startswith("#"):
            return None

        if " " not in line and "\t" not in line:
            return BucketObject(key=self.normalize_key(line), size=0)

        parts = re.split(r"\s+", line, maxsplit=3)

        if len(parts) == 4 and self._is_number(parts[2]):
            return BucketObject(
                key=self.normalize_key(parts[3]),
                size=self._parse_size(parts[2]),
                last_modified=f"{parts[0]}T{parts[1]}",
            )

        if len(parts) >= 2 and self._is_number(parts[0]):
            return BucketObject(
                key=self.normalize_key(" ".join(parts[1:])),
                size=self._parse_size(parts[0]),
            )

        if len(parts) >= 3 and self._is_number(parts[1]):
            return BucketObject(
                key=self.normalize_key(" ".join(parts[2:])),
                size=self._parse_size(parts[1]),
                last_modified=parts[0],
            )

        candidate = parts[-1]
        if "/" in candidate or candidate.startswith("s3://"):
            return BucketObject(key=self.normalize_key(candidate), size=0)

        return None

    @staticmethod
    def _looks_like_csv_header(line: str) -> bool:
        fields = {field.strip().lower() for field in line.split(",")}
        return bool(fields & {"key", "object_key", "object key", "s3_key", "path", "name"})

    @staticmethod
    def _is_number(value: str) -> bool:
        try:
            float(value.replace(",", ""))
            return True
        except ValueError:
            return False

    @staticmethod
    def _parse_size(value: str) -> int:
        try:
            return max(int(float((value or "0").replace(",", ""))), 0)
        except ValueError:
            return 0

    @staticmethod
    def format_bytes(value: int) -> str:
        size = float(value)
        units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]

        for unit in units:
            if size < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.2f} {unit}"
            size /= 1024

        return f"{value} B"
