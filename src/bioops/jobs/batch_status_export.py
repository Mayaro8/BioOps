from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from bioops.tools.batch_status_rows import SHEET_COLUMNS
from bioops.tools.batch_status_store import BatchStatusStore
from bioops.tools.time_format import format_moscow_fields


def export_csv(rows: list[dict[str, str]], path: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_COLUMNS)
        writer.writeheader()

        for row in rows:
            display_row = format_moscow_fields(row)
            writer.writerow(
                {
                    column: display_row.get(column, "")
                    for column in SHEET_COLUMNS
                }
            )


def export_json(rows: list[dict[str, str]], path: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "rows_seen": len(rows),
        "columns": SHEET_COLUMNS,
        "rows": [format_moscow_fields(row) for row in rows],
    }

    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Batch Status DB to CSV/JSON.")

    parser.add_argument(
        "--db-path",
        default="/data/bioops_batch_status.sqlite3",
        help="Path to Batch Status SQLite DB.",
    )

    parser.add_argument(
        "--csv-path",
        default="/data/batch_status.csv",
        help="Output CSV path.",
    )

    parser.add_argument(
        "--json-path",
        default="/data/batch_status.json",
        help="Output JSON path.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum number of rows to export.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    store = BatchStatusStore(args.db_path)
    rows = store.list_rows(limit=args.limit)

    export_csv(rows, args.csv_path)
    export_json(rows, args.json_path)

    print("Batch Status export complete")
    print(f"db_path: {args.db_path}")
    print(f"csv_path: {args.csv_path}")
    print(f"json_path: {args.json_path}")
    print(f"rows_exported: {len(rows)}")


if __name__ == "__main__":
    main()
