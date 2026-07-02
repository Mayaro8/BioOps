from __future__ import annotations

import sqlite3
from pathlib import Path

from bioops.tools.batch_status_rows import SHEET_COLUMNS


class BatchStatusStore:
    """SQLite-backed storage for BioOps batch status rows."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        columns_sql = ",\n                    ".join(
            f"{column} TEXT NOT NULL DEFAULT ''" for column in SHEET_COLUMNS
        )

        with self._connect() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS batch_status (
                    {columns_sql},
                    PRIMARY KEY (workflow_name)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_batch_status_batch_id
                ON batch_status(batch_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_batch_status_status
                ON batch_status(status)
                """
            )

    def upsert_rows(self, rows: list[dict[str, str]]) -> dict[str, int]:
        self.initialize()

        if not rows:
            return {"rows_seen": 0, "rows_upserted": 0}

        valid_rows = [row for row in rows if row.get("workflow_name")]

        if not valid_rows:
            return {"rows_seen": len(rows), "rows_upserted": 0}

        columns = ", ".join(SHEET_COLUMNS)
        placeholders = ", ".join("?" for _ in SHEET_COLUMNS)
        updates = ", ".join(
            f"{column}=excluded.{column}"
            for column in SHEET_COLUMNS
            if column != "workflow_name"
        )

        sql = f"""
            INSERT INTO batch_status ({columns})
            VALUES ({placeholders})
            ON CONFLICT(workflow_name) DO UPDATE SET
                {updates}
        """

        values = [
            [str(row.get(column, "")) for column in SHEET_COLUMNS]
            for row in valid_rows
        ]

        with self._connect() as connection:
            connection.executemany(sql, values)

        return {
            "rows_seen": len(rows),
            "rows_upserted": len(valid_rows),
        }

    def list_rows(self, limit: int = 50) -> list[dict[str, str]]:
        self.initialize()

        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                SELECT {", ".join(SHEET_COLUMNS)}
                FROM batch_status
                ORDER BY last_checked_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            )
            return [dict(row) for row in cursor.fetchall()]

    def find_by_batch_id(self, batch_id: str) -> list[dict[str, str]]:
        self.initialize()

        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                SELECT {", ".join(SHEET_COLUMNS)}
                FROM batch_status
                WHERE batch_id = ?
                ORDER BY last_checked_at DESC
                """,
                (batch_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection
