from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_caddy_no_longer_uses_shared_basic_auth() -> None:
    caddyfile = (
        ROOT / "deploy" / "k8s" / "bioops-api" / "Caddyfile"
    ).read_text(encoding="utf-8")

    assert "basic_auth" not in caddyfile
    assert "reverse_proxy 127.0.0.1:8000" in caddyfile


def test_runtime_enables_identity_hub_sso_with_secure_cookie() -> None:
    runtime = (
        ROOT / "deploy" / "k8s" / "config" / "runtime.env"
    ).read_text(encoding="utf-8")

    assert "BIOOPS_SSO_ENABLED=true" in runtime
    assert "BIOOPS_AUTH_ALLOWED_DOMAIN=genotek.ru" in runtime
    assert "BIOOPS_AUTH_BOOTSTRAP_EMAILS=" in runtime
    assert "BIOOPS_LOCAL_ACCESS_ENABLED=true" in runtime
    assert "BIOOPS_COOKIE_SECURE=true" in runtime
    assert (
        "YANDEX_SSO_REDIRECT_URI=https://"
        "bioops.84-201-181-221.sslip.io/auth/sso/callback"
    ) in runtime


def test_secret_template_lists_identity_hub_oidc_credentials() -> None:
    template = (
        ROOT / "deploy" / "k8s" / "config" / "secret.example.env"
    ).read_text(encoding="utf-8")

    assert "YANDEX_SSO_CLIENT_ID=REPLACE_ME" in template
    assert "YANDEX_SSO_CLIENT_SECRET=REPLACE_ME" in template
    assert (
        "YANDEX_SSO_OPENID_CONFIGURATION_URL="
        "REPLACE_WITH_IDENTITY_HUB_OPENID_CONFIGURATION_URL" in template
    )
    assert "BIOOPS_SESSION_SECRET=REPLACE_WITH_A_LONG_RANDOM_VALUE" in template
    assert (
        "BIOOPS_LOCAL_ACCESS_CODE="
        "REPLACE_WITH_A_SEPARATE_LONG_RANDOM_VALUE" in template
    )
