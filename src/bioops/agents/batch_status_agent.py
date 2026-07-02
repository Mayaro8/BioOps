from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.batch_status_store import BatchStatusStore


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = PROJECT_ROOT / "configs" / "agents.yaml"


class BatchStatusAgent(BaseAgent):
    """Answer batch status questions from the persisted batch_status database."""

    name = "batch_status"
    description = "Answers questions about batch processing status from the Batch Status DB."

    def __init__(self, config_path: Path = AGENTS_CONFIG_PATH) -> None:
        config = self._load_config(config_path)
        batch_config = config.get("agents", {}).get("batch_status", {}) or {}

        self.db_path = (
            os.getenv("BATCH_STATUS_DB_PATH")
            or batch_config.get("db_path")
            or "/data/bioops_batch_status.sqlite3"
        )
        self.store = BatchStatusStore(self.db_path)

    def run(self, message: str) -> str:
        message = (message or "").strip()
        lowered = message.lower()

        if not message:
            return self._help()

        batch_id = self._extract_batch_id(message)
        if batch_id:
            rows = self.store.find_by_batch_id(batch_id)
            if rows:
                return self._format_batch_answer(batch_id, rows)
            return self._not_found(batch_id)

        if any(word in lowered for word in ["failed", "error", "broken"]):
            return self._format_filtered_statuses({"Failed", "Error"}, "Failed/Error batches")

        if any(word in lowered for word in ["running", "pending", "active"]):
            return self._format_filtered_statuses({"Running", "Pending"}, "Running/Pending batches")

        if any(word in lowered for word in ["latest", "recent", "all", "status", "statuses"]):
            return self._format_latest()

        return self._help()

    def process(self, message: str) -> str:
        """Compatibility alias for orchestrators that call process()."""
        return self.run(message)

    def handle(self, message: str) -> str:
        """Compatibility alias for orchestrators that call handle()."""
        return self.run(message)

    def _extract_batch_id(self, message: str) -> str | None:
        patterns = [
            r"\bbatch[_\-\s]*id\s*[:=]?\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)\b",
            r"\bbatch\s+([A-Za-z0-9][A-Za-z0-9_.\-]*)\b",
            r"\b(batch[A-Za-z0-9_.\-]+)\b",
        ]

        stopwords = {
            "status",
            "statuses",
            "state",
            "progress",
            "failed",
            "running",
            "latest",
            "recent",
            "all",
            "batch",
            "batches",
        }

        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if not match:
                continue

            candidate = match.group(1).strip()
            candidate = re.sub(r"\s+", "-", candidate)

            if not candidate or candidate.lower() in stopwords:
                continue

            if candidate.lower().startswith("batch"):
                return candidate

            # For phrases like "batch 140325", support stored IDs like batch140325.
            compact = f"batch{candidate}"
            rows = self.store.find_by_batch_id(compact)
            if rows:
                return compact

            dashed = f"batch-{candidate}"
            rows = self.store.find_by_batch_id(dashed)
            if rows:
                return dashed

            return compact

        return None

    def _format_batch_answer(self, batch_id: str, rows: list[dict[str, str]]) -> str:
        lines = [
            f"Batch Status: {batch_id}",
            f"Records found: {len(rows)}",
            "",
        ]

        for index, row in enumerate(rows[:5], start=1):
            lines.extend(
                [
                    f"{index}. Workflow: {row.get('workflow_name') or '-'}",
                    f"   Status: {row.get('status') or 'Unknown'}",
                    f"   Progress: {row.get('progress') or '-'}",
                    f"   Current step: {row.get('current_step') or '-'}",
                    f"   Stage: {row.get('stage') or '-'}",
                    f"   Mode: {row.get('mode') or '-'}",
                    f"   Samples: {row.get('sample_ids') or '-'}",
                    f"   Started: {row.get('started_at') or '-'}",
                    f"   Finished: {row.get('finished_at') or '-'}",
                    f"   Last checked: {row.get('last_checked_at') or '-'}",
                ]
            )

            error_message = row.get("error_message") or ""
            if error_message:
                lines.append(f"   Error: {error_message}")

            argo_url = row.get("argo_url") or ""
            if argo_url:
                lines.append(f"   Argo: {argo_url}")

            lines.append("")

        if len(rows) > 5:
            lines.append(f"Showing 5 of {len(rows)} records.")

        return "\n".join(lines).strip()

    def _format_latest(self, limit: int = 10) -> str:
        rows = self.store.list_rows(limit=limit)

        if not rows:
            return (
                "No batch status records found in the database yet.\n\n"
                f"DB path: {self.db_path}\n"
                "Run the Batch Status sync job first."
            )

        lines = ["Latest Batch Status Records", ""]
        for row in rows:
            lines.append(self._compact_row(row))

        return "\n".join(lines)

    def _format_filtered_statuses(
        self,
        statuses: set[str],
        title: str,
        limit: int = 20,
    ) -> str:
        rows = self.store.list_rows(limit=limit)
        filtered = [
            row
            for row in rows
            if (row.get("status") or "").strip() in statuses
        ]

        if not filtered:
            return f"No {title.lower()} found in the latest {len(rows)} database records."

        lines = [title, ""]
        for row in filtered[:10]:
            lines.append(self._compact_row(row))

        return "\n".join(lines)

    def _compact_row(self, row: dict[str, str]) -> str:
        batch_id = row.get("batch_id") or "-"
        workflow_name = row.get("workflow_name") or "-"
        status = row.get("status") or "Unknown"
        progress = row.get("progress") or "-"
        current_step = row.get("current_step") or "-"
        checked = row.get("last_checked_at") or "-"

        text = (
            f"- {batch_id}: {status}, progress {progress}, "
            f"step {current_step}, workflow {workflow_name}, checked {checked}"
        )

        error_message = row.get("error_message") or ""
        if error_message:
            text += f"\n  Error: {error_message}"

        return text

    def _not_found(self, batch_id: str) -> str:
        return (
            f"I could not find batch `{batch_id}` in the Batch Status database.\n\n"
            f"DB path: {self.db_path}\n"
            "Run the Batch Status sync job, then try again."
        )

    def _help(self) -> str:
        return (
            "Batch Status Agent\n\n"
            "I answer from the persistent Batch Status database.\n\n"
            "Try:\n"
            "- status of batch-test-001\n"
            "- latest batch status\n"
            "- show failed batches\n"
            "- show running batches"
        )

    def _load_config(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
