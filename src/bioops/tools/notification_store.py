from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class NotificationStore:
    """Persistent browser notification inbox."""

    def __init__(
        self,
        db_path: str = "/data/bioops_notifications.sqlite3",
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def create(
        self,
        title: str,
        message: str,
        severity: str,
    ) -> dict:
        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO notifications (
                    title,
                    message,
                    severity,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    message.strip(),
                    severity.strip().lower(),
                    created_at,
                ),
            )
            notification_id = int(cursor.lastrowid)

        return self.get(notification_id)

    def get(self, notification_id: int) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM notifications WHERE id = ?",
                (notification_id,),
            ).fetchone()

        if row is None:
            raise KeyError(notification_id)

        return dict(row)

    def list_recent(self, limit: int = 50) -> list[dict]:
        safe_limit = max(1, min(int(limit), 200))

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM notifications
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        return [dict(row) for row in rows]

    def unread_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM notifications
                WHERE is_read = 0
                """
            ).fetchone()

        return int(row[0])

    def mark_read(self, notification_id: int) -> dict:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE notifications
                SET is_read = 1
                WHERE id = ?
                """,
                (notification_id,),
            )

            if cursor.rowcount == 0:
                raise KeyError(notification_id)

        return self.get(notification_id)
