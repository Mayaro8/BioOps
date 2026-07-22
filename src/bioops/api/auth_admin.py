from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from bioops.api.yandex_auth import AuthStore, email_is_allowed


def _store() -> AuthStore:
    return AuthStore(
        os.getenv("BIOOPS_AUTH_DB_PATH", "/data/bioops_auth.sqlite3")
    )


def _allowed_domain() -> str:
    return os.getenv("BIOOPS_AUTH_ALLOWED_DOMAIN", "genotek.ru").strip()


def _require_corporate_email(email: str) -> str:
    normalized = email.strip().casefold()
    if not email_is_allowed(normalized, _allowed_domain()):
        raise ValueError(
            f"{email!r} is not an @{_allowed_domain()} email address"
        )
    return normalized


def _add(args: argparse.Namespace) -> int:
    email = _require_corporate_email(args.email)
    row = _store().authorize_email(
        email,
        display_name=args.name,
        source="manual",
    )
    print(f"enabled\t{row['email']}\t{row['display_name']}")
    return 0


def _disable(args: argparse.Namespace) -> int:
    email = _require_corporate_email(args.email)
    changed = _store().disable_email(email)
    state = "disabled" if changed else "already-disabled-or-missing"
    print(f"{state}\t{email}")
    return 0


def _list(args: argparse.Namespace) -> int:
    rows = _store().list_authorized_emails(
        include_disabled=args.include_disabled
    )
    print("status\temail\tdisplay_name\tsource")
    for row in rows:
        status = "enabled" if row["enabled"] else "disabled"
        print(
            f"{status}\t{row['email']}\t{row['display_name']}\t"
            f"{row['source']}"
        )
    return 0


def _import_csv(args: argparse.Namespace) -> int:
    path = Path(args.path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or args.email_column not in reader.fieldnames:
            raise ValueError(
                f"CSV must contain the {args.email_column!r} column"
            )
        records = list(reader)

    prepared: list[tuple[str, str]] = []
    for line_number, record in enumerate(records, start=2):
        raw_email = str(record.get(args.email_column, ""))
        if not raw_email.strip():
            raise ValueError(f"CSV row {line_number} has no email")
        try:
            email = _require_corporate_email(raw_email)
        except ValueError as error:
            raise ValueError(f"CSV row {line_number}: {error}") from error
        display_name = str(record.get(args.name_column, "")).strip()
        prepared.append((email, display_name))

    store = _store()
    source = f"csv:{path.name}"
    for email, display_name in prepared:
        store.authorize_email(
            email,
            display_name=display_name,
            source=source,
        )
    print(f"imported\t{len(prepared)}\t{path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the BioOps corporate email database."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="Enable one corporate email.")
    add.add_argument("email")
    add.add_argument("--name", default="")
    add.set_defaults(handler=_add)

    disable = subparsers.add_parser(
        "disable", help="Disable an email and revoke its sessions."
    )
    disable.add_argument("email")
    disable.set_defaults(handler=_disable)

    list_command = subparsers.add_parser(
        "list", help="List authorized corporate emails."
    )
    list_command.add_argument(
        "--include-disabled", action="store_true"
    )
    list_command.set_defaults(handler=_list)

    import_csv = subparsers.add_parser(
        "import-csv", help="Enable every corporate email in a CSV file."
    )
    import_csv.add_argument("path")
    import_csv.add_argument("--email-column", default="email")
    import_csv.add_argument("--name-column", default="display_name")
    import_csv.set_defaults(handler=_import_csv)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
