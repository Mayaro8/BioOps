from __future__ import annotations

import csv
import hmac
import html
import io
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel
from requests import RequestException

from bioops.api.batch_status_page import BATCH_STATUS_PAGE
from bioops.graph_orchestrator import run_graph
from bioops.tools.batch_status_rows import SHEET_COLUMNS
from bioops.tools.batch_status_store import BatchStatusStore
from bioops.tools.bitrix_sender import BitrixSender
from bioops.tools.notification_store import NotificationStore
from bioops.api.yandex_auth import (
    AuthStore,
    CorporateSSOSettings,
    IdentityHubOIDCClient,
    create_pkce_verifier,
    create_state_token,
    email_is_allowed,
    safe_return_to,
    verify_state_token,
)


logger = logging.getLogger(__name__)

app = FastAPI(
    title="BioOps API",
    description="Web chat and optional Bitrix adapter for BioOps agents.",
)

bitrix_sender = BitrixSender()

_notification_store: NotificationStore | None = None
_batch_status_store: BatchStatusStore | None = None
_auth_store: AuthStore | None = None
_sso_client: IdentityHubOIDCClient | None = None


def get_auth_settings() -> CorporateSSOSettings:
    return CorporateSSOSettings.from_env()


def get_auth_store() -> AuthStore:
    global _auth_store

    if _auth_store is None:
        settings = get_auth_settings()
        _auth_store = AuthStore(
            os.getenv(
                "BIOOPS_AUTH_DB_PATH",
                "/data/bioops_auth.sqlite3",
            )
        )
        for email in settings.bootstrap_emails:
            if email_is_allowed(email, settings.allowed_domain):
                _auth_store.authorize_email(email, source="bootstrap")
            else:
                logger.warning(
                    "Ignoring non-corporate bootstrap email: %s", email
                )
    return _auth_store


def get_sso_client() -> IdentityHubOIDCClient:
    global _sso_client

    settings = get_auth_settings()
    if _sso_client is None:
        _sso_client = IdentityHubOIDCClient(settings)
    return _sso_client


PUBLIC_PATHS = {
    "/health",
    "/login",
    "/auth/sso/login",
    "/auth/sso/callback",
    "/auth/local",
    "/internal/alerts",
    "/bitrix/message",
}
HTML_PATHS = {"/", "/batches"}


@app.middleware("http")
async def require_browser_session(request: Request, call_next):
    settings = get_auth_settings()
    if (
        not settings.enabled
        or request.method == "OPTIONS"
        or request.url.path in PUBLIC_PATHS
    ):
        return await call_next(request)

    token = request.cookies.get(settings.session_cookie_name, "")
    user = get_auth_store().get_session_user(token)
    if user is not None:
        request.state.user = user
        return await call_next(request)

    if request.url.path in HTML_PATHS:
        query = urlencode({"next": request.url.path})
        return RedirectResponse(f"/login?{query}", status_code=303)

    return JSONResponse(
        status_code=401,
        content={"detail": "Sign in with an authorized corporate account."},
    )


def get_notification_store() -> NotificationStore:
    global _notification_store

    if _notification_store is None:
        db_path = os.getenv(
            "BIOOPS_ALERT_DB_PATH",
            "/data/bioops_notifications.sqlite3",
        )
        _notification_store = NotificationStore(
            db_path
        )

    return _notification_store


def get_batch_status_store() -> BatchStatusStore:
    global _batch_status_store

    if _batch_status_store is None:
        db_path = os.getenv(
            "BATCH_STATUS_DB_PATH",
            "/data/bioops_batch_status.sqlite3",
        )
        _batch_status_store = BatchStatusStore(db_path)

    return _batch_status_store


class ChatRequest(BaseModel):
    message: str


class AlertRequest(BaseModel):
    title: str
    message: str
    severity: str = "warning"


class ChatResponse(BaseModel):
    ok: bool
    message: str
    answer: str


AUTH_ERROR_MESSAGES = {
    "sso_denied": "Corporate sign-in was cancelled or denied.",
    "sso_failed": "Corporate sign-in could not be completed. Please try again.",
    "invalid_state": "The sign-in request expired or was invalid. Please try again.",
    "invalid_local_code": "The developer access code is invalid.",
}

_local_login_failures: dict[str, list[datetime]] = {}


