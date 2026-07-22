from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from bioops.api import bitrix_app, yandex_auth
from bioops.api.yandex_auth import (
    AuthStore,
    CorporateSSOSettings,
    IdentityHubOIDCClient,
    create_state_token,
    email_is_allowed,
    verify_state_token,
)


def test_domain_check_requires_exact_genotek_suffix() -> None:
    assert email_is_allowed("User@GENOTEK.RU", "genotek.ru") is True
    assert email_is_allowed("user@other.ru", "genotek.ru") is False
    assert email_is_allowed("user@evilgenotek.ru", "genotek.ru") is False


def test_sso_state_is_signed_expires_and_rejects_external_return() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    token = create_state_token(
        secret="test-secret",
        return_to="https://evil.example",
        oidc_nonce="oidc-nonce",
        code_verifier="pkce-verifier",
        now=now,
    )
    payload = verify_state_token(
        token,
        secret="test-secret",
        ttl_minutes=10,
        now=now + timedelta(minutes=5),
    )

    assert payload["return_to"] == "/"
    assert payload["oidc_nonce"] == "oidc-nonce"
    assert payload["code_verifier"] == "pkce-verifier"
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


def test_auth_store_links_repeated_sso_login_to_same_user(tmp_path) -> None:
    store = AuthStore(tmp_path / "auth.sqlite3")
    authorized = store.authorize_email(
        "Person@GENOTEK.RU",
        display_name="Person",
        source="test",
    )

    assert authorized["email"] == "person@genotek.ru"
    assert store.is_email_authorized("PERSON@genotek.ru") is True
    assert store.list_authorized_emails()[0]["source"] == "test"

    first = store.link_sso_user(
        subject="identity-hub-user-123",
        email="person@genotek.ru",
        display_name="Person",
    )
    second = store.link_sso_user(
        subject="identity-hub-user-123",
        email="person@genotek.ru",
        display_name="Updated Person",
    )
    token = store.create_session(user_id=first["id"], ttl_hours=12)

    assert second["id"] == first["id"]
    assert store.get_session_user(token)["display_name"] == "Updated Person"
    assert store.disable_email("person@genotek.ru") is True
    assert store.is_email_authorized("person@genotek.ru") is False
    assert store.get_session_user(token) is None


class FakeSSOClient:
    def __init__(self, email: str) -> None:
        self.email = email

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_verifier: str,
    ) -> str:
        assert nonce
        assert code_verifier
        return "https://identity.test/authorize?" + (
            f"state={state}&nonce={nonce}"
        )

    def complete_login(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
    ) -> dict[str, object]:
        assert code == "valid-code"
        assert code_verifier
        assert nonce
        return {
            "sub": "identity-hub-user-1",
            "email": self.email,
            "email_verified": True,
            "name": "BioOps User",
        }


