import csv
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from bioops.jobs.export_bucket_inventory import export_bucket_inventory


def test_exporter_writes_header_csv(tmp_path: Path) -> None:
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "data/c2023/c2023.imputed.vcf.gz",
                    "Size": 123,
                    "LastModified": datetime(2026, 7, 7, tzinfo=timezone.utc),
                    "StorageClass": "STANDARD",
                }
            ]
        }
    ]
    client = MagicMock()
    client.get_paginator.return_value = paginator
    output = tmp_path / "inventory.csv"

    with patch("bioops.jobs.export_bucket_inventory.boto3.client", return_value=client):
        result = export_bucket_inventory(
            endpoint_url="http://minio:9000",
            access_key_id="test",
            secret_access_key="test",
            bucket_name="genotek-testing",
            output_path=output,
        )

    with output.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert result["objects"] == 1
    assert rows[0]["key"] == "data/c2023/c2023.imputed.vcf.gz"
    assert rows[0]["size"] == "123"
    assert rows[0]["storage_class"] == "STANDARD"
    assert rows[0]["inventory_date"]