def login_page_html(error: str = "", return_to: str = "/") -> str:
    message = AUTH_ERROR_MESSAGES.get(error, error)
    error_html = (
        f'<p class="auth-error" role="alert">{html.escape(message)}</p>'
        if message
        else ""
    )
    login_url = "/auth/sso/login?" + urlencode(
        {"next": safe_return_to(return_to)}
    )
    settings = get_auth_settings()
    local_access_html = ""
    if settings.local_access_enabled:
        local_access_html = f"""
      <div class="auth-divider"><span>or</span></div>
      <form class="local-access" method="post" action="/auth/local">
        <input
          type="hidden"
          name="return_to"
          value="{html.escape(safe_return_to(return_to))}"
        >
        <label for="local-access-code">Developer access code</label>
        <div class="local-access-row">
          <input
            id="local-access-code"
            name="access_code"
            type="password"
            autocomplete="current-password"
            required
          >
          <button type="submit">Sign in</button>
        </div>
      </form>
"""
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in | BioOps</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
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
    .auth-panel {{
      width: min(420px, 100%);
      padding: 32px;
      border: 1px solid #d9dde3;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 10px 32px rgba(23, 32, 52, 0.08);
    }}
    .brand {{
      margin: 0 0 28px;
      color: #172034;
      font-size: 1rem;
      font-weight: 760;
    }}
    h1 {{
      margin: 0;
      color: #172034;
      font-size: 1.75rem;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin: 10px 0 24px;
      color: #626b78;
      line-height: 1.5;
    }}
    .sso-button {{
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 46px;
      width: 100%;
      border: 1px solid #cbd0d8;
      border-radius: 7px;
      background: #ffffff;
      color: #20242b;
      font-weight: 700;
      text-decoration: none;
    }}
    .sso-mark {{
      display: grid;
      width: 26px;
      height: 26px;
      margin-right: 10px;
      border-radius: 50%;
      background: #fc3f1d;
      color: #ffffff;
      font-weight: 800;
      place-items: center;
    }}
    .auth-error {{
      margin: 0 0 18px;
      padding: 11px 12px;
      border-left: 4px solid #c73b3f;
      background: #fff1f1;
      color: #8a2529;
      line-height: 1.4;
    }}
    .auth-divider {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin: 22px 0;
      color: #7b8491;
      font-size: 0.8rem;
    }}
    .auth-divider::before,
    .auth-divider::after {{
      height: 1px;
      flex: 1;
      background: #e1e4e8;
      content: "";
    }}
    .local-access label {{
      display: block;
      margin-bottom: 7px;
      color: #4e5764;
      font-size: 0.84rem;
      font-weight: 650;
    }}
    .local-access-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
    }}
    .local-access input[type="password"] {{
      min-width: 0;
      min-height: 42px;
      padding: 0 11px;
      border: 1px solid #cbd0d8;
      border-radius: 6px;
      font: inherit;
    }}
    .local-access button {{
      min-height: 42px;
      padding: 0 15px;
      border: 0;
      border-radius: 6px;
      background: #264f8f;
      color: #ffffff;
      cursor: pointer;
      font-weight: 700;
    }}
    .access-note {{
      margin: 18px 0 0;
      color: #707987;
      font-size: 0.85rem;
    }}
  </style>
</head>
<body>
  <main>
    <section class="auth-panel" aria-labelledby="sign-in-title">
      <p class="brand">BioOps</p>
      <h1 id="sign-in-title">Sign in</h1>
      <p class="subtitle">Use your Genotek work account to continue.</p>
      {error_html}
      <a class="sso-button" href="{html.escape(login_url)}">
        <span class="sso-mark" aria-hidden="true">Y</span>
        Continue with work email
      </a>
      {local_access_html}
      <p class="access-note">
        Company access is restricted to @genotek.ru accounts.
      </p>
    </section>
  </main>