@pytest.fixture
def sso_environment(monkeypatch, tmp_path):
    values = {
        "BIOOPS_SSO_ENABLED": "true",
        "YANDEX_SSO_OPENID_CONFIGURATION_URL": (
            "https://identity.test/.well-known/openid-configuration"
        ),
        "YANDEX_SSO_CLIENT_ID": "client-id",
        "YANDEX_SSO_CLIENT_SECRET": "client-secret",
        "YANDEX_SSO_REDIRECT_URI": (
            "https://bioops.example/auth/sso/callback"
        ),
        "YANDEX_SSO_TOKEN_AUTH_METHOD": "client_secret_post",
        "BIOOPS_AUTH_ALLOWED_DOMAIN": "genotek.ru",
        "BIOOPS_AUTH_BOOTSTRAP_EMAILS": "person@genotek.ru",
        "BIOOPS_LOCAL_ACCESS_ENABLED": "true",
        "BIOOPS_LOCAL_ACCESS_CODE": "test-only-access-code",
        "BIOOPS_SESSION_SECRET": "session-secret-for-tests",
        "BIOOPS_COOKIE_SECURE": "false",
        "BIOOPS_AUTH_DB_PATH": str(tmp_path / "auth.sqlite3"),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(bitrix_app, "_auth_store", None)
    monkeypatch.setattr(bitrix_app, "_sso_client", None)
    bitrix_app._local_login_failures.clear()


def begin_login(client: TestClient) -> str:
    response = client.get(
        "/auth/sso/login?next=/batches",
        follow_redirects=False,
    )
    assert response.status_code == 303
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def test_protected_page_redirects_to_corporate_sso(
    sso_environment,
) -> None:
    with TestClient(bitrix_app.app) as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login?next=%2F"

        login = client.get("/login?next=/batches")
        assert login.status_code == 200
        assert "Continue with work email" in login.text
        assert "next=%2Fbatches" in login.text


def test_genotek_sso_user_signs_in_and_gets_session(
    sso_environment, monkeypatch
) -> None:
    monkeypatch.setattr(
        bitrix_app,
        "_sso_client",
        FakeSSOClient("person@genotek.ru"),
    )
    with TestClient(bitrix_app.app) as client:
        state = begin_login(client)
        callback = client.get(
            "/auth/sso/callback",
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


def test_non_genotek_sso_user_is_rejected_clearly(
    sso_environment, monkeypatch
) -> None:
    monkeypatch.setattr(
        bitrix_app,
        "_sso_client",
        FakeSSOClient("outsider@example.com"),
    )
    with TestClient(bitrix_app.app) as client:
        state = begin_login(client)
        callback = client.get(
            "/auth/sso/callback",
            params={"code": "valid-code", "state": state},
        )

        assert callback.status_code == 403
        assert "explicitly approved users" in callback.text
        assert client.get("/auth/me").status_code == 401


def test_unlisted_genotek_sso_user_is_rejected(
    sso_environment, monkeypatch
) -> None:
    monkeypatch.setattr(
        bitrix_app,
        "_sso_client",
        FakeSSOClient("unlisted@genotek.ru"),
    )
    with TestClient(bitrix_app.app) as client:
        state = begin_login(client)
        callback = client.get(
            "/auth/sso/callback",
            params={"code": "valid-code", "state": state},
        )

        assert callback.status_code == 403
        assert "not active in the" in callback.text
        assert "employee database" in callback.text
        assert client.get("/auth/me").status_code == 401


def test_developer_access_code_creates_session(sso_environment) -> None:
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
        assert bitrix_app.get_auth_store().is_email_authorized(
            "developer@bioops.local"
        ) is False


def test_oidc_authorization_uses_pkce_and_signed_id_token(
    sso_environment, monkeypatch
) -> None:
    settings = CorporateSSOSettings.from_env()
    client = IdentityHubOIDCClient(settings)
    client._discovery = {
        "issuer": "https://identity.test",
        "authorization_endpoint": "https://identity.test/authorize",
        "token_endpoint": "https://identity.test/token",
        "userinfo_endpoint": "https://identity.test/userinfo",
        "jwks_uri": "https://identity.test/jwks",
        "id_token_signing_alg_values_supported": ["RS256", "none"],
    }

    authorization_url = client.authorization_url(
        state="signed-state",
        nonce="expected-nonce",
        code_verifier="test-code-verifier",
    )
    query = parse_qs(urlparse(authorization_url).query)
    expected_challenge = yandex_auth._base64url(
        hashlib.sha256(b"test-code-verifier").digest()
    )
    assert query["scope"] == ["openid email profile"]
    assert query["nonce"] == ["expected-nonce"]
    assert query["code_challenge"] == [expected_challenge]
    assert query["code_challenge_method"] == ["S256"]

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    id_token = jwt.encode(
        {
            "iss": "https://identity.test",
            "aud": "client-id",
            "sub": "identity-hub-user-1",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "nonce": "expected-nonce",
            "email": "person@genotek.ru",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    class SigningKey:
        key = private_key.public_key()

    class StaticJWKClient:
        def get_signing_key_from_jwt(self, token: str):
            assert token == id_token
            return SigningKey()

    monkeypatch.setattr(
        yandex_auth.jwt,
        "PyJWKClient",
        lambda *args, **kwargs: StaticJWKClient(),
    )
    claims = client.verify_id_token(id_token, "expected-nonce")
    assert claims["sub"] == "identity-hub-user-1"
    with pytest.raises(RuntimeError, match="nonce"):
        client.verify_id_token(id_token, "wrong-nonce")
