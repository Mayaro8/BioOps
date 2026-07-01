from __future__ import annotations

import os
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from bioops.tools.batch_status_rows import SHEET_COLUMNS


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleSheetStatusSync:
    """Upsert batch status rows into a Google Sheet."""

    def __init__(
        self,
        *,
        spreadsheet_id: str,
        worksheet_name: str = "batch_status",
        credentials_path: str | None = None,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEET_ID", "")
        self.worksheet_name = worksheet_name or os.getenv(
            "GOOGLE_SHEET_WORKSHEET", "batch_status"
        )
        self.credentials_path = credentials_path or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS", ""
        )

        if not self.spreadsheet_id:
            raise ValueError(
                "Google Sheet spreadsheet_id is missing. Set GOOGLE_SHEET_ID "
                "or configs.agents.batch_status.google_sheet.spreadsheet_id."
            )

        if not self.credentials_path:
            raise ValueError(
                "Google credentials path is missing. Set GOOGLE_APPLICATION_CREDENTIALS."
            )

        credentials = service_account.Credentials.from_service_account_file(
            self.credentials_path,
            scopes=SCOPES,
        )
        self.service = build("sheets", "v4", credentials=credentials)

    def upsert_rows(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        self.ensure_header()

        existing = self._read_all_rows()
        workflow_to_row_number = self._workflow_row_index(existing)

        updates = 0
        appends = 0

        for row in rows:
            values = [row.get(column, "") for column in SHEET_COLUMNS]
            workflow_name = row.get("workflow_name", "")

            if workflow_name and workflow_name in workflow_to_row_number:
                row_number = workflow_to_row_number[workflow_name]
                self._update_row(row_number, values)
                updates += 1
            else:
                self._append_row(values)
                appends += 1

        return {
            "rows_seen": len(rows),
            "rows_updated": updates,
            "rows_appended": appends,
            "worksheet_name": self.worksheet_name,
        }

    def find_batch(self, batch_id: str) -> list[dict[str, str]]:
        self.ensure_header()
        values = self._read_all_rows()
        if not values:
            return []

        header = values[0]
        rows = []
        for raw in values[1:]:
            row = self._row_to_dict(header, raw)
            if row.get("batch_id") == batch_id:
                rows.append(row)

        return rows

    def ensure_header(self) -> None:
        values = self._read_range(f"{self.worksheet_name}!1:1")
        first_row = values[0] if values else []

        if first_row == SHEET_COLUMNS:
            return

        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!1:1",
            valueInputOption="RAW",
            body={"values": [SHEET_COLUMNS]},
        ).execute()

    def _read_all_rows(self) -> list[list[str]]:
        return self._read_range(f"{self.worksheet_name}!A:Z")

    def _read_range(self, range_name: str) -> list[list[str]]:
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=range_name)
            .execute()
        )
        return result.get("values", [])

    def _workflow_row_index(self, values: list[list[str]]) -> dict[str, int]:
        if not values:
            return {}

        header = values[0]
        try:
            workflow_idx = header.index("workflow_name")
        except ValueError:
            return {}

        index: dict[str, int] = {}
        for offset, row in enumerate(values[1:], start=2):
            if len(row) <= workflow_idx:
                continue
            workflow_name = row[workflow_idx]
            if workflow_name:
                index[workflow_name] = offset

        return index

    def _update_row(self, row_number: int, values: list[str]) -> None:
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A{row_number}",
            valueInputOption="RAW",
            body={"values": [values]},
        ).execute()

    def _append_row(self, values: list[str]) -> None:
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A:Z",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [values]},
        ).execute()

    def _row_to_dict(self, header: list[str], raw: list[str]) -> dict[str, str]:
        return {
            key: raw[index] if index < len(raw) else ""
            for index, key in enumerate(header)
        }