</body>
</html>
"""


CHAT_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BioOps Chat</title>

  <style>
    :root {
      color-scheme: light dark;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    body {
      margin: 0;
      background: #111827;
      color: #f9fafb;
    }

    main {
      width: min(900px, calc(100% - 32px));
      margin: 32px auto;
    }

    h1 {
      margin-bottom: 4px;
    }

    .chat-nav {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 24px;
      padding-bottom: 12px;
      border-bottom: 1px solid #374151;
    }

    .chat-nav strong {
      color: #f9fafb;
    }

    .chat-nav-links {
      display: flex;
      align-items: center;
      gap: 18px;
    }

    .chat-nav a {
      color: #cbd5e1;
      font-size: 0.9rem;
      font-weight: 600;
      text-decoration: none;
    }

    .chat-nav a[aria-current="page"] {
      color: #93c5fd;
    }

    #logout-form {
      display: inline;
      margin: 0;
    }

    #logout-form button {
      min-width: auto;
      padding: 0;
      background: transparent;
      color: #cbd5e1;
      font-size: 0.9rem;
    }

    .subtitle {
      margin-top: 0;
      color: #9ca3af;
    }

    #notification-panel {
      margin-bottom: 14px;
      padding: 14px;
      border: 1px solid #92400e;
      border-radius: 12px;
      background: #422006;
    }

    #notification-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    #notification-items {
      margin-top: 8px;
    }

    .notification-item {
      margin-top: 8px;
      padding: 10px;
      border-radius: 8px;
      background: #78350f;
      white-space: pre-wrap;
    }

    .notification-item.info {
      background: #1e3a5f;
    }

    .notification-item.critical {
      background: #7f1d1d;
    }

    .notification-time {
      color: #d1d5db;
      font-size: 0.85rem;
    }

    .notification-read {
      min-width: auto;
      margin-top: 8px;
      padding: 6px 10px;
      background: #374151;
    }

    #messages {
      min-height: 420px;
      max-height: 65vh;
      overflow-y: auto;
      padding: 16px;
      border: 1px solid #374151;
      border-radius: 12px;
      background: #1f2937;
    }

    .message {
      margin: 12px 0;
      padding: 12px 14px;
      border-radius: 10px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .user {
      margin-left: 15%;
      background: #1d4ed8;
    }

    .assistant {
      margin-right: 15%;
      background: #374151;
    }

    .error {
      background: #7f1d1d;
    }

    form {
      display: flex;
      gap: 10px;
      margin-top: 14px;
    }

    textarea {
      flex: 1;
      min-height: 54px;
      resize: vertical;
      padding: 12px;
      border: 1px solid #4b5563;
      border-radius: 10px;
      font: inherit;
    }

    button {
      min-width: 100px;
      border: 0;
      border-radius: 10px;
      padding: 0 18px;
      background: #2563eb;
      color: white;
      font-weight: 600;
      cursor: pointer;
    }

    button:disabled {
      cursor: wait;
      opacity: 0.6;
    }
  
/* BIOOPS_COLLAPSIBLE_ALERTS_CSS */
#notification-header {
  cursor: pointer;
  user-select: none;
}

#notification-header::before {
  content: "+";
  display: inline-block;
  margin-right: 8px;
  font-size: 0.75rem;
}

#notification-panel[data-open="true"] #notification-header::before {
  content: "-";
}

#notification-panel[data-open="false"] #notification-items {
  display: none;
}

#notification-items {
  max-height: 220px;
  overflow-y: auto;
}

</style>
</head>

<body>
  <main>
    <nav class="chat-nav" aria-label="Primary navigation">
      <strong>BioOps</strong>
      <span class="chat-nav-links">
        <a href="/" aria-current="page">Chat</a>
        <a href="/batches">Batch status</a>
        <form id="logout-form" method="post" action="/logout">
          <button type="submit">Sign out</button>
        </form>
      </span>
    </nav>
    <h1>BioOps Chat</h1>
    <p class="subtitle">
      Ask about workflows, batches, workflow health, storage, documentation, or code review.
    </p>

    <section
      id="notification-panel"
      aria-live="polite"
    >
      <div id="notification-header">
        <strong>Infrastructure notifications</strong>
        <span>
          Unread:
          <span id="notification-count">0</span>
        </span>
      </div>

      <div id="notification-items">
        No notifications yet.
      </div>
    </section>

    <section id="messages" aria-live="polite">
      <div class="message assistant">
        BioOps is ready. Enter a question below.
      </div>
    </section>

    <form id="chat-form">
      <textarea
        id="message-input"
        name="message"
        placeholder="Example: Show failed batches"
        required
      ></textarea>

      <button id="send-button" type="submit">Send</button>
    </form>
  </main>

  <script>
    const form = document.getElementById("chat-form");
    const input = document.getElementById("message-input");
    const messages = document.getElementById("messages");
    const button = document.getElementById("send-button");
    const notificationItems =
      document.getElementById("notification-items");
    const notificationCount =
      document.getElementById("notification-count");

    function addMessage(text, className) {
      const element = document.createElement("div");
      element.className = `message ${className}`;
      element.textContent = text;
      messages.appendChild(element);
      messages.scrollTop = messages.scrollHeight;
    }

    async function markNotificationRead(id) {
      await fetch(`/alerts/${id}/read`, {
        method: "POST"
      });

      await refreshNotifications();
    }

    async function refreshNotifications() {
      try {
        const response = await fetch(
          "/alerts?limit=10"
        );

        if (!response.ok) {
          return;
        }

        const payload = await response.json();

        notificationCount.textContent =
          payload.unread;

        notificationItems.replaceChildren();

        if (payload.items.length === 0) {
          notificationItems.textContent =
            "No notifications yet.";
          return;
        }

        payload.items.forEach((item) => {
          const element =
            document.createElement("div");

          element.className =
            `notification-item ${item.severity}`;

          const title =
            document.createElement("strong");

          title.textContent =
            `[${item.severity.toUpperCase()}] ` +
            item.title;

          const timestamp =
            document.createElement("div");

          timestamp.className =
            "notification-time";

          const moscowTime =
            new Date(
              item.created_at
            ).toLocaleString(
              "en-GB",
              { timeZone: "Europe/Moscow" }
            );

          timestamp.textContent =
            `${moscowTime} MSK`;

          const message =
            document.createElement("div");

          message.textContent = item.message;

          element.append(
            title,
            timestamp,
            message
          );

          if (!item.is_read) {
            const readButton =
              document.createElement("button");

            readButton.type = "button";
            readButton.className =
              "notification-read";
            readButton.textContent =
              "Mark as read";

            readButton.addEventListener(
              "click",
              () => markNotificationRead(
                item.id
              )
            );

            element.appendChild(readButton);
          }

          notificationItems.appendChild(
            element
          );
        });
      } catch (error) {
        console.error(
          "Could not load notifications",
          error
        );
      }
    }

    refreshNotifications();
    setInterval(
      refreshNotifications,
      15000
    );

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const message = input.value.trim();

      if (!message) {
        return;
      }

      addMessage(message, "user");
      input.value = "";
      button.disabled = true;
      button.textContent = "Working...";

      try {
        const response = await fetch("/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ message })
        });

        const payload = await response.json();

        if (!response.ok) {
          throw new Error(payload.detail || "BioOps request failed");
        }

        addMessage(payload.answer, "assistant");
      } catch (error) {
        addMessage(String(error), "error");
      } finally {
        button.disabled = false;
        button.textContent = "Send";
        input.focus();
      }
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
  
/* BIOOPS_COLLAPSIBLE_ALERTS_JS */
(function () {
  function installCollapsibleNotifications() {
    const panel = document.getElementById("notification-panel");
    const header = document.getElementById("notification-header");
    const items = document.getElementById("notification-items");

    if (!panel || !header || !items) {
      console.warn("Notification panel elements were not found.");
      return;
    }

    panel.dataset.open = "false";

    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");
    header.setAttribute("aria-expanded", "false");

    function togglePanel() {
      const willOpen = panel.dataset.open !== "true";

      panel.dataset.open = String(willOpen);
      header.setAttribute("aria-expanded", String(willOpen));
    }

    header.addEventListener("click", togglePanel);

    header.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        togglePanel();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      installCollapsibleNotifications
    );
  } else {
    installCollapsibleNotifications();
  }
})();

</script>
</body>
</html>
"""


