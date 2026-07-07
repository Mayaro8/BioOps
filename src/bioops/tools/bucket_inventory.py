from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote_plus


_DATE_PATTERN = re.compile(r"(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)(?!\d)")


@dataclass(frozen=True)
class BucketObject:
    key: str
    size: int
    last_modified: str = ""
    storage_class: str = ""
    inventory_date: str = ""
    bucket: str = ""


class BucketInventoryTool:
    """Read-only access to an S3/MinIO inventory CSV.

    Supported CSV formats:
    1. Header CSV produced by the BioOps exporter:
       key,size,last_modified,storage_class,inventory_date
    2. Headerless company inventory:
       bucket,key,size,storage_class

    ``inventory_path`` may point to one CSV file or a directory containing
    dated CSV snapshots. When it is a directory, the newest inventory is
    chosen using: embedded inventory date, filename date, then modification
    time.
    """

    def __init__(
        self,
        inventory_path: str | Path,
        bucket_name: str = "genotek-testing",
        inventory_date: str | None = None,
    ) -> None:
        self.inventory_path = Path(inventory_path)
        self.bucket_name = bucket_name
        self.configured_inventory_date = (inventory_date or "").strip()
        self.resolved_inventory_path: Path | None = None
        self._objects: list[BucketObject] | None = None

    @property
    def objects(self) -> list[BucketObject]:
        if self._objects is None:
            self.resolved_inventory_path = self._resolve_inventory_path()
            self._objects = self._load_objects(self.resolved_inventory_path)
        return self._objects

    @property
    def inventory_file(self) -> str:
        _ = self.objects
        return self.resolved_inventory_path.name if self.resolved_inventory_path else "unknown"

    def inventory_date(self) -> str:
        if self.configured_inventory_date:
            return self.configured_inventory_date

        dates = [obj.inventory_date for obj in self.objects if obj.inventory_date]
        parsed_dates = [self._parse_date(value) for value in dates]
        parsed_dates = [value for value in parsed_dates if value is not None]
        if parsed_dates:
            return max(parsed_dates).isoformat()

        path = self.resolved_inventory_path
        if path is None:
            return "unknown"

        filename_date = self._extract_date_from_text(path.name)
        if filename_date:
            return filename_date.isoformat()

        return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()

    def overview(self) -> dict[str, object]:
        return self.filtered_stats()

    def extension_stats(self, extension: str) -> dict[str, object]:
        return self.filtered_stats(extension=extension)

    def prefix_stats(self, prefix: str) -> dict[str, object]:
        return self.filtered_stats(prefix=prefix)

    def filter_objects(
        self,
        prefix: str | None = None,
        extension: str | None = None,
        name_suffix: str | None = None,
        known_name_suffixes: Iterable[str] | None = None,
    ) -> list[BucketObject]:
        rows = list(self.objects)

        if prefix:
            normalized_prefix = self.normalize_key(prefix).rstrip("/")
            rows = [obj for obj in rows if self._is_under_prefix(obj.key, normalized_prefix)]

        if name_suffix:
            normalized_suffix = self._normalize_suffix(name_suffix)
            rows = [
                obj
                for obj in rows
                if self._matches_name_suffix(
                    obj.key,
                    normalized_suffix,
                    list(known_name_suffixes or []),
                )
            ]
        elif extension:
            normalized_extension = self._normalize_extension(extension)
            rows = [obj for obj in rows if obj.key.lower().endswith(normalized_extension)]

        return sorted(rows, key=lambda obj: obj.key)

    def filtered_stats(
        self,
        prefix: str | None = None,
        extension: str | None = None,
        name_suffix: str | None = None,
        known_name_suffixes: Iterable[str] | None = None,
    ) -> dict[str, object]:
        rows = self.filter_objects(
            prefix=prefix,
            extension=extension,
            name_suffix=name_suffix,
            known_name_suffixes=known_name_suffixes,
        )

        normalized_prefix = self.normalize_key(prefix or "").rstrip("/")
        normalized_extension = self._normalize_extension(extension) if extension and not name_suffix else ""
        normalized_suffix = self._normalize_suffix(name_suffix or "")

        by_class: dict[str, dict[str, object]] = {}
        for obj in rows:
            storage_class = (obj.storage_class or "UNKNOWN").strip() or "UNKNOWN"
            entry = by_class.setdefault(
                storage_class,
                {"storage_class": storage_class, "objects": 0, "bytes": 0},
            )
            entry["objects"] = int(entry["objects"]) + 1
            entry["bytes"] = int(entry["bytes"]) + obj.size

        storage_classes = sorted(
            by_class.values(),
            key=lambda row: (-int(row["bytes"]), str(row["storage_class"])),
        )

        return {
            "prefix": f"{normalized_prefix}/" if normalized_prefix else "(bucket root)",
            "extension": normalized_extension or "(all files)",
            "name_suffix": normalized_suffix,
            "objects": len(rows),
            "bytes": sum(obj.size for obj in rows),
            "storage_classes": storage_classes,
        }

    def top_prefixes(self, depth: int = 1, limit: int = 10) -> list[dict[str, object]]:
        stats: dict[str, dict[str, object]] = {}
        for obj in self.objects:
            parts = [part for part in obj.key.strip("/").split("/") if part]
            prefix = "(bucket root)" if not parts else f"{'/'.join(parts[:depth])}/"
            entry = stats.setdefault(prefix, {"prefix": prefix, "objects": 0, "bytes": 0})
            entry["objects"] = int(entry["objects"]) + 1
            entry["bytes"] = int(entry["bytes"]) + obj.size

        return sorted(
            stats.values(),
            key=lambda row: (-int(row["bytes"]), str(row["prefix"])),
        )[:limit]

    def extension_breakdown(self, limit: int = 20) -> list[dict[str, object]]:
        stats: dict[str, dict[str, object]] = {}
        compound_extensions = [".vcf.gz", ".gvcf.gz", ".fastq.gz", ".fq.gz", ".tar.gz"]

        for obj in self.objects:
            filename = obj.key.rsplit("/", 1)[-1].lower()
            extension = next((ext for ext in compound_extensions if filename.endswith(ext)), None)
            if extension is None:
                suffix = Path(filename).suffix
                extension = suffix if suffix else "(no extension)"

            entry = stats.setdefault(
                extension,
                {"extension": extension, "objects": 0, "bytes": 0},
            )
            entry["objects"] = int(entry["objects"]) + 1
            entry["bytes"] = int(entry["bytes"]) + obj.size

        return sorted(
            stats.values(),
            key=lambda row: (-int(row["bytes"]), str(row["extension"])),
        )[:limit]

    def _resolve_inventory_path(self) -> Path:
        path = self.inventory_path
        if path.is_file():
            return path

        if not path.exists():
            raise FileNotFoundError(f"Bucket inventory path does not exist: {path}")
        if not path.is_dir():
            raise FileNotFoundError(f"Bucket inventory path is not a file or directory: {path}")

        candidates = sorted(candidate for candidate in path.rglob("*.csv") if candidate.is_file())
        if not candidates:
            raise FileNotFoundError(f"No CSV inventory files found under: {path}")

        return max(candidates, key=self._candidate_sort_key)

    def _candidate_sort_key(self, path: Path) -> tuple[date, float]:
        embedded_date = self._read_embedded_inventory_date(path)
        filename_date = self._extract_date_from_text(path.name)
        fallback_date = datetime.fromtimestamp(path.stat().st_mtime).date()
        return embedded_date or filename_date or fallback_date, path.stat().st_mtime

    def _read_embedded_inventory_date(self, path: Path) -> date | None:
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                first = next(reader, None)
                if not first or not self._looks_like_header(first):
                    return None
                normalized = [column.strip().lower() for column in first]
                if "inventory_date" not in normalized:
                    return None
                index = normalized.index("inventory_date")
                dates: list[date] = []
                for row_number, row in enumerate(reader):
                    if row_number >= 100:
                        break
                    if index < len(row):
                        parsed = self._parse_date(row[index])
                        if parsed:
                            dates.append(parsed)
                return max(dates) if dates else None
        except (OSError, UnicodeDecodeError, csv.Error):
            return None

    def _load_objects(self, path: Path) -> list[BucketObject]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            first = next(reader, None)
            if first is None:
                return []

            if self._looks_like_header(first):
                return self._load_header_rows(first, reader)

            objects: list[BucketObject] = []
            first_obj = self._parse_headerless_row(first)
            if first_obj:
                objects.append(first_obj)
            for row in reader:
                obj = self._parse_headerless_row(row)
                if obj:
                    objects.append(obj)
            return objects

    def _load_header_rows(
        self,
        header: list[str],
        rows: Iterable[list[str]],
    ) -> list[BucketObject]:
        normalized_header = [column.strip().lower() for column in header]
        objects: list[BucketObject] = []

        for row in rows:
            if not row or not any(value.strip() for value in row):
                continue
            mapping = {
                normalized_header[index]: row[index].strip() if index < len(row) else ""
                for index in range(len(normalized_header))
            }
            key = self._first_value(
                mapping,
                "key",
                "object_key",
                "object key",
                "s3_key",
                "path",
                "name",
            )
            if not key:
                continue
            bucket = self._first_value(mapping, "bucket", "bucket_name")
            if bucket and self.bucket_name and bucket != self.bucket_name:
                continue
            objects.append(
                BucketObject(
                    key=self.normalize_key(key),
                    size=self._parse_size(
                        self._first_value(mapping, "size", "object_size", "object size", "bytes")
                    ),
                    last_modified=self._first_value(
                        mapping,
                        "last_modified",
                        "lastmodifieddate",
                        "last modified",
                    ),
                    storage_class=self._first_value(
                        mapping,
                        "storage_class",
                        "storageclass",
                        "storage class",
                    ),
                    inventory_date=self._first_value(
                        mapping,
                        "inventory_date",
                        "listing_date",
                        "snapshot_date",
                    ),
                    bucket=bucket,
                )
            )
        return objects

    def _parse_headerless_row(self, row: list[str]) -> BucketObject | None:
        values = [value.strip() for value in row]
        if not values or not any(values):
            return None

        # Observed company format: bucket,key,size,storage_class
        if len(values) >= 4 and self._is_number(values[2]):
            bucket, key, size, storage_class = values[:4]
            if self.bucket_name and bucket and bucket != self.bucket_name:
                return None
            return BucketObject(
                bucket=bucket,
                key=self.normalize_key(key),
                size=self._parse_size(size),
                storage_class=storage_class,
            )

        # Compatible fallback: key,size,storage_class
        if len(values) >= 3 and self._is_number(values[1]):
            key, size, storage_class = values[:3]
            return BucketObject(
                key=self.normalize_key(key),
                size=self._parse_size(size),
                storage_class=storage_class,
            )

        return None

    @staticmethod
    def _looks_like_header(row: list[str]) -> bool:
        fields = {field.strip().lower() for field in row}
        return bool(fields & {"key", "object_key", "object key", "s3_key", "path", "name"})

    @staticmethod
    def _first_value(mapping: dict[str, str], *keys: str) -> str:
        for key in keys:
            value = mapping.get(key, "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def normalize_key(value: str) -> str:
        normalized = (value or "").strip().replace("\\", "/")
        if normalized.startswith("s3://"):
            without_scheme = normalized[5:]
            normalized = without_scheme.split("/", 1)[1] if "/" in without_scheme else ""
        normalized = re.sub(r"/{2,}", "/", normalized)
        return unquote_plus(normalized.strip("/"))

    @classmethod
    def _is_under_prefix(cls, key: str, prefix: str) -> bool:
        normalized_key = cls.normalize_key(key)
        normalized_prefix = cls.normalize_key(prefix).rstrip("/")
        return not normalized_prefix or normalized_key == normalized_prefix or normalized_key.startswith(
            normalized_prefix + "/"
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
        known = sorted(
            {cls._normalize_suffix(item) for item in known_name_suffixes if item},
            key=len,
            reverse=True,
        )

        if not (filename == normalized_suffix or filename.endswith("." + normalized_suffix)):
            return False

        # A shorter product suffix must not absorb a more specific configured suffix.
        for specific_suffix in known:
            if specific_suffix == normalized_suffix or len(specific_suffix) <= len(normalized_suffix):
                continue
            if specific_suffix.endswith(normalized_suffix) and (
                filename == specific_suffix or filename.endswith("." + specific_suffix)
            ):
                return False
        return True

    @staticmethod
    def _normalize_suffix(value: str) -> str:
        return (value or "").strip().lower().lstrip(".")

    @staticmethod
    def _normalize_extension(value: str | None) -> str:
        if not value:
            return ""
        normalized = value.strip().lower()
        return normalized if normalized.startswith(".") else f".{normalized}"

    @staticmethod
    def _parse_size(value: str) -> int:
        try:
            return max(int(float((value or "0").replace(",", ""))), 0)
        except ValueError:
            return 0

    @staticmethod
    def _is_number(value: str) -> bool:
        try:
            float((value or "").replace(",", ""))
            return True
        except ValueError:
            return False

    @classmethod
    def _extract_date_from_text(cls, value: str) -> date | None:
        matches = list(_DATE_PATTERN.finditer(value or ""))
        if not matches:
            return None
        year, month, day = matches[-1].groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    @staticmethod
    def _parse_date(value: str) -> date | None:
        value = (value or "").strip()
        if not value:
            return None
        candidate = value[:10]
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            return None

    @staticmethod
    def format_bytes(value: int) -> str:
        size = float(value)
        units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{int(size)} {unit}" if unit == "B" else f"{size:.2f} {unit}"
            size /= 1024
        return f"{value} B"
