from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.batch_status_store import BatchStatusStore
from bioops.tools.llm_action_router import (
    LLMActionRouter,
    format_action_routing_error,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = PROJECT_ROOT / "configs" / "agents.yaml"


class BatchStatusAgent(BaseAgent):
    """Answer read-only batch status questions from the persisted database."""

    name = "batch_status"
    description = "Answers questions about batch processing status from the Batch Status DB."

    def __init__(
        self,
        config_path: Path = AGENTS_CONFIG_PATH,
        action_router: LLMActionRouter | None = None,
        store: BatchStatusStore | None = None,
    ) -> None:
        config = self._load_config(config_path)
        batch_config = config.get("agents", {}).get("batch_status", {}) or {}
        self.db_path = (
            os.getenv("BATCH_STATUS_DB_PATH")
            or batch_config.get("db_path")
            or "/data/bioops_batch_status.sqlite3"
        )
        self.stale_after_minutes = int(batch_config.get("stale_after_minutes", 30))
        self.store = store or BatchStatusStore(self.db_path)
        self.action_router = action_router or self._build_action_router()

    def run(self, message: str) -> str:
        try:
            decision = self.action_router.route(message)
        except Exception as error:
            return format_action_routing_error("Batch Status Agent", error)

        parameters = decision.parameters
        limit = self._bounded_limit(parameters.get("limit"), default=20, maximum=200)

        if decision.action == "specific_batch":
            batch_id = self._required_text(parameters, "batch_id")
            if batch_id is None:
                return self._invalid_parameters(
                    "specific_batch requires a non-empty batch_id."
                )
            rows = self.store.find_by_batch_id(batch_id)
            return self._format_batch_answer(batch_id, rows) if rows else self._not_found(batch_id)

        if decision.action == "latest":
            return self._format_latest(limit=min(limit, 50))
        if decision.action == "failed":
            return self._format_filtered_statuses(
                {"Failed", "Error"},
                "Failed/Error batches",
                limit=limit,
            )
        if decision.action == "running":
            return self._format_filtered_statuses(
                {"Running", "Pending"},
                "Running/Pending batches",
                limit=limit,
            )
        if decision.action == "completed":
            return self._format_filtered_statuses(
                {"Succeeded", "Completed"},
                "Completed batches",
                limit=limit,
            )
        if decision.action == "stale":
            return self._format_stale(limit=limit)
        if decision.action == "export_info":
            return self._export_info()
        if decision.action == "sync_info":
            return self._sync_info()
        return self._help()

    def process(self, message: str) -> str:
        return self.run(message)

    def handle(self, message: str) -> str:
        return self.run(message)

    @staticmethod
    def _build_action_router() -> LLMActionRouter:
        return LLMActionRouter(
            agent_name="Batch Status Agent",
            actions={
                "specific_batch": "Read records for one explicitly named batch ID.",
                "latest": "Show the latest batch status records.",
                "failed": "Show Failed or Error records.",
                "running": "Show Running or Pending records.",
                "completed": "Show Succeeded or Completed records.",
                "stale": "Show active records whose last check is older than the threshold.",
                "export_info": "Explain the read-only CSV/JSON export path and command.",
                "sync_info": "Explain the read-only synchronization command and schedule.",
                "help": "Explain supported Batch Status questions.",
            },
            parameter_schema={
                "batch_id": "Exact batch ID from the user's request; otherwise null.",
                "limit": "Optional integer result limit between 1 and 200.",
            },
            rules=[
                "Never start synchronization, export, or a Kubernetes Job from chat.",
                "Choose specific_batch only when the user supplies an explicit batch ID.",
                "Choose completed for successfully finished batches.",
                "Choose stale for active records that have not been refreshed recently.",
            ],
            examples=[
                {
                    "request": "What is the status of batch-140325?",
                    "action": "specific_batch",
                    "parameters": {"batch_id": "batch-140325", "limit": None},
                    "reason": "An exact batch ID is present.",
                },
                {
                    "request": "Export batch status to CSV",
                    "action": "export_info",
                    "parameters": {"batch_id": None, "limit": None},
                    "reason": "Chat may explain export but must not run the job.",
                },
            ],
        )

    def _format_batch_answer(self, batch_id: str, rows: list[dict[str, str]]) -> str:
        lines = [f"Batch Status: {batch_id}", f"Records found: {len(rows)}", ""]
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
        return "\n".join(
            ["Latest Batch Status Records", "", *[self._compact_row(row) for row in rows]]
        )

    def _format_filtered_statuses(
        self,
        statuses: set[str],
        title: str,
        *,
        limit: int,
    ) -> str:
        rows = self.store.list_rows(limit=limit)
        normalized_statuses = {status.casefold() for status in statuses}
        filtered = [
            row
            for row in rows
            if (row.get("status") or "").strip().casefold() in normalized_statuses
        ]
        if not filtered:
            return f"No {title.lower()} found in the latest {len(rows)} database records."
        return "\n".join([title, "", *[self._compact_row(row) for row in filtered[:10]]])

    def _format_stale(self, *, limit: int) -> str:
        rows = self.store.list_rows(limit=limit)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.stale_after_minutes)
        stale_rows = [row for row in rows if self._is_stale_active_row(row, cutoff)]
        if not stale_rows:
            return (
                "No stale active batches found in the latest "
                f"{len(rows)} database records.\n"
                f"Stale threshold: {self.stale_after_minutes} minutes."
            )
        return "\n".join(
            [
                f"Stale active batches (>{self.stale_after_minutes} minutes)",
                "",
                *[self._compact_row(row) for row in stale_rows[:10]],
            ]
        )

    def _is_stale_active_row(
        self,
        row: dict[str, str],
        cutoff: datetime,
    ) -> bool:
        status = (row.get("status") or "").strip().casefold()
        if status not in {"running", "pending"}:
            return False
        checked_at = self._parse_datetime(row.get("last_checked_at") or "")
        return checked_at is not None and checked_at < cutoff

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _compact_row(self, row: dict[str, str]) -> str:
        text = (
            f"- {row.get('batch_id') or '-'}: {row.get('status') or 'Unknown'}, "
            f"progress {row.get('progress') or '-'}, "
            f"step {row.get('current_step') or '-'}, "
            f"workflow {row.get('workflow_name') or '-'}, "
            f"checked {row.get('last_checked_at') or '-'}"
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

    def _export_info(self) -> str:
        return (
            "Batch Status export is read-only from chat. No export job was started.\n\n"
            "The Kubernetes batch-status job runs:\n"
            "python -m bioops.jobs.batch_status_export "
            "--db-path /data/bioops_batch_status.sqlite3 "
            "--csv-path /data/batch_status.csv "
            "--json-path /data/batch_status.json\n\n"
            "Expected files:\n"
            "- /data/batch_status.csv\n"
            "- /data/batch_status.json"
        )

    def _sync_info(self) -> str:
        return (
            "Batch Status synchronization is read-only from chat. No Kubernetes Job "
            "was started.\n\n"
            "Run the configured CronJob or execute:\n"
            "python -m bioops.jobs.batch_status_sync --limit 100 --no-sheet"
        )

    def _help(self) -> str:
        return (
            "Batch Status Agent\n\n"
            "I answer from the persistent Batch Status database.\n\n"
            "Supported requests:\n"
            "- status of one explicit batch ID\n"
            "- latest batch statuses\n"
            "- failed, running, completed, or stale batches\n"
            "- read-only export and synchronization instructions"
        )

    @staticmethod
    def _required_text(parameters: dict[str, Any], key: str) -> str | None:
        value = parameters.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    @staticmethod
    def _bounded_limit(value: Any, *, default: int, maximum: int) -> int:
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(1, min(parsed, maximum))

    @staticmethod
    def _invalid_parameters(detail: str) -> str:
        return "\n".join(
            [
                "Batch Status action parameters are invalid",
                "",
                f"Error: {detail}",
                "No database query was started.",
            ]
        )

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