ACTIVE_BATCH_STATUSES = {"pending", "running"}
FAILED_BATCH_STATUSES = {"failed", "error"}
COMPLETED_BATCH_STATUSES = {"succeeded", "completed"}
VALID_BATCH_FILTERS = {"", "active", "failed", "completed", "stale"}


def _batch_status_group(status: str) -> str:
    normalized = status.strip().lower()

    if normalized in ACTIVE_BATCH_STATUSES:
        return "active"
    if normalized in FAILED_BATCH_STATUSES:
        return "failed"
    if normalized in COMPLETED_BATCH_STATUSES:
        return "completed"

    return "other"


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _stale_minutes() -> int:
    raw_value = os.getenv("BATCH_STATUS_STALE_MINUTES", "30")

    try:
        return max(1, int(raw_value))
    except ValueError:
        return 30


def _prepare_batch_rows(
    rows: list[dict[str, str]],
    *,
    search: str,
    status: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=_stale_minutes())
    prepared: list[dict[str, Any]] = []

    for row in rows:
        checked_at = _parse_timestamp(row.get("last_checked_at", ""))
        is_stale = (
            _batch_status_group(row.get("status", "")) == "active"
            and checked_at is not None
            and checked_at < stale_before
        )
        prepared.append({**row, "is_stale": is_stale})

    summary = {
        "total": len(prepared),
        "active": sum(
            _batch_status_group(str(row["status"])) == "active"
            for row in prepared
        ),
        "failed": sum(
            _batch_status_group(str(row["status"])) == "failed"
            for row in prepared
        ),
        "completed": sum(
            _batch_status_group(str(row["status"])) == "completed"
            for row in prepared
        ),
        "stale": sum(bool(row["is_stale"]) for row in prepared),
    }

    normalized_search = search.strip().lower()
    normalized_status = status.strip().lower()

    if normalized_status not in VALID_BATCH_FILTERS:
        raise HTTPException(
            status_code=400,
            detail="Unknown batch status filter.",
        )

    filtered = prepared

    if normalized_search:
        filtered = [
            row
            for row in filtered
            if any(
                normalized_search in str(row.get(column, "")).lower()
                for column in SHEET_COLUMNS
            )
        ]

    if normalized_status == "stale":
        filtered = [row for row in filtered if row["is_stale"]]
    elif normalized_status:
        filtered = [
            row
            for row in filtered
            if _batch_status_group(str(row["status"])) == normalized_status
        ]

    return filtered, summary


