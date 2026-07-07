from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ENDPOINT_URL = "https://storage.yandexcloud.net"
DEFAULT_BUCKET_NAME = "genotek-testing"
DEFAULT_OUTPUT_PATH = "data/bucket_inventory.csv"


def make_s3_client() -> Any:
    """
    Create an S3-compatible client.

    For Yandex Object Storage, use:
      S3_ENDPOINT_URL=https://storage.yandexcloud.net
      S3_ACCESS_KEY_ID=...
      S3_SECRET_ACCESS_KEY=...
    """
    try:
        import boto3
    except ImportError as error:
        raise RuntimeError(
            "boto3 is required for S3 export. Install requirements first."
        ) from error

    endpoint_url = os.getenv("S3_ENDPOINT_URL", DEFAULT_ENDPOINT_URL)
    access_key = os.getenv("S3_ACCESS_KEY_ID")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY")

    if not access_key or not secret_key:
        raise RuntimeError(
            "Missing S3 credentials. Set S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY."
        )

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def export_inventory(
    bucket_name: str,
    output_path: str | Path,
    prefix: str = "",
    s3_client: Any | None = None,
) -> int:
    """
    Export object metadata from S3/Object Storage to a local CSV.

    This stores metadata only, not file contents.
    CSV columns:
      key,size,last_modified,storage_class,inventory_date
    """
    s3 = s3_client or make_s3_client()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    inventory_date = datetime.now(timezone.utc).date().isoformat()
    rows_written = 0

    paginator = s3.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(
        Bucket=bucket_name,
        Prefix=prefix,
    )

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "key",
                "size",
                "last_modified",
                "storage_class",
                "inventory_date",
            ],
        )
        writer.writeheader()

        for page in page_iterator:
            for obj in page.get("Contents", []):
                last_modified = obj.get("LastModified", "")

                if hasattr(last_modified, "isoformat"):
                    last_modified = last_modified.isoformat()

                writer.writerow(
                    {
                        "key": obj.get("Key", ""),
                        "size": obj.get("Size", 0),
                        "last_modified": last_modified,
                        "storage_class": obj.get("StorageClass", ""),
                        "inventory_date": inventory_date,
                    }
                )
                rows_written += 1

    return rows_written


def main() -> None:
    bucket_name = os.getenv("BUCKET_NAME", DEFAULT_BUCKET_NAME)
    output_path = os.getenv("BUCKET_INVENTORY_PATH", DEFAULT_OUTPUT_PATH)
    prefix = os.getenv("BUCKET_PREFIX", "")

    count = export_inventory(
        bucket_name=bucket_name,
        output_path=output_path,
        prefix=prefix,
    )

    print(
        f"Exported {count} objects from bucket {bucket_name!r} "
        f"to {output_path!r}."
    )


if __name__ == "__main__":
    main()
