from __future__ import annotations

import base64
import hashlib
import html
import os
import secrets
import time
from urllib.parse import parse_qs, urlencode

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse


ISSUER = os.getenv(
    "MOCK_IDENTITY_HUB_ISSUER", "http://127.0.0.1:8001"
).rstrip("/")
CLIENT_ID = os.getenv("MOCK_IDENTITY_HUB_CLIENT_ID", "bioops-local")
CLIENT_SECRET = os.getenv(
    "MOCK_IDENTITY_HUB_CLIENT_SECRET", "local-sso-secret"
)
REDIRECT_URI = os.getenv(
    "MOCK_IDENTITY_HUB_REDIRECT_URI",
    "http://127.0.0.1:8000/auth/sso/callback",
)
KEY_ID = "bioops-local-key"

app = FastAPI(title="Local Identity Hub")
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
authorization_codes: dict[str, dict[str, str]] = {}
access_tokens: dict[str, dict[str, object]] = {}


def _base64url_int(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": "invalid_request", "error_description": message},
        status_code=status_code,
    )


@app.get("/.well-known/openid-configuration")
def discovery() -> dict[str, object]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "userinfo_endpoint": f"{ISSUER}/userinfo",
        "jwks_uri": f"{ISSUER}/jwks",
        "scopes_supported": ["openid", "email", "profile"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }


@app.get("/jwks")
def jwks() -> dict[str, object]:
    numbers = private_key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": KEY_ID,
                "n": _base64url_int(numbers.n),
                "e": _base64url_int(numbers.e),
            }
        ]
    }


@app.get("/authorize", response_class=HTMLResponse)
def authorize_page(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    nonce: str,
    code_challenge: str,
    code_challenge_method: str,
) -> HTMLResponse:
    values = {
        "response_type": response_type,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
    }
    hidden = "\n".join(
        f'<input type="hidden" name="{html.escape(name)}" '
        f'value="{html.escape(value)}">'
        for name, value in values.items()
    )
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Genotek SSO | Local Identity Hub</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      background: #f4f6f8;
      color: #20242b;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; }}
    main {{
      display: grid;
      min-height: 100vh;
      place-items: center;
      padding: 24px;
    }}
    section {{
      width: min(420px, 100%);
      padding: 32px;
      border: 1px solid #d9dde3;
      border-radius: 8px;
      background: #fff;
      box-shadow: 0 10px 32px rgba(23, 32, 52, 0.08);
    }}
    .brand {{ margin: 0 0 28px; color: #172034; font-weight: 760; }}
    h1 {{ margin: 0; color: #172034; font-size: 1.75rem; }}
    p {{ margin: 10px 0 24px; color: #626b78; line-height: 1.5; }}
    label {{ display: block; margin-bottom: 7px; font-weight: 650; }}
    input[type="email"] {{
      width: 100%;
      min-height: 44px;
      padding: 0 12px;
      border: 1px solid #cbd0d8;
      border-radius: 6px;
      font: inherit;
    }}
    button {{
      width: 100%;
      min-height: 44px;
      margin-top: 12px;
      border: 0;
      border-radius: 6px;
      background: #264f8f;
      color: #fff;
      cursor: pointer;
      font-weight: 700;
    }}
    small {{ display: block; margin-top: 18px; color: #707987; }}
  </style>
</head>
<body>
  <main>
    <section aria-labelledby="sso-title">
      <p class="brand">Local Identity Hub</p>
      <h1 id="sso-title">Genotek sign in</h1>
      <p>Continue with your work account.</p>
      <form method="post" action="/authorize">
        {hidden}
        <label for="email">Work email</label>
        <input id="email" name="email" type="email"
          value="person@genotek.ru" autocomplete="email" required>
        <button type="submit">Continue</button>
      </form>
      <small>Local development identity provider</small>
    </section>
  </main>
</body>
</html>"""
    )


@app.post("/authorize")
async def authorize(request: Request):
    values = parse_qs(
        (await request.body()).decode("utf-8"), keep_blank_values=True
    )
    field = lambda name: values.get(name, [""])[-1]
    if field("response_type") != "code":
        return _error("Only the authorization-code flow is supported")
    if field("client_id") != CLIENT_ID:
        return _error("Unknown client")
    if field("redirect_uri") != REDIRECT_URI:
        return _error("Redirect URI does not match")
    if field("code_challenge_method") != "S256":
        return _error("PKCE S256 is required")
    email = field("email").strip().casefold()
    if not email:
        return _error("Work email is required")

    code = secrets.token_urlsafe(32)
    authorization_codes[code] = {
        "client_id": field("client_id"),
        "redirect_uri": field("redirect_uri"),
        "nonce": field("nonce"),
        "code_challenge": field("code_challenge"),
        "email": email,
    }
    return RedirectResponse(
        f"{REDIRECT_URI}?{urlencode({'code': code, 'state': field('state')})}",
        status_code=303,
    )


@app.post("/token")
async def token(request: Request):
    values = parse_qs(
        (await request.body()).decode("utf-8"), keep_blank_values=True
    )
    field = lambda name: values.get(name, [""])[-1]
    if field("grant_type") != "authorization_code":
        return _error("Unsupported grant type")
    if field("client_id") != CLIENT_ID or field("client_secret") != CLIENT_SECRET:
        return _error("Client authentication failed", 401)
    record = authorization_codes.get(field("code"))
    if record is None:
        return _error("Authorization code is invalid")
    if field("redirect_uri") != record["redirect_uri"]:
        return _error("Redirect URI does not match")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(field("code_verifier").encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    if not secrets.compare_digest(challenge, record["code_challenge"]):
        return _error("PKCE verification failed")
    authorization_codes.pop(field("code"), None)

    now = int(time.time())
    subject = "local-" + hashlib.sha256(
        record["email"].encode("utf-8")
    ).hexdigest()[:24]
    profile: dict[str, object] = {
        "sub": subject,
        "email": record["email"],
        "email_verified": True,
        "name": "Local Genotek User",
    }
    id_token = jwt.encode(
        {
            **profile,
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "iat": now,
            "exp": now + 300,
            "nonce": record["nonce"],
        },
        private_key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )
    access_token = secrets.token_urlsafe(32)
    access_tokens[access_token] = profile
    return {
        "access_token": access_token,
        "id_token": id_token,
        "token_type": "Bearer",
        "expires_in": 300,
    }


@app.get("/userinfo")
def userinfo(request: Request):
    authorization = request.headers.get("Authorization", "")
    scheme, _, access_token = authorization.partition(" ")
    profile = access_tokens.get(access_token)
    if scheme.lower() != "bearer" or profile is None:
        return _error("Access token is invalid", 401)
    return profile