@app.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    error: str = "",
    next: str = "/",
) -> Response:
    settings = get_auth_settings()
    token = request.cookies.get(settings.session_cookie_name, "")
    if settings.enabled and get_auth_store().get_session_user(token):
        return RedirectResponse(safe_return_to(next), status_code=303)
    return HTMLResponse(login_page_html(error, next))


@app.get("/auth/sso/login")
def sso_login(next: str = "/") -> Response:
    settings = get_auth_settings()
    try:
        settings.require_sso_configuration()
    except RuntimeError:
        logger.exception("Corporate SSO configuration is incomplete.")
        return HTMLResponse(
            login_page_html(
                "Corporate SSO is not configured. Contact the BioOps administrator."
            ),
            status_code=503,
        )

    oidc_nonce = secrets.token_urlsafe(32)
    code_verifier = create_pkce_verifier()
    state = create_state_token(
        secret=settings.session_secret,
        return_to=safe_return_to(next),
        oidc_nonce=oidc_nonce,
        code_verifier=code_verifier,
    )
    try:
        authorization_url = get_sso_client().authorization_url(
            state=state,
            nonce=oidc_nonce,
            code_verifier=code_verifier,
        )
    except (RuntimeError, RequestException):
        logger.exception("Corporate SSO discovery failed.")
        return HTMLResponse(
            login_page_html("sso_failed"), status_code=502
        )
    response = RedirectResponse(
        authorization_url,
        status_code=303,
    )
    response.set_cookie(
        settings.state_cookie_name,
        state,
        max_age=settings.state_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/auth/sso/callback",
    )
    return response


