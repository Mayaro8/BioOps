from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml

from bioops.tools.batch_status_argo import BatchStatusArgoScanner
from bioops.tools.batch_status_rows import workflows_to_batch_status_rows
from bioops.tools.batch_status_store import BatchStatusStore


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = PROJECT_ROOT / "configs" / "agents.yaml"


def main() -> None:
    args = parse_args()
    config = load_config()

    batch_config = config.get("agents", {}).get("batch_status", {}) or {}
    submit_config = config.get("agents", {}).get("submit_master", {}) or {}

    namespace = batch_config.get(
        "argo_namespace",
        submit_config.get("argo_namespace", "bioops-dev"),
    )
    workflow_template_name = batch_config.get(
        "argo_workflow_template",
        submit_config.get("argo_workflow_template", "bioops-submit-master-local"),
    )
    workflow_name_prefix = batch_config.get(
        "workflow_name_prefix",
        submit_config.get("workflow_name_prefix", "bioops-submit-master"),
    )

    scanner = BatchStatusArgoScanner(
        namespace=namespace,
        workflow_name_prefix=workflow_name_prefix,
        workflow_template_name=workflow_template_name,
        label_selector=batch_config.get("workflow_label_selector", ""),
    )

    workflows = scanner.list_matching_workflows()

    if args.limit:
        workflows = workflows[: args.limit]

    rows = workflows_to_batch_status_rows(
        workflows,
        argo_ui_url=submit_config.get("argo_ui_url", ""),
    )

    print("Batch Status Sync")
    print(f"Namespace: {namespace}")
    print(f"Workflows found: {len(workflows)}")
    print(f"Rows prepared: {len(rows)}")

    if args.dry_run:
        print("")
        print_table(rows)
        return

    db_path = (
        args.db_path
        or os.getenv("BATCH_STATUS_DB_PATH")
        or batch_config.get("db_path")
        or "/tmp/bioops_batch_status.sqlite3"
    )

    store = BatchStatusStore(db_path)
    db_result = store.upsert_rows(rows)

    print("")
    print("Database updated")
    print(f"db_path: {db_path}")
    for key, value in db_result.items():
        print(f"{key}: {value}")

    if args.no_sheet:
        return

    sheet_config = batch_config.get("google_sheet", {}) or {}
    if not sheet_config.get("enabled", False):
        print("")
        print("Google Sheet sync skipped: google_sheet.enabled is false.")
        return

    # Lazy import so DB-only mode works even before Google API dependencies
    # are configured in the image.
    from bioops.tools.google_sheet_status_sync import GoogleSheetStatusSync

    sync = GoogleSheetStatusSync(
        spreadsheet_id=sheet_config.get("spreadsheet_id", ""),
        worksheet_name=sheet_config.get("worksheet_name", "batch_status"),
    )
    result = sync.upsert_rows(rows)

    print("")
    print("Google Sheet updated")
    for key, value in result.items():
        print(f"{key}: {value}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Argo batch statuses to database and optional Google Sheet."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print extracted rows without updating database or Google Sheet.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of workflows processed.",
    )
    parser.add_argument(
        "--db-path",
        default="",
        help="SQLite database path for storing batch status rows.",
    )
    parser.add_argument(
        "--no-sheet",
        action="store_true",
        help="Update database only; do not sync to Google Sheet.",
    )
    return parser.parse_args()


def load_config(path: Path = AGENTS_CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def print_table(rows: list[dict[str, str]]) -> None:
    if not rows:
        print("No rows to print.")
        return

    columns = [
        "batch_id",
        "workflow_name",
        "workflow_template",
        "status",
        "progress",
        "current_step",
        "started_at",
        "finished_at",
        "error_message",
    ]

    print("\t".join(columns))
    for row in rows:
        print("\t".join(row.get(column, "") for column in columns))


if __name__ == "__main__":
    main()
