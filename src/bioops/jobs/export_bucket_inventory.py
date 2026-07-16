from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3

from bioops.tools.time_format import format_moscow_datetime, now_moscow


CSV_FIELDS = ["key", "size", "last_modified", "storage_class", "inventory_date"]


def export_bucket_inventory(
    *,
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
    bucket_name: str,
    output_path: str | Path,
    prefix: str = "",
) -> dict[str, int | str]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )
    paginator = client.get_paginator("list_objects_v2")
    inventory_date = now_moscow().date().isoformat()

    object_count = 0
    total_bytes = 0
    temporary = output.with_suffix(output.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                size = int(obj.get("Size", 0))
                writer.writerow(
                    {
                        "key": obj.get("Key", ""),
                        "size": size,
                        "last_modified": _format_datetime(obj.get("LastModified")),
                        "storage_class": obj.get("StorageClass") or "STANDARD",
                        "inventory_date": inventory_date,
                    }
                )
                object_count += 1
                total_bytes += size

    temporary.replace(output)
    return {
        "bucket": bucket_name,
        "output_path": str(output),
        "objects": object_count,
        "bytes": total_bytes,
        "inventory_date": inventory_date,
    }


def _format_datetime(value: Any) -> str:
    if value is None:
        return ""
    return format_moscow_datetime(value, fallback="")


def main() -> None:
    endpoint = os.getenv("S3_ENDPOINT_URL", "https://storage.yandexcloud.net")
    access_key = os.getenv("S3_ACCESS_KEY_ID", "")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY", "")
    bucket = os.getenv("BUCKET_NAME", "genotek-testing")
    prefix = os.getenv("BUCKET_PREFIX", "")
    output = os.getenv("BUCKET_INVENTORY_PATH", "data/bucket_inventory.csv")

    missing = [
        name
        for name, value in (
            ("S3_ACCESS_KEY_ID", access_key),
            ("S3_SECRET_ACCESS_KEY", secret_key),
            ("BUCKET_NAME", bucket),
            ("BUCKET_INVENTORY_PATH", output),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")

    result = export_bucket_inventory(
        endpoint_url=endpoint,
        access_key_id=access_key,
        secret_access_key=secret_key,
        bucket_name=bucket,
        output_path=output,
        prefix=prefix,
    )
    print(
        "Exported {objects} objects ({bytes} bytes) from {bucket} to {output_path}; "
        "inventory date {inventory_date}".format(**result)
    )


if __name__ == "__main__":
    main()
