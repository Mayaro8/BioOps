from bioops.tools.time_format import (
    format_moscow_datetime,
    format_moscow_fields,
)


def test_utc_is_displayed_as_moscow_time() -> None:
    assert format_moscow_datetime(
        "2026-07-15T06:00:00Z"
    ) == "2026-07-15 09:00:00 MSK"


def test_timestamp_fields_are_converted() -> None:
    result = format_moscow_fields(
        {
            "batch_id": "batch-1",
            "started_at": "2026-07-15T06:00:00Z",
        }
    )

    assert result == {
        "batch_id": "batch-1",
        "started_at": "2026-07-15 09:00:00 MSK",
    }
