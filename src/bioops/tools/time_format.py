from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")
MOSCOW_TIMESTAMP_FIELDS = {
    "created_at",
    "started_at",
    "finished_at",
    "last_checked_at",
}


def now_moscow() -> datetime:
    return datetime.now(MOSCOW_TIMEZONE)


def format_moscow_datetime(
    value: Any,
    *,
    fallback: str = "-",
) -> str:
    parsed = _parse_datetime(value)

    if parsed is None:
        text = str(value or "").strip()
        return text or fallback

    return parsed.astimezone(
        MOSCOW_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M:%S MSK")


def format_moscow_fields(
    row: dict[str, str],
) -> dict[str, str]:
    return {
        key: (
            format_moscow_datetime(value, fallback="")
            if key in MOSCOW_TIMESTAMP_FIELDS
            else value
        )
        for key, value in row.items()
    }


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()

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

    return parsed