@app.post("/auth/local")
async def local_access_login(request: Request) -> Response:
    settings = get_auth_settings()
    try:
        settings.require_local_access_configuration()
    except RuntimeError:
        return HTMLResponse(
            login_page_html(
                "Developer access is not configured. Contact the BioOps administrator."
            ),
            status_code=503,
        )

    client_address = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=5)
    failures = [
        attempted_at
        for attempted_at in _local_login_failures.get(client_address, [])
        if attempted_at > cutoff
    ]
    _local_login_failures[client_address] = failures
    if len(failures) >= 5:
        return HTMLResponse(
            login_page_html(
                "Too many failed developer sign-in attempts. Try again later."
            ),
            status_code=429,
        )

    body = await request.body()
    values = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    access_code = values.get("access_code", [""])[-1]
    return_to = safe_return_to(values.get("return_to", ["/"])[-1])
    if not hmac.compare_digest(access_code, settings.local_access_code):
        failures.append(now)
        _local_login_failures[client_address] = failures
        return HTMLResponse(
            login_page_html("invalid_local_code", return_to),
            status_code=401,
        )

    _local_login_failures.pop(client_address, None)
    user = get_auth_store().link_external_user(
        provider="local",
        provider_user_id="developer",
        email="developer@bioops.local",
        display_name="BioOps Developer",
    )
    session_token = get_auth_store().create_session(
        user_id=int(user["id"]),
        ttl_hours=settings.session_ttl_hours,
    )
    response = RedirectResponse(return_to, status_code=303)
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@app.get("/auth/sso/callback")
def sso_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
) -> Response:
    settings = get_auth_settings()
    try:
        settings.require_sso_configuration()
    except RuntimeError:
        return HTMLResponse(
            login_page_html(
                "Corporate SSO is not configured. Contact the BioOps administrator."
            ),
            status_code=503,
        )
    if error:
        return HTMLResponse(
            login_page_html("sso_denied"), status_code=400
        )
    if not code:
        return HTMLResponse(
            login_page_html("Identity Hub did not return an authorization code."),
            status_code=400,
        )

    state_cookie = request.cookies.get(settings.state_cookie_name, "")
    if not state or not state_cookie or not hmac.compare_digest(
        state, state_cookie
    ):
        return HTMLResponse(
            login_page_html("invalid_state"), status_code=400
        )

    try:
        state_payload = verify_state_token(
            state,
            secret=settings.session_secret,
            ttl_minutes=settings.state_ttl_minutes,
        )
        oidc_nonce = str(state_payload["oidc_nonce"])
        code_verifier = str(state_payload["code_verifier"])
        profile = get_sso_client().complete_login(
            code=code,
            code_verifier=code_verifier,
            nonce=oidc_nonce,
        )
    except (ValueError, RuntimeError, RequestException):
        logger.exception("Corporate SSO callback failed.")
        return HTMLResponse(
            login_page_html("sso_failed"), status_code=502
        )

    email = str(profile.get("email", "")).strip().casefold()
    if not email_is_allowed(
        email,
        settings.allowed_domain,
    ):
        response = HTMLResponse(
            login_page_html(
                "Access denied. BioOps is available only to "
                f"@{settings.allowed_domain} accounts or explicitly "
                "approved users."
            ),
            status_code=403,
        )
        response.delete_cookie(
            settings.state_cookie_name,
            path="/auth/sso/callback",
        )
        return response

    if not get_auth_store().is_email_authorized(email):
        response = HTMLResponse(
            login_page_html(
                "Access denied. This Genotek email is not active in the "
                "BioOps employee database."
            ),
            status_code=403,
        )
        response.delete_cookie(
            settings.state_cookie_name,
            path="/auth/sso/callback",
        )
        return response

    subject = str(profile.get("sub", "")).strip()
    if not subject:
        return HTMLResponse(
            login_page_html("Identity Hub did not return a stable user ID."),
            status_code=502,
        )

    display_name = str(
        profile.get("name")
        or profile.get("preferred_username")
        or email
    ).strip()
    user = get_auth_store().link_sso_user(
        subject=subject,
        email=email,
        display_name=display_name,
    )
    session_token = get_auth_store().create_session(
        user_id=int(user["id"]),
        ttl_hours=settings.session_ttl_hours,
    )
    response = RedirectResponse(
        safe_return_to(str(state_payload.get("return_to", "/"))),
        status_code=303,
    )
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        settings.state_cookie_name,
        path="/auth/sso/callback",
    )
    return response


@app.post("/logout")
def logout(request: Request) -> Response:
    settings = get_auth_settings()
    token = request.cookies.get(settings.session_cookie_name, "")
    get_auth_store().revoke_session(token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response


@app.get("/auth/me")
def current_user(request: Request) -> dict[str, Any]:
    return dict(request.state.user)


@app.get("/", response_class=HTMLResponse)
def chat_page() -> str:
    return CHAT_PAGE


@app.get("/batches", response_class=HTMLResponse)
def batch_status_page() -> str:
    return BATCH_STATUS_PAGE


@app.get("/api/batches")
def list_batch_status(
    search: str = "",
    status: str = "",
    limit: int = Query(default=250, ge=1, le=1000),
) -> dict[str, Any]:
    rows = get_batch_status_store().list_all_rows()
    filtered, summary = _prepare_batch_rows(
        rows,
        search=search,
        status=status,
    )
    latest_update = next(
        (
            row["last_checked_at"]
            for row in rows
            if row.get("last_checked_at")
        ),
        "",
    )

    return {
        "items": filtered[:limit],
        "matching": len(filtered),
        "summary": summary,
        "latest_update": latest_update,
    }


@app.get("/batch-status.csv")
def download_batch_status_csv(
    search: str = "",
    status: str = "",
) -> Response:
    rows = get_batch_status_store().list_all_rows()
    filtered, _ = _prepare_batch_rows(
        rows,
        search=search,
        status=status,
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=SHEET_COLUMNS)
    writer.writeheader()
    writer.writerows(
        {
            column: str(row.get(column, ""))
            for column in SHEET_COLUMNS
        }
        for row in filtered
    )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="bioops-batch-status.csv"'
            )
        },
    )


