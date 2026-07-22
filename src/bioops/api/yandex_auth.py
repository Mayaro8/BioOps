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

import jwt
import requests


def _boolean_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _secure_or_local_url(value: str) -> bool:
    return (
        value.startswith("https://")
        or value.startswith("http://localhost")
        or value.startswith("http://127.0.0.1")
    )


@dataclass(frozen=True)
class CorporateSSOSettings:
    enabled: bool
    configuration_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    session_secret: str
    allowed_domain: str
    bootstrap_emails: tuple[str, ...]
    local_access_enabled: bool
    local_access_code: str
    session_cookie_name: str
    state_cookie_name: str
    session_ttl_hours: int
    state_ttl_minutes: int
    cookie_secure: bool
    request_timeout_seconds: int
    token_auth_method: str

    @classmethod
    def from_env(cls) -> "CorporateSSOSettings":
        return cls(
            enabled=_boolean_env("BIOOPS_SSO_ENABLED", True),
            configuration_url=os.getenv(
                "YANDEX_SSO_OPENID_CONFIGURATION_URL", ""
            ).strip(),
            client_id=os.getenv("YANDEX_SSO_CLIENT_ID", "").strip(),
            client_secret=os.getenv("YANDEX_SSO_CLIENT_SECRET", "").strip(),
            redirect_uri=os.getenv("YANDEX_SSO_REDIRECT_URI", "").strip(),
            session_secret=os.getenv("BIOOPS_SESSION_SECRET", "").strip(),
            allowed_domain=os.getenv(
                "BIOOPS_AUTH_ALLOWED_DOMAIN", "genotek.ru"
            ).strip().lower().lstrip("@"),
            bootstrap_emails=tuple(
                email.strip().casefold()
                for email in os.getenv(
                    "BIOOPS_AUTH_BOOTSTRAP_EMAILS", ""
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
            state_cookie_name="bioops_sso_state",
            session_ttl_hours=max(
                1, int(os.getenv("BIOOPS_SESSION_TTL_HOURS", "12"))
            ),
            state_ttl_minutes=10,
            cookie_secure=_boolean_env("BIOOPS_COOKIE_SECURE", True),
            request_timeout_seconds=max(
                1, int(os.getenv("BIOOPS_SSO_TIMEOUT_SECONDS", "10"))
            ),
            token_auth_method=os.getenv(
                "YANDEX_SSO_TOKEN_AUTH_METHOD", "client_secret_post"
            ).strip(),
        )

    def require_sso_configuration(self) -> None:
        missing = [
            name
            for name, value in {
                "YANDEX_SSO_OPENID_CONFIGURATION_URL": self.configuration_url,
                "YANDEX_SSO_CLIENT_ID": self.client_id,
                "YANDEX_SSO_CLIENT_SECRET": self.client_secret,
                "YANDEX_SSO_REDIRECT_URI": self.redirect_uri,
                "BIOOPS_SESSION_SECRET": self.session_secret,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Corporate SSO is not configured: " + ", ".join(missing)
            )
        if not _secure_or_local_url(self.configuration_url):
            raise RuntimeError(
                "YANDEX_SSO_OPENID_CONFIGURATION_URL must use HTTPS "
                "outside localhost"
            )
        if not _secure_or_local_url(self.redirect_uri):
            raise RuntimeError(
                "YANDEX_SSO_REDIRECT_URI must use HTTPS outside localhost"
            )
        if self.token_auth_method not in {
            "client_secret_basic",
            "client_secret_post",
        }:
            raise RuntimeError(
                "YANDEX_SSO_TOKEN_AUTH_METHOD must be client_secret_basic "
                "or client_secret_post"
            )

    def require_local_access_configuration(self) -> None:
        if not self.local_access_enabled:
            raise RuntimeError("Developer access is disabled")
        if len(self.local_access_code) < 5:
            raise RuntimeError(
                "BIOOPS_LOCAL_ACCESS_CODE must contain at least 5 characters"
            )


class IdentityHubOIDCClient:
    def __init__(
        self,
        settings: CorporateSSOSettings,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self._discovery: dict[str, Any] | None = None

    def _configuration(self) -> dict[str, Any]:
        if self._discovery is not None:
            return self._discovery
        response = self.session.get(
            self.settings.configuration_url,
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Identity Hub discovery response is invalid")
        required = {
            "issuer",
            "authorization_endpoint",
            "token_endpoint",
            "userinfo_endpoint",
            "jwks_uri",
        }
        missing = sorted(
            key
            for key in required
            if not isinstance(payload.get(key), str) or not payload[key]
        )
        if missing:
            raise RuntimeError(
                "Identity Hub discovery is missing: " + ", ".join(missing)
            )
        insecure = sorted(
            key
            for key in required - {"issuer"}
            if not _secure_or_local_url(str(payload[key]))
        )
        if insecure:
            raise RuntimeError(
                "Identity Hub endpoints must use HTTPS: "
                + ", ".join(insecure)
            )
        self._discovery = payload
        return payload

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_verifier: str,
    ) -> str:
        configuration = self._configuration()
        code_challenge = _base64url(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        )
        return f"{configuration['authorization_endpoint']}?{urlencode({
            'response_type': 'code',
            'client_id': self.settings.client_id,
            'redirect_uri': self.settings.redirect_uri,
            'scope': 'openid email profile',
            'state': state,
            'nonce': nonce,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        })}"

    def exchange_code(self, code: str, code_verifier: str) -> dict[str, Any]:
        configuration = self._configuration()
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.redirect_uri,
            "client_id": self.settings.client_id,
            "code_verifier": code_verifier,
        }
        auth: tuple[str, str] | None = None
        if self.settings.token_auth_method == "client_secret_post":
            data["client_secret"] = self.settings.client_secret
        else:
            auth = (self.settings.client_id, self.settings.client_secret)
        response = self.session.post(
            configuration["token_endpoint"],
            data=data,
            auth=auth,
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Identity Hub token response is invalid")
        for name in ("access_token", "id_token"):
            if not isinstance(payload.get(name), str) or not payload[name]:
                raise RuntimeError(
                    f"Identity Hub token response has no {name}"
                )
        return payload

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        configuration = self._configuration()
        response = self.session.get(
            configuration["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Identity Hub user response is invalid")
        return payload

    def verify_id_token(self, id_token: str, nonce: str) -> dict[str, Any]:
        configuration = self._configuration()
        supported = configuration.get(
            "id_token_signing_alg_values_supported", ["RS256"]
        )
        safe_algorithms = [
            algorithm
            for algorithm in supported
            if algorithm
            in {
                "RS256",
                "RS384",
                "RS512",
                "PS256",
                "PS384",
                "PS512",
                "ES256",
                "ES384",
                "ES512",
            }
        ]
        if not safe_algorithms:
            raise RuntimeError("Identity Hub has no supported signing algorithm")
        try:
            jwk_client = jwt.PyJWKClient(
                configuration["jwks_uri"],
                cache_keys=True,
                timeout=self.settings.request_timeout_seconds,
            )
            signing_key = jwk_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=safe_algorithms,
                audience=self.settings.client_id,
                issuer=configuration["issuer"],
                options={
                    "require": ["aud", "exp", "iat", "iss", "sub"],
                },
            )
        except jwt.PyJWTError as error:
            raise RuntimeError("Identity Hub ID token is invalid") from error
        if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            raise RuntimeError("Identity Hub nonce is invalid")
        return claims

    def complete_login(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
    ) -> dict[str, Any]:
        token = self.exchange_code(code, code_verifier)
        claims = self.verify_id_token(str(token["id_token"]), nonce)
        profile = self.get_user_info(str(token["access_token"]))
        if not hmac.compare_digest(
            str(claims.get("sub", "")), str(profile.get("sub", ""))
        ):
            raise RuntimeError("Identity Hub user subject does not match")
        return {**claims, **profile}


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


def sso_login_identifier(
    profile: dict[str, Any], allowed_domain: str
) -> str:
    """Return the organization-controlled identifier from OIDC claims."""
    candidates = (
        profile.get("preferred_username", ""),
        profile.get("email", ""),
    )
    for candidate in candidates:
        normalized = str(candidate).strip().casefold()
        if email_is_allowed(normalized, allowed_domain):
            return normalized
    return ""


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def create_state_token(
    *,
    secret: str,
    return_to: str,
    oidc_nonce: str = "",
    code_verifier: str = "",
    now: datetime | None = None,
) -> str:
    current = now or datetime.now(timezone.utc)
    payload = {
        "request_id": secrets.token_urlsafe(24),
        "return_to": safe_return_to(return_to),
        "issued_at": int(current.timestamp()),
    }
    if oidc_nonce:
        payload["oidc_nonce"] = oidc_nonce
    if code_verifier:
        payload["code_verifier"] = code_verifier
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
                CREATE TABLE IF NOT EXISTS authorized_emails (
                    email TEXT PRIMARY KEY COLLATE NOCASE,
                    display_name TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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

    def authorize_email(
        self,
        email: str,
        *,
        display_name: str = "",
        source: str = "manual",
    ) -> dict[str, Any]:
        normalized = email.strip().casefold()
        if not normalized or "@" not in normalized:
            raise ValueError("A valid email address is required")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO authorized_emails(
                    email, display_name, enabled, source, created_at, updated_at
                ) VALUES (?, ?, 1, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    display_name = excluded.display_name,
                    enabled = 1,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (normalized, display_name.strip(), source.strip(), now, now),
            )
            row = connection.execute(
                """
                SELECT email, display_name, enabled, source, created_at, updated_at
                FROM authorized_emails WHERE email = ? COLLATE NOCASE
                """,
                (normalized,),
            ).fetchone()
        return dict(row)

    def disable_email(self, email: str) -> bool:
        normalized = email.strip().casefold()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE authorized_emails SET enabled = 0, updated_at = ?
                WHERE email = ? COLLATE NOCASE AND enabled = 1
                """,
                (now, normalized),
            )
            connection.execute(
                """
                DELETE FROM sessions WHERE user_id IN (
                    SELECT id FROM users WHERE email = ? COLLATE NOCASE
                )
                """,
                (normalized,),
            )
        return cursor.rowcount > 0

    def is_email_authorized(self, email: str) -> bool:
        normalized = email.strip().casefold()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM authorized_emails
                WHERE email = ? COLLATE NOCASE AND enabled = 1
                """,
                (normalized,),
            ).fetchone()
        return row is not None

    def list_authorized_emails(
        self, *, include_disabled: bool = False
    ) -> list[dict[str, Any]]:
        where = "" if include_disabled else "WHERE enabled = 1"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT email, display_name, enabled, source, created_at, updated_at
                FROM authorized_emails {where}
                ORDER BY email COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]

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

    def link_sso_user(
        self,
        *,
        subject: str,
        email: str,
        display_name: str,
    ) -> dict[str, Any]:
        return self.link_external_user(
            provider="yandex_identity_hub",
            provider_user_id=subject,
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
