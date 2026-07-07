from datetime import datetime, timezone

from bioops.jobs.export_bucket_inventory import export_inventory


class FakePaginator:
    def paginate(self, Bucket, Prefix):
        assert Bucket == "genotek-testing"
        assert Prefix == "raw/"

        return [
            {
                "Contents": [
                    {
                        "Key": "raw/sample-001.bam",
                        "Size": 100,
                        "LastModified": datetime(2026, 7, 1, tzinfo=timezone.utc),
                        "StorageClass": "STANDARD",
                    },
                    {
                        "Key": "raw/sample-002.bam",
                        "Size": 200,
                        "LastModified": datetime(2026, 7, 1, tzinfo=timezone.utc),
                        "StorageClass": "STANDARD",
                    },
                ]
            }
        ]


class FakeS3Client:
    def get_paginator(self, operation_name):
        assert operation_name == "list_objects_v2"
        return FakePaginator()


def test_export_inventory_writes_metadata_csv(tmp_path):
    output = tmp_path / "bucket_inventory.csv"

    count = export_inventory(
        bucket_name="genotek-testing",
        output_path=output,
        prefix="raw/",
        s3_client=FakeS3Client(),
    )

    text = output.read_text(encoding="utf-8")

    assert count == 2
    assert "key,size,last_modified,storage_class,inventory_date" in text
    assert "raw/sample-001.bam,100" in text
    assert "raw/sample-002.bam,200" in text
    assert "STANDARD" in text
