from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bioops.api import bitrix_app
from bioops.tools.batch_status_rows import SHEET_COLUMNS
from bioops.tools.batch_status_store import BatchStatusStore


client = TestClient(bitrix_app.app)


def batch_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in SHEET_COLUMNS}
    row.update(
        {
            "batch_id": "batch-140325",
            "workflow_name": "batch-140325-sample-a",
            "workflow_template": "fastq-parent",
            "stage": "stage-2",
            "mode": "batch",
            "sample_ids": "sample-a.fastq.gz",
            "status": "Running",
            "progress": "4/10",
            "current_step": "align-reads",
            "created_at": "2026-07-21T07:00:00+00:00",
            "started_at": "2026-07-21T07:01:00+00:00",
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
            "argo_url": (
                "http://argo.example/workflows/batch-140325-sample-a"
            ),
        }
    )
    row.update(overrides)
    return row


@pytest.fixture
def batch_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> BatchStatusStore:
    store = BatchStatusStore(tmp_path / "batch-status.sqlite3")
    monkeypatch.setattr(bitrix_app, "_batch_status_store", store)
    return store


def test_batch_dashboard_page_is_available() -> None:
    response = client.get("/batches")

    assert response.status_code == 200
    assert "Batch status" in response.text
    assert 'fetch(`/api/batches?' in response.text
    assert 'href="/"' in response.text


def test_batch_api_returns_summary_and_stale_state(
    batch_store: BatchStatusStore,
) -> None:
    stale_time = datetime.now(timezone.utc) - timedelta(hours=2)
    batch_store.upsert_rows(
        [
            batch_row(last_checked_at=stale_time.isoformat()),
            batch_row(
                batch_id="batch-140326",
                workflow_name="batch-140326-sample-b",
                sample_ids="sample-b.fastq.gz",
                status="Succeeded",
                progress="10/10",
                current_step="publish-results",
            ),
            batch_row(
                batch_id="batch-140327",
                workflow_name="batch-140327-sample-c",
                sample_ids="sample-c.fastq.gz",
                status="Failed",
                error_message="align-reads: container exited with code 1",
            ),
        ]
    )

    response = client.get("/api/batches")

    assert response.status_code == 200
    payload = response.json()
    assert payload["matching"] == 3
    assert payload["summary"] == {
        "total": 3,
        "active": 1,
        "failed": 1,
        "completed": 1,
        "stale": 1,
    }
    running = next(
        item
        for item in payload["items"]
        if item["workflow_name"] == "batch-140325-sample-a"
    )
    assert running["is_stale"] is True


def test_batch_api_filters_by_search_and_state(
    batch_store: BatchStatusStore,
) -> None:
    batch_store.upsert_rows(
        [
            batch_row(),
            batch_row(
                batch_id="batch-failed",
                workflow_name="batch-failed-sample-z",
                sample_ids="sample-z.fastq.gz",
                status="Error",
            ),
        ]
    )

    response = client.get(
        "/api/batches",
        params={"search": "sample-z", "status": "failed"},
    )

    assert response.status_code == 200
    assert response.json()["matching"] == 1
    assert response.json()["items"][0]["batch_id"] == "batch-failed"


def test_batch_csv_download_uses_current_filters(
    batch_store: BatchStatusStore,
) -> None:
    batch_store.upsert_rows(
        [
            batch_row(),
            batch_row(
                batch_id="batch-failed",
                workflow_name="batch-failed-sample-z",
                status="Failed",
            ),
        ]
    )

    response = client.get(
        "/batch-status.csv",
        params={"status": "failed"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "bioops-batch-status.csv" in response.headers[
        "content-disposition"
    ]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert [row["workflow_name"] for row in rows] == [
        "batch-failed-sample-z"
    ]


def test_batch_api_rejects_unknown_filter(
    batch_store: BatchStatusStore,
) -> None:
    response = client.get("/api/batches", params={"status": "broken"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown batch status filter."
