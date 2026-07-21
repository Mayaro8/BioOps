from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests


YANDEX_AUTHORIZE_URL = "https://oauth.yandex.com/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.com/token"
YANDEX_USER_INFO_URL = "https://login.yandex.ru/info"


def _boolean_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class YandexAuthSettings:
    enabled: bool
    client_id: str
    client_secret: str
    redirect_uri: str
    session_secret: str
    allowed_domain: str
    allowed_emails: tuple[str, ...]
    local_access_enabled: bool
    local_access_code: str
    session_cookie_name: str
    state_cookie_name: str
    session_ttl_hours: int
    state_ttl_minutes: int
    cookie_secure: bool
    request_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "YandexAuthSettings":
        return cls(
            enabled=_boolean_env("YANDEX_AUTH_ENABLED", True),
            client_id=os.getenv("YANDEX_OAUTH_CLIENT_ID", "").strip(),
            client_secret=os.getenv("YANDEX_OAUTH_CLIENT_SECRET", "").strip(),
            redirect_uri=os.getenv("YANDEX_OAUTH_REDIRECT_URI", "").strip(),
            session_secret=os.getenv("BIOOPS_SESSION_SECRET", "").strip(),
            allowed_domain=os.getenv(
                "YANDEX_AUTH_ALLOWED_DOMAIN", "genotek.ru"
            ).strip().lower().lstrip("@"),
            allowed_emails=tuple(
                email.strip().casefold()
                for email in os.getenv(
                    "YANDEX_AUTH_ALLOWED_EMAILS", ""
                ).split(",")
                if email.strip()
            ),
            local_access_enabled=_boolean_env(
                "BIOOPS_LOCAL_ACCESS_ENABLED", False
            ),
            local_access_code=os.getenv(
                "BIOOPS_LOCAL_ACCESS_CODE", ""
            ).strip(),
            session_cookie_name=os.getenv(
                "BIOOPS_SESSION_COOKIE", "bioops_session"
            ).strip(),
            state_cookie_name="bioops_oauth_state",
            session_ttl_hours=max(
                1, int(os.getenv("BIOOPS_SESSION_TTL_HOURS", "12"))
            ),
            state_ttl_minutes=10,
            cookie_secure=_boolean_env("BIOOPS_COOKIE_SECURE", True),
            request_timeout_seconds=max(
                1, int(os.getenv("YANDEX_OAUTH_TIMEOUT_SECONDS", "10"))
            ),
        )

    def require_oauth_configuration(self) -> None:
        missing = [
            name
            for name, value in {
                "YANDEX_OAUTH_CLIENT_ID": self.client_id,
                "YANDEX_OAUTH_CLIENT_SECRET": self.client_secret,
                "YANDEX_OAUTH_REDIRECT_URI": self.redirect_uri,
                "BIOOPS_SESSION_SECRET": self.session_secret,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Yandex OAuth is not configured: " + ", ".join(missing)
            )

    def require_local_access_configuration(self) -> None:
        if not self.local_access_enabled:
            raise RuntimeError("Developer access is disabled")
        if len(self.local_access_code) < 5:
            raise RuntimeError(
                "BIOOPS_LOCAL_ACCESS_CODE must contain at least 5 characters"
            )


class YandexOAuthClient:
    def __init__(
        self,
        settings: YandexAuthSettings,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()

    def authorization_url(self, state: str) -> str:
        return f"{YANDEX_AUTHORIZE_URL}?{urlencode({
            'response_type': 'code',
            'client_id': self.settings.client_id,
            'redirect_uri': self.settings.redirect_uri,
            'scope': 'login:email,login:info',
            'state': state,
        })}"

    def exchange_code(self, code: str) -> str:
        response = self.session.post(
            YANDEX_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
            },
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Yandex token response has no access_token")
        return token

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        response = self.session.get(
            YANDEX_USER_INFO_URL,
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"},
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Yandex user response is invalid")
        return payload


def email_is_allowed(
    email: str,
    allowed_domain: str,
    allowed_emails: tuple[str, ...] = (),
) -> bool:
    normalized = email.strip().casefold()
    domain = allowed_domain.strip().casefold().lstrip("@")
    exact_emails = {value.strip().casefold() for value in allowed_emails}
    return normalized in exact_emails or (
        bool(domain) and normalized.endswith(f"@{domain}")
    )


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_state_token(
    *,
    secret: str,
    return_to: str,
    now: datetime | None = None,
) -> str:
    current = now or datetime.now(timezone.utc)
    payload = {
        "nonce": secrets.token_urlsafe(24),
        "return_to": safe_return_to(return_to),
        "issued_at": int(current.timestamp()),
    }
    encoded = _base64url(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    signature = _base64url(
        hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}"


def verify_state_token(
    token: str,
    *,
    secret: str,
    ttl_minutes: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _base64url(
            hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("OAuth state signature is invalid")
        payload = json.loads(_decode_base64url(encoded))
        issued_at = datetime.fromtimestamp(
            int(payload["issued_at"]), timezone.utc
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("OAuth state is invalid") from error

    current = now or datetime.now(timezone.utc)
    if issued_at > current + timedelta(minutes=1):
        raise ValueError("OAuth state is invalid")
    if current - issued_at > timedelta(minutes=ttl_minutes):
        raise ValueError("OAuth state has expired")
    payload["return_to"] = safe_return_to(str(payload.get("return_to", "/")))
    return payload


def safe_return_to(value: str) -> str:
    cleaned = value.strip()
    if not cleaned.startswith("/") or cleaned.startswith("//"):
        return "/"
    return cleaned


class AuthStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_identities (
                    provider TEXT NOT NULL,
                    provider_user_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    PRIMARY KEY (provider, provider_user_id)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_user_id
                    ON sessions(user_id);
                """
            )

    def link_external_user(
        self,
        *,
        provider: str,
        provider_user_id: str,
        email: str,
        display_name: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            identity = connection.execute(
                """
                SELECT users.id, users.email, users.display_name
                FROM oauth_identities
                JOIN users ON users.id = oauth_identities.user_id
                WHERE provider = ? AND provider_user_id = ?
                """,
                (provider, provider_user_id),
            ).fetchone()
            if identity is not None:
                connection.execute(
                    """
                    UPDATE users SET email = ?, display_name = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (email, display_name, now, identity["id"]),
                )
                user_id = int(identity["id"])
            else:
                existing = connection.execute(
                    "SELECT id FROM users WHERE email = ? COLLATE NOCASE",
                    (email,),
                ).fetchone()
                if existing is None:
                    cursor = connection.execute(
                        """
                        INSERT INTO users(email, display_name, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (email, display_name, now, now),
                    )
                    user_id = int(cursor.lastrowid)
                else:
                    user_id = int(existing["id"])
                    connection.execute(
                        """
                        UPDATE users SET display_name = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (display_name, now, user_id),
                    )
                connection.execute(
                    """
                    INSERT INTO oauth_identities(provider, provider_user_id, user_id)
                    VALUES (?, ?, ?)
                    """,
                    (provider, provider_user_id, user_id),
                )
            row = connection.execute(
                "SELECT id, email, display_name FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return dict(row)

    def link_yandex_user(
        self,
        *,
        yandex_id: str,
        email: str,
        display_name: str,
    ) -> dict[str, Any]:
        return self.link_external_user(
            provider="yandex",
            provider_user_id=yandex_id,
            email=email,
            display_name=display_name,
        )

    def create_session(self, *, user_id: int, ttl_hours: int) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(hours=ttl_hours)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?",
                (created_at.isoformat(),),
            )
            connection.execute(
                """
                INSERT INTO sessions(token_hash, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    token_hash,
                    user_id,
                    created_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
        return token

    def get_session_user(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.email, users.display_name
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
        return dict(row) if row is not None else None

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
            )