@app.post("/internal/alerts")
def create_alert(
    payload: AlertRequest,
    request: Request,
) -> dict:
    expected_token = os.getenv(
        "BIOOPS_INTERNAL_ALERT_TOKEN",
        "",
    )
    supplied_token = request.headers.get(
        "X-BioOps-Alert-Token",
        "",
    )

    if (
        expected_token
        and supplied_token != expected_token
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid alert token.",
        )

    return get_notification_store().create(
        title=payload.title,
        message=payload.message,
        severity=payload.severity,
    )


@app.get("/alerts")
def list_alerts(limit: int = 50) -> dict:
    store = get_notification_store()

    return {
        "items": store.list_recent(limit),
        "unread": store.unread_count(),
    }


@app.post("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: int) -> dict:
    try:
        return get_notification_store().mark_read(
            alert_id
        )
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail="Alert not found.",
        ) from None


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "bioops-api",
    }


def process_message(message: str) -> str:
    clean_message = message.strip()

    if not clean_message:
        raise ValueError("Message cannot be empty.")

    return run_graph(clean_message)


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    try:
        answer = process_message(message)
    except Exception:
        logger.exception("BioOps failed while processing a chat message.")
        raise HTTPException(
            status_code=500,
            detail="BioOps failed while processing the message.",
        ) from None

    return ChatResponse(
        ok=True,
        message=message,
        answer=answer,
    )


def nested_value(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data

    for key in keys:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def first_text(*values: Any) -> str:
    for value in values:
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue

        text = str(value).strip()

        if text:
            return text

    return ""


def extract_message(data: dict[str, Any]) -> str:
    return first_text(
        data.get("data[message][text]"),
        nested_value(data, "data", "message", "text"),
        data.get("message"),
        data.get("MESSAGE"),
        data.get("text"),
        data.get("TEXT"),
        nested_value(data, "PARAMS", "MESSAGE"),
        nested_value(data, "event", "text"),
    )


def extract_chat_id(data: dict[str, Any]) -> str | None:
    chat_id = first_text(
        data.get("data[chat][dialogId]"),
        data.get("data[message][chatId]"),
        nested_value(data, "data", "chat", "dialogId"),
        nested_value(data, "data", "message", "chatId"),
        data.get("chat_id"),
        data.get("DIALOG_ID"),
        data.get("dialog_id"),
        nested_value(data, "PARAMS", "DIALOG_ID"),
        nested_value(data, "event", "dialog_id"),
    )

    return chat_id or None


async def read_request_payload(request: Request) -> dict[str, Any]:
    body = await request.body()

    if not body:
        return {}

    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

        return payload if isinstance(payload, dict) else {}

    try:
        parsed = parse_qs(
            body.decode("utf-8"),
            keep_blank_values=True,
        )
    except UnicodeDecodeError:
        return {}

    return {
        key: values[-1] if values else ""
        for key, values in parsed.items()
    }


@app.post("/bitrix/message")
async def bitrix_message(request: Request) -> dict[str, Any]:
    data = await read_request_payload(request)

    message = extract_message(data)
    chat_id = extract_chat_id(data)

    if not message:
        answer = "BioOps received an empty message."
    else:
        try:
            answer = process_message(message)
        except Exception as error:
            logger.exception("BioOps failed while processing a Bitrix message.")
            answer = (
                "BioOps failed while processing your message.\n\n"
                f"Error: {type(error).__name__}: {error}"
            )

    delivered = False

    try:
        bitrix_sender.send_message(
            text=answer,
            chat_id=chat_id,
        )
        delivered = True
    except Exception:
        logger.exception("Could not send the BioOps response to Bitrix.")

    return {
        "ok": True,
        "received": message,
        "chat_id": chat_id,
        "answer": answer,
        "delivered_to_bitrix": delivered,
    }
