from bioops.tools.notification_store import (
    NotificationStore,
)


def test_create_list_and_mark_notification_read(
    tmp_path,
):
    store = NotificationStore(
        str(
            tmp_path
            / "notifications.sqlite3"
        )
    )

    created = store.create(
        title="Database warning",
        message="ClickHouse mutation is stuck.",
        severity="warning",
    )

    assert created["id"] == 1
    assert created["is_read"] == 0
    assert store.unread_count() == 1

    rows = store.list_recent()

    assert len(rows) == 1
    assert rows[0]["title"] == (
        "Database warning"
    )

    updated = store.mark_read(
        created["id"]
    )

    assert updated["is_read"] == 1
    assert store.unread_count() == 0


def test_list_recent_uses_newest_first(
    tmp_path,
):
    store = NotificationStore(
        str(
            tmp_path
            / "notifications.sqlite3"
        )
    )

    store.create(
        title="First",
        message="First alert",
        severity="info",
    )
    store.create(
        title="Second",
        message="Second alert",
        severity="critical",
    )

    rows = store.list_recent()

    assert rows[0]["title"] == "Second"
    assert rows[1]["title"] == "First"
