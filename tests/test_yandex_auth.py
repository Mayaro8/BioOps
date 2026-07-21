from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from bioops.api import bitrix_app
from bioops.api.yandex_auth import (
    AuthStore,
    create_state_token,
    email_is_allowed,
    verify_state_token,
)


def test_domain_check_requires_exact_genotek_suffix() -> None:
    assert email_is_allowed("User@GENOTEK.RU", "genotek.ru") is True
    assert email_is_allowed("user@other.ru", "genotek.ru") is False
    assert email_is_allowed("user@evilgenotek.ru", "genotek.ru") is False


def test_oauth_state_is_signed_expires_and_rejects_external_return() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    token = create_state_token(
        secret="test-secret",
        return_to="https://evil.example",
        now=now,
    )
    payload = verify_state_token(
        token,
        secret="test-secret",
        ttl_minutes=10,
        now=now + timedelta(minutes=5),
    )

    assert payload["return_to"] == "/"
    with pytest.raises(ValueError, match="invalid"):
        verify_state_token(
            token + "tampered",
            secret="test-secret",
            ttl_minutes=10,
            now=now,
        )
    with pytest.raises(ValueError, match="expired"):
        verify_state_token(
            token,
            secret="test-secret",
            ttl_minutes=10,
            now=now + timedelta(minutes=11),
        )


def test_auth_store_links_repeated_yandex_login_to_same_user(tmp_path) -> None:
    store = AuthStore(tmp_path / "auth.sqlite3")

    first = store.link_yandex_user(
        yandex_id="yandex-123",
        email="person@genotek.ru",
        display_name="Person",
    )
    second = store.link_yandex_user(
        yandex_id="yandex-123",
        email="person@genotek.ru",
        display_name="Updated Person",
    )
    token = store.create_session(user_id=first["id"], ttl_hours=12)

    assert second["id"] == first["id"]
    assert store.get_session_user(token)["display_name"] == "Updated Person"
    store.revoke_session(token)
    assert store.get_session_user(token) is None


class FakeYandexClient:
    def __init__(self, email: str) -> None:
        self.email = email

    def authorization_url(self, state: str) -> str:
        return f"https://oauth.yandex.test/authorize?state={state}"

    def exchange_code(self, code: str) -> str:
        assert code == "valid-code"
        return "access-token"

    def get_user_info(self, access_token: str) -> dict[str, str]:
        assert access_token == "access-token"
        return {
            "id": "yandex-user-1",
            "default_email": self.email,
            "display_name": "BioOps User",
        }


@pytest.fixture
def oauth_environment(monkeypatch, tmp_path):
    values = {
        "YANDEX_AUTH_ENABLED": "true",
        "YANDEX_OAUTH_CLIENT_ID": "client-id",
        "YANDEX_OAUTH_CLIENT_SECRET": "client-secret",
        "YANDEX_OAUTH_REDIRECT_URI": (
            "https://bioops.example/auth/yandex/callback"
        ),
        "YANDEX_AUTH_ALLOWED_DOMAIN": "genotek.ru",
        "YANDEX_AUTH_ALLOWED_EMAILS": "",
        "BIOOPS_LOCAL_ACCESS_ENABLED": "true",
        "BIOOPS_LOCAL_ACCESS_CODE": "test-only-access-code",
        "BIOOPS_SESSION_SECRET": "session-secret-for-tests",
        "BIOOPS_COOKIE_SECURE": "false",
        "BIOOPS_AUTH_DB_PATH": str(tmp_path / "auth.sqlite3"),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(bitrix_app, "_auth_store", None)
    monkeypatch.setattr(bitrix_app, "_yandex_oauth_client", None)
    bitrix_app._local_login_failures.clear()


def begin_login(client: TestClient) -> str:
    response = client.get(
        "/auth/yandex/login?next=/batches",
        follow_redirects=False,
    )
    assert response.status_code == 303
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def test_protected_page_redirects_to_yandex_login(oauth_environment) -> None:
    with TestClient(bitrix_app.app) as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login?next=%2F"

        login = client.get("/login?next=/batches")
        assert login.status_code == 200
        assert "Sign in with Yandex" in login.text
        assert "next=%2Fbatches" in login.text


def test_genotek_user_signs_in_and_gets_session(
    oauth_environment, monkeypatch
) -> None:
    monkeypatch.setattr(
        bitrix_app,
        "_yandex_oauth_client",
        FakeYandexClient("person@genotek.ru"),
    )
    with TestClient(bitrix_app.app) as client:
        state = begin_login(client)
        callback = client.get(
            "/auth/yandex/callback",
            params={"code": "valid-code", "state": state},
            follow_redirects=False,
        )

        assert callback.status_code == 303
        assert callback.headers["location"] == "/batches"
        assert "bioops_session=" in callback.headers["set-cookie"]
        me = client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == "person@genotek.ru"

        logout = client.post("/logout", follow_redirects=False)
        assert logout.status_code == 303
        assert logout.headers["location"] == "/login"
        assert client.get("/auth/me").status_code == 401


def test_non_genotek_user_is_rejected_clearly(
    oauth_environment, monkeypatch
) -> None:
    monkeypatch.setattr(
        bitrix_app,
        "_yandex_oauth_client",
        FakeYandexClient("outsider@example.com"),
    )
    with TestClient(bitrix_app.app) as client:
        state = begin_login(client)
        callback = client.get(
            "/auth/yandex/callback",
            params={"code": "valid-code", "state": state},
        )

        assert callback.status_code == 403
        assert "explicitly approved users" in callback.text
        assert client.get("/auth/me").status_code == 401


def test_developer_access_code_creates_session(oauth_environment) -> None:
    with TestClient(bitrix_app.app) as client:
        rejected = client.post(
            "/auth/local",
            data={"access_code": "wrong", "return_to": "/batches"},
            follow_redirects=False,
        )
        assert rejected.status_code == 401
        assert "developer access code is invalid" in rejected.text.lower()

        accepted = client.post(
            "/auth/local",
            data={
                "access_code": "test-only-access-code",
                "return_to": "/batches",
            },
            follow_redirects=False,
        )
        assert accepted.status_code == 303
        assert accepted.headers["location"] == "/batches"
        assert client.get("/auth/me").json()["display_name"] == (
            "BioOps Developer"
        )
