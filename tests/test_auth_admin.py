from __future__ import annotations

import sys

import pytest

from bioops.api import auth_admin
from bioops.api.yandex_auth import AuthStore


def run_admin(monkeypatch, *arguments: str) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        ["bioops-auth-admin", *arguments],
    )
    return auth_admin.main()


def test_admin_add_list_import_and_disable(monkeypatch, tmp_path, capsys) -> None:
    database = tmp_path / "auth.sqlite3"
    monkeypatch.setenv("BIOOPS_AUTH_DB_PATH", str(database))
    monkeypatch.setenv("BIOOPS_AUTH_ALLOWED_DOMAIN", "genotek.ru")

    assert run_admin(
        monkeypatch,
        "add",
        "first@genotek.ru",
        "--name",
        "First User",
    ) == 0

    employees = tmp_path / "employees.csv"
    employees.write_text(
        "email,display_name\nsecond@genotek.ru,Second User\n",
        encoding="utf-8",
    )
    assert run_admin(monkeypatch, "import-csv", str(employees)) == 0
    assert run_admin(monkeypatch, "list") == 0
    output = capsys.readouterr().out
    assert "first@genotek.ru" in output
    assert "second@genotek.ru" in output

    assert run_admin(
        monkeypatch, "disable", "first@genotek.ru"
    ) == 0
    store = AuthStore(database)
    assert store.is_email_authorized("first@genotek.ru") is False
    assert store.is_email_authorized("second@genotek.ru") is True


def test_admin_rejects_non_corporate_email(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BIOOPS_AUTH_DB_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setenv("BIOOPS_AUTH_ALLOWED_DOMAIN", "genotek.ru")

    with pytest.raises(SystemExit):
        run_admin(monkeypatch, "add", "outsider@example.com")
